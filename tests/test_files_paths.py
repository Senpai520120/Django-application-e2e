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
    # Stays inside the root once normalised, but ".." is refused on sight.
    "docs/../other",
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
    # Shown as "photoexe.jpg": the right-to-left override hides the extension.
    "photo" + chr(0x202E) + "gpj.exe",
    "zero" + chr(0x200B) + "width.txt",
    "del\x7f.txt",
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


# The reason reaches the user as a form error, so it has to be the right one.
REJECTION_REASONS = [
    (clean_name, 42, "The name must be a string."),
    (clean_name, "a\x00b", "The name contains a null byte."),
    (clean_name, "   ", "Empty name."),
    (clean_name, "a:b", "The name contains forbidden characters."),
    (
        clean_name,
        "photo" + chr(0x202E) + "gpj.exe",
        "The name contains invisible characters.",
    ),
    (clean_name, "..", "Name is not allowed."),
    (clean_name, ". .", "Name is not allowed."),
    (clean_name, "nul.tar.gz", "The name 'nul.tar.gz' is reserved by the system."),
    (
        clean_name,
        "a" * (MAX_NAME_LENGTH + 1),
        f"The name is longer than {MAX_NAME_LENGTH} characters.",
    ),
    (normalize_path, 42, "The path must be a string."),
    (normalize_path, "docs/\x00", "The path contains a null byte."),
    (normalize_path, "/etc", "Absolute paths are not allowed."),
    (normalize_path, "docs/../..", "Escaping the storage root is forbidden."),
]


@pytest.mark.parametrize(("check", "value", "reason"), REJECTION_REASONS)
def test_rejection_says_why(check, value, reason):
    with pytest.raises(SuspiciousFileOperation) as caught:
        check(value)
    assert str(caught.value) == reason


def test_name_of_exactly_the_maximum_length_is_kept():
    name = "a" * MAX_NAME_LENGTH
    assert clean_name(name) == name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Only dots and spaces are trimmed from the ends, nothing else.
        ("XML report.", "XML report"),
        ("console.log", "console.log"),  # starts like CON, but is not CON
        ("con-notes.txt", "con-notes.txt"),
    ],
)
def test_trimming_and_reserved_names_stop_where_they_should(raw, expected):
    assert clean_name(raw) == expected


@pytest.mark.parametrize(
    "name",
    [
        "COM1",
        "com9.txt",
        "LPT9.log",
        *("COM" + chr(code) for code in (0xB9, 0xB2, 0xB3)),
        *("lpt" + chr(code) + ".txt" for code in (0xB9, 0xB2, 0xB3)),
    ],
)
def test_every_windows_device_name_is_reserved(name):
    with pytest.raises(SuspiciousFileOperation, match="reserved by the system"):
        clean_name(name)


@pytest.mark.parametrize("name", ["COM0.txt", "COM10.txt", "LPT0", "LPT10.log"])
def test_device_names_stop_at_nine(name):
    assert clean_name(name) == name


def test_names_are_limited_to_120_characters():
    # The limit itself, not only the constant: a changed constant shows here.
    assert clean_name("a" * 120) == "a" * 120
    with pytest.raises(SuspiciousFileOperation):
        clean_name("a" * 121)


def test_a_part_that_sorts_before_dots_is_kept():
    # "-" sorts before "." and ".."; only ".." itself is refused.
    assert normalize_path("-docs/a") == "-docs/a"
