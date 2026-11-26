"""Turn mutmut results into a SonarQube Generic Issue Import report.

SonarQube Community Build has no Python mutation-testing plugin, but it imports
issues from any tool in its "generic issue" JSON format. This script writes one
issue per mutant the tests did not catch (it survived, or no test reached it),
on the line that was mutated, and prints the mutation score.

Run it after ``mutmut run``, from the folder that holds ``mutants/``, in the
same environment as mutmut (it calls ``mutmut show`` for each diff):

    python scripts/mutants_to_sonar.py --output mutation-report.json

The scanner then picks the report up with
``-Dsonar.externalIssuesReportPaths=mutation-report.json``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

# mutmut's own meaning of a mutant's exit code (mutmut/stats.py).
STATUS_BY_EXIT_CODE = {
    0: "survived",
    1: "killed",
    3: "killed",
    5: "no tests",
    33: "no tests",
    34: "skipped",
    36: "timeout",
    24: "timeout",
    -24: "timeout",
    152: "timeout",
    255: "timeout",
    37: "caught by type check",
    None: "not checked",
}
# Statuses that mean "a test noticed the change". A timeout counts: the mutant
# made the code hang, and the test run caught that.
CAUGHT = {"killed", "timeout", "caught by type check"}
# Statuses that become SonarQube issues.
MISSED = {"survived", "no tests"}

RULE_ID = "survived-mutant"
RULE = {
    "id": RULE_ID,
    "name": "Mutant not caught by the tests",
    "description": (
        "mutmut changed this line (for example < into <=, and into or, a value "
        "into None) and every unit test still passed. Add or tighten a test so "
        "that it fails for the changed code."
    ),
    "engineId": "mutmut",
    "cleanCodeAttribute": "TESTED",
    "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
}
EFFORT_MINUTES = 10

# Class methods are named x<SEP>Class<SEP>method; SEP is U+01C1, written with
# chr() so the file stays ASCII.
CLASS_SEP = chr(0x01C1)
MUTANT_RE = re.compile(r"^x_?(?P<func>.+)__mutmut_\d+$")
HUNK_RE = re.compile(r"^@@ -(?P<start>\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")


@dataclass(frozen=True)
class Mutant:
    name: str  # e.g. files.paths.x_clean_name__mutmut_3
    path: str  # source file, relative to the project root
    status: str


@dataclass(frozen=True)
class Change:
    offset: int  # 1-based line inside the function's source text
    removed: str
    added: str
    first_removed: str  # the first removed line as it stands, to find it again


def status_of(exit_code: int | None) -> str:
    return STATUS_BY_EXIT_CODE.get(exit_code, "suspicious")


def load_mutants(mutants_dir: Path) -> list[Mutant]:
    """Read every ``<file>.py.meta`` mutmut wrote next to the mutated copies."""
    mutants = []
    for meta in sorted(mutants_dir.rglob("*.py.meta")):
        source = meta.relative_to(mutants_dir).with_suffix("").as_posix()
        codes = json.loads(meta.read_text(encoding="utf-8"))["exit_code_by_key"]
        for name, code in codes.items():
            mutants.append(Mutant(name=name, path=source, status=status_of(code)))
    return mutants


def mutation_score(mutants: Iterable[Mutant]) -> tuple[int, int, float]:
    """Return (caught, tested, percent). Skipped and unchecked ones don't count."""
    counts = Counter(m.status for m in mutants)
    tested = sum(n for status, n in counts.items() if status in CAUGHT | MISSED)
    tested += counts["suspicious"]
    caught = sum(counts[status] for status in CAUGHT)
    return caught, tested, (100.0 * caught / tested if tested else 0.0)


def function_path(mutant_name: str) -> tuple[str | None, str]:
    """``mod.xǁCǁm__mutmut_2`` -> ("C", "m"); ``mod.x_f__mutmut_1`` -> (None, "f")."""
    last = mutant_name.rsplit(".", 1)[-1]
    if last.startswith("x" + CLASS_SEP):
        _, cls, rest = last.split(CLASS_SEP, 2)
        return cls, rest.rsplit("__mutmut_", 1)[0]
    match = MUTANT_RE.match(last)
    if not match:
        raise ValueError(f"not a mutmut mutant name: {mutant_name}")
    return None, match["func"]


