"""Create GitHub issues from tools/test_cases.json, or write docs/test-cases.md.

Each issue looks like one filled in through the "Test case" form
(.github/ISSUE_TEMPLATE/test-case.yml). Issues that already exist (same ID in
the title) are skipped, so the script can be run again safely.

Creating issues needs the GitHub CLI: https://cli.github.com, then `gh auth login`.
The issues are created from your GitHub account.

Usage:
    python tools/create_test_case_issues.py --dry-run     # show, create nothing
    python tools/create_test_case_issues.py               # create the issues
    python tools/create_test_case_issues.py --markdown    # write docs/test-cases.md
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
CASES_FILE = ROOT / "tools" / "test_cases.json"
MARKDOWN_FILE = ROOT / "docs" / "test-cases.md"
LABEL = "test-case"


def load_cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def numbered(steps: list[str]) -> str:
    return "\n".join(f"{number}. {step}" for number, step in enumerate(steps, 1))


def issue_title(case: dict) -> str:
    return f"[{case['id']}] {case['title']}"


def issue_body(case: dict) -> str:
    """The same markdown GitHub makes when the issue form is submitted."""
    return (
        f"### Preconditions\n\n{case['preconditions']}\n\n"
        f"### Steps\n\n{numbered(case['steps'])}\n\n"
        f"### Expected result\n\n{case['expected']}\n\n"
        f"### Automated test\n\n{case['autotest']}\n"
    )


def gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        sys.exit(f"gh failed: gh {' '.join(args)}\n{result.stderr}")
    return result.stdout


def existing_ids() -> set[str]:
    """IDs of test-case issues that are already on GitHub, open or closed."""
    raw = gh(
        "issue",
        "list",
        "--label",
        LABEL,
        "--state",
        "all",
        "--limit",
        "500",
        "--json",
        "title",
    )
    titles = [issue["title"] for issue in json.loads(raw)]
    return {title[1 : title.index("]")] for title in titles if title.startswith("[")}


def create_issues(cases: list[dict]) -> None:
    gh("label", "create", LABEL, "--color", "0E8A16", "--force")
    already_there = existing_ids()
    for case in cases:
        if case["id"] in already_there:
            print(f"[{case['id']}] already exists, skipped")
            continue
        url = gh(
            "issue",
            "create",
            "--title",
            issue_title(case),
            "--body",
            issue_body(case),
            "--label",
            LABEL,
        )
        print(f"[{case['id']}] {url.strip()}")
        time.sleep(1)  # stay well below GitHub's rate limit


def write_markdown(cases: list[dict]) -> None:
    lines = [
        "# Test cases",
        "",
        "Generated from `tools/test_cases.json` by "
        "`python tools/create_test_case_issues.py --markdown`. Do not edit by hand.",
        "",
    ]
    for case in cases:
        lines += [
            f"## {case['id']}. {case['title']}",
            "",
            f"**Preconditions:** {case['preconditions']}",
            "",
            "**Steps:**",
            "",
            numbered(case["steps"]),
            "",
            f"**Expected result:** {case['expected']}",
            "",
            f"**Automated test:** `{case['autotest']}`",
            "",
        ]
    MARKDOWN_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written {MARKDOWN_FILE.relative_to(ROOT)} ({len(cases)} cases)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test cases → GitHub issues")
    parser.add_argument("--dry-run", action="store_true", help="show, create nothing")
    parser.add_argument(
        "--markdown", action="store_true", help="write docs/test-cases.md"
    )
    args = parser.parse_args()

    cases = load_cases()
    if args.markdown:
        write_markdown(cases)
    elif args.dry_run:
        for case in cases:
            print(f"=== {issue_title(case)}\n{issue_body(case)}")
        print(f"{len(cases)} issues would be created.")
    else:
        create_issues(cases)


if __name__ == "__main__":
    main()
