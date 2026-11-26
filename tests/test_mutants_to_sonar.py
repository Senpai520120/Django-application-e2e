"""scripts/mutants_to_sonar.py: mutmut results -> SonarQube generic issues."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mutants_to_sonar.py"
_spec = importlib.util.spec_from_file_location("mutants_to_sonar", SCRIPT)
assert _spec and _spec.loader
m2s = importlib.util.module_from_spec(_spec)
# dataclasses look their module up in sys.modules.
sys.modules[_spec.name] = m2s
_spec.loader.exec_module(m2s)

SEP = chr(0x01C1)  # mutmut's separator in class-method mutant names

SOURCE = '''"""A module."""


def clean_name(value):
    # a comment
    value = value.strip()
    if len(value) > 255:
        raise ValueError("too long")
    return value


class Form:
    @property
    def size(self):
        return 1 + 2
'''

DIFF_FUNC = """--- files/paths.py
+++ files/paths.py
@@ -1,6 +1,6 @@
 def clean_name(value):
     # a comment
     value = value.strip()
-    if len(value) > 255:
+    if len(value) >= 255:
         raise ValueError("too long")
     return value"""

DIFF_METHOD = """--- files/forms.py
+++ files/forms.py
@@ -1,3 +1,3 @@
 @property
 def size(self):
-    return 1 + 2
+    return 1 - 2"""


def write_meta(root: Path, source: str, codes: dict) -> None:
    meta = root / f"{source}.meta"
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"exit_code_by_key": codes}), encoding="utf-8")


def test_load_mutants_reads_every_meta_file(tmp_path):
    write_meta(
        tmp_path,
        "files/paths.py",
        {"files.paths.x_clean_name__mutmut_1": 1, "files.paths.x_f__mutmut_2": 0},
    )
    write_meta(tmp_path, "airflow/dags/upload_groups.py", {"a.x_g__mutmut_1": None})

    mutants = m2s.load_mutants(tmp_path)

    assert [(m.path, m.status) for m in mutants] == [
        ("airflow/dags/upload_groups.py", "not checked"),
        ("files/paths.py", "killed"),
        ("files/paths.py", "survived"),
    ]


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (0, "survived"),
        (1, "killed"),
        (33, "no tests"),
        (36, "timeout"),
        (99, "suspicious"),
    ],
)
def test_status_follows_mutmut_exit_codes(code, status):
    assert m2s.status_of(code) == status


def test_score_counts_timeouts_as_caught_and_ignores_skipped():
    mutants = [
        m2s.Mutant("a", "f.py", status)
        for status in ["killed", "killed", "timeout", "survived", "no tests", "skipped"]
    ]
    assert m2s.mutation_score(mutants) == (3, 5, 60.0)


def test_score_of_nothing_is_zero():
    assert m2s.mutation_score([]) == (0, 0, 0.0)


def test_function_path_of_function_and_method():
    assert m2s.function_path("files.paths.x_clean_name__mutmut_3") == (
        None,
        "clean_name",
    )
    assert m2s.function_path(f"files.forms.x{SEP}Form{SEP}size__mutmut_12") == (
        "Form",
        "size",
    )
    # A private helper keeps its own leading underscore.
    assert m2s.function_path("upload_groups.x__quote__mutmut_1") == (None, "_quote")
    with pytest.raises(ValueError):
        m2s.function_path("files.paths.clean_name")


def test_parse_diff_finds_the_changed_line():
    change = m2s.parse_diff(DIFF_FUNC)
    assert change == m2s.Change(
        offset=4,
        removed="if len(value) > 255:",
        added="if len(value) >= 255:",
        first_removed="if len(value) > 255:",
    )
    assert m2s.parse_diff("") is None


def test_locate_maps_the_change_to_the_source_line():
    func = m2s.Mutant(
        "files.paths.x_clean_name__mutmut_1", "files/paths.py", "survived"
    )
    method = m2s.Mutant(
        f"files.forms.x{SEP}Form{SEP}size__mutmut_1", "files/forms.py", "survived"
    )
    assert m2s.locate(SOURCE, func, m2s.parse_diff(DIFF_FUNC)) == 7
    assert m2s.locate(SOURCE, method, m2s.parse_diff(DIFF_METHOD)) == 15
    # Without a diff the issue goes on the def line; an unknown function on line 1.
    assert m2s.locate(SOURCE, func, None) == 4
    gone = m2s.Mutant("files.paths.x_gone__mutmut_1", "files/paths.py", "survived")
    assert m2s.locate(SOURCE, gone, None) == 1


def test_build_report_has_one_issue_per_missed_mutant():
    mutants = [
        m2s.Mutant("files.paths.x_clean_name__mutmut_1", "files/paths.py", "survived"),
        m2s.Mutant("files.paths.x_clean_name__mutmut_2", "files/paths.py", "killed"),
        m2s.Mutant("files.paths.x_clean_name__mutmut_3", "files/paths.py", "no tests"),
    ]
    diffs = {"files.paths.x_clean_name__mutmut_1": DIFF_FUNC}

    report = m2s.build_report(
        mutants, show=lambda name: diffs.get(name, ""), read_source=lambda _path: SOURCE
    )

    assert report["rules"][0]["id"] == m2s.RULE_ID
    assert [i["primaryLocation"]["textRange"] for i in report["issues"]] == [
        {"startLine": 7},
        {"startLine": 4},
    ]
    first, second = (i["primaryLocation"]["message"] for i in report["issues"])
    assert "survived" in first
    assert "'if len(value) > 255:' -> 'if len(value) >= 255:'" in first
    assert "No unit test runs this code" in second


def test_main_writes_the_report_and_prints_the_score(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "files").mkdir()
    (tmp_path / "files/paths.py").write_text(SOURCE, encoding="utf-8")
    write_meta(
        tmp_path / "mutants",
        "files/paths.py",
        {
            "files.paths.x_clean_name__mutmut_1": 0,
            "files.paths.x_clean_name__mutmut_2": 1,
        },
    )
    monkeypatch.setattr(m2s, "mutmut_show", lambda _name: DIFF_FUNC)

    assert m2s.main(["--output", "out.json"]) == 0

    report = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert len(report["issues"]) == 1
    assert "Mutation score: 1/2 caught = 50.0%" in capsys.readouterr().out


def test_main_without_results_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert m2s.main([]) == 1
    assert "Run 'mutmut run' first" in capsys.readouterr().out