def parse_diff(diff: str) -> Change | None:
    """Find the first changed line of a ``mutmut show`` diff of one function."""
    line_no = None
    removed: list[str] = []
    added: list[str] = []
    first = None
    for line in diff.splitlines():
        if line.startswith(("---", "+++")):
            continue
        hunk = HUNK_RE.match(line)
        if hunk:
            if first is not None:
                break
            line_no = int(hunk["start"])
            continue
        if line_no is None:
            continue
        if line.startswith("-"):
            first = first or line_no
            removed.append(line[1:].strip())
            line_no += 1
        elif line.startswith("+"):
            first = first or line_no
            added.append(line[1:].strip())
        elif first is not None:
            break
        else:
            line_no += 1
    if first is None:
        return None
    return Change(
        offset=first,
        removed=" ".join(removed),
        added=" ".join(added),
        first_removed=removed[0] if removed else "",
    )


def function_span(source: str, cls: str | None, func: str) -> tuple[int, int] | None:
    """First (decorator included) and last line of a function in the file."""
    tree = ast.parse(source)
    scope: Iterable[ast.AST] = tree.body
    if cls is not None:
        owner = next(
            (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls),
            None,
        )
        if owner is None:
            return None
        scope = owner.body
    for node in scope:
        is_function = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        if is_function and node.name == func:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return first, node.end_lineno or node.lineno
    return None


def locate(source: str, mutant: Mutant, change: Change | None) -> int:
    """The line in the original file that the mutant changed (1 if unknown)."""
    cls, func = function_path(mutant.name)
    span = function_span(source, cls, func)
    if span is None:
        return 1
    start, end = span
    if change is None:
        return start
    guess = start + change.offset - 1
    lines = source.splitlines()
    # The offset is exact unless comments sit right above the def; so look for
    # the removed line itself and take the match closest to the guess.
    candidates = [
        n
        for n in range(start, end + 1)
        if change.first_removed and lines[n - 1].strip() == change.first_removed
    ]
    if candidates:
        return min(candidates, key=lambda n: abs(n - guess))
    return min(max(guess, start), end)


def message(mutant: Mutant, change: Change | None) -> str:
    if mutant.status == "no tests":
        lead = "No unit test runs this code, so no mutant here can be caught"
    else:
        lead = "Mutant survived: every unit test still passes"
    if change is None:
        return f"{lead} ({mutant.name})."
    edit = f"'{change.removed}' -> '{change.added or '(removed)'}'"
    return f"{lead} after {edit} ({mutant.name.rsplit('.', 1)[-1]})."


def build_report(
    mutants: Iterable[Mutant],
    show: Callable[[str], str],
    read_source: Callable[[str], str],
) -> dict:
    issues = []
    for mutant in mutants:
        if mutant.status not in MISSED:
            continue
        change = parse_diff(show(mutant.name))
        line = locate(read_source(mutant.path), mutant, change)
        issues.append(
            {
                "ruleId": RULE_ID,
                "effortMinutes": EFFORT_MINUTES,
                "primaryLocation": {
                    "message": message(mutant, change),
                    "filePath": mutant.path,
                    "textRange": {"startLine": line},
                },
            }
        )
    return {"rules": [RULE], "issues": issues}


def mutmut_show(name: str) -> str:
    result = subprocess.run(
        ["mutmut", "show", name], capture_output=True, text=True, check=True
    )
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mutmut results -> SonarQube issues")
    parser.add_argument("--mutants", type=Path, default=Path("mutants"))
    parser.add_argument("--output", type=Path, default=Path("mutation-report.json"))
    args = parser.parse_args(argv)

    mutants = load_mutants(args.mutants)
    if not mutants:
        print(f"No mutmut results in {args.mutants}/. Run 'mutmut run' first.")
        return 1

    report = build_report(
        mutants,
        show=mutmut_show,
        read_source=lambda path: Path(path).read_text(encoding="utf-8"),
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    caught, tested, score = mutation_score(mutants)
    print(f"Mutation score: {caught}/{tested} caught = {score:.1f}%")
    by_file = Counter((m.path, m.status) for m in mutants)
    for (path, status), n in sorted(by_file.items()):
        print(f"  {path:35} {status:12} {n}")
    print(f"{len(report['issues'])} issues written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
