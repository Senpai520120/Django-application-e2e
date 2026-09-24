"""Path and name normalisation: the first line of defence against traversal."""

import pytest
from django.core.exceptions import SuspiciousFileOperation

from files.paths import (
    MAX_NAME_LENGTH,
    breadcrumbs,
    clean_name,
    join_path,
    normalize_path,
    parent_path,
)

TRAVERSAL_PATHS = [
    "../etc/passwd",
    "../../etc/passwd",
    "docs/../../etc/passwd",
    "docs/../..",
    "/etc/passwd",
    "//etc/passwd",
    "C:/Windows/System32",
    "c:\\Windows\\System32",
    "..\\..\\windows",
    "docs\\..\\..\\secret",
    "docs/\x00../etc",
]


@pytest.mark.parametrize("path", TRAVERSAL_PATHS)
def test_traversal_is_rejected(path):
    with pytest.raises(SuspiciousFileOperation):
        normalize_path(path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        (".", ""),
        ("./", ""),
        ("docs", "docs"),
        ("docs/", "docs"),
        ("/docs", None),  # checked separately below
    ],
)
def test_normalize_path_simple_cases(raw, expected):
    if expected is None:
        with pytest.raises(SuspiciousFileOperation):
            normalize_path(raw)
    else:
        assert normalize_path(raw) == expected


def test_normalize_path_keeps_nested_paths():
    assert normalize_path("docs/2024/отчёты") == "docs/2024/отчёты"
    assert normalize_path("docs//2024///q1") == "docs/2024/q1"
    assert normalize_path("docs\\2024") == "docs/2024"


BAD_NAMES = [
    "",
    "   ",
    ".",
    "..",
    "...",
    "a/b",
    "a\\b",
    "file\x00.txt",
    "con",
    "COM1.txt",
    'quote"name',
    "pipe|name",
    "star*name",
    "a" * (MAX_NAME_LENGTH + 1),
]


@pytest.mark.parametrize("name", BAD_NAMES)
def test_bad_names_are_rejected(name):
    with pytest.raises(SuspiciousFileOperation):
        clean_name(name)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("отчёт.pdf", "отчёт.pdf"),
        ("  spaced.txt  ", "spaced.txt"),
        ("trailing.dots...", "trailing.dots"),
        ("file name with spaces.txt", "file name with spaces.txt"),
    ],
)
def test_good_names_are_kept(raw, expected):
    assert clean_name(raw) == expected


def test_join_path_cleans_both_parts():
    assert join_path("docs", "отчёт.pdf") == "docs/отчёт.pdf"
    assert join_path("", "file.txt") == "file.txt"

    with pytest.raises(SuspiciousFileOperation):
        join_path("docs", "../escape.txt")

    with pytest.raises(SuspiciousFileOperation):
        join_path("../docs", "file.txt")


def test_parent_path():
    assert parent_path("docs/2024/file.txt") == "docs/2024"
    assert parent_path("docs") == ""
    assert parent_path("") == ""


def test_breadcrumbs_walk_from_root():
    assert breadcrumbs("") == []
    assert breadcrumbs("docs/2024/q1") == [
        ("docs", "docs"),
        ("2024", "docs/2024"),
        ("q1", "docs/2024/q1"),
    ]
