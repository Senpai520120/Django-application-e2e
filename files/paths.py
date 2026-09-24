"""Path and name normalisation for the file manager.

The single place that decides what a user is allowed to address. Anything that
leads outside the storage root is rejected here, not in the views.
"""

import posixpath
import re

from django.core.exceptions import SuspiciousFileOperation

MAX_NAME_LENGTH = 120

# Separators, control characters, and whatever breaks Windows paths.
_FORBIDDEN_IN_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_DRIVE_LETTER = re.compile(r"^[a-zA-Z]:")


def clean_name(name: str) -> str:
    """One file or folder name, safe to write into the storage.

    Rejects path separators, control characters, leading and trailing dots,
    names reserved by Windows, and names that are simply too long.
    """
    if not isinstance(name, str):
        raise SuspiciousFileOperation("The name must be a string.")

    # A null byte is rejected rather than stripped: otherwise
    # file\x00.exe would quietly become file.exe.
    if "\x00" in name:
        raise SuspiciousFileOperation("The name contains a null byte.")

    name = name.strip()
    if not name:
        raise SuspiciousFileOperation("Empty name.")

    if _FORBIDDEN_IN_NAME.search(name):
        raise SuspiciousFileOperation("The name contains forbidden characters.")

    # ".", ".." and leading dots: either a way out or invisible clutter.
    if name.strip(".") == "":
        raise SuspiciousFileOperation("Name is not allowed.")

    name = name.strip(". ")
    if not name:
        raise SuspiciousFileOperation("Name is not allowed.")

    stem = name.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise SuspiciousFileOperation(f"The name {name!r} is reserved by the system.")

    if len(name) > MAX_NAME_LENGTH:
        raise SuspiciousFileOperation(
            f"The name is longer than {MAX_NAME_LENGTH} characters."
        )

    return name


def normalize_path(path: str | None) -> str:
    """A relative path inside the storage root.

    Returns a posix-style path with no leading slash: "", "docs", "docs/2024".
    Absolute paths, drive letters, `..` and null bytes are treated as an attack.
    """
    if not path:
        return ""

    if not isinstance(path, str):
        raise SuspiciousFileOperation("The path must be a string.")

    if "\x00" in path:
        raise SuspiciousFileOperation("The path contains a null byte.")

    # The user may come from a Windows client, so normalise the separators.
    path = path.replace("\\", "/").strip()

    if path.startswith("/") or _DRIVE_LETTER.match(path):
        raise SuspiciousFileOperation("Absolute paths are not allowed.")

    parts: list[str] = []
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise SuspiciousFileOperation("Escaping the storage root is forbidden.")
        parts.append(part)

    normalized = posixpath.normpath("/".join(parts)) if parts else ""
    if normalized in (".", "/"):
        return ""

    # normpath should not have unwound anything, but check the result as well.
    if normalized.startswith(("..", "/")):
        raise SuspiciousFileOperation("Escaping the storage root is forbidden.")

    return normalized


def join_path(path: str, name: str) -> str:
    """Path to a nested item: clean the name first, then join."""
    parent = normalize_path(path)
    child = clean_name(name)
    return posixpath.join(parent, child) if parent else child


def parent_path(path: str) -> str:
    """Parent folder of a path. For the root it is the root again."""
    normalized = normalize_path(path)
    if not normalized:
        return ""
    return posixpath.dirname(normalized)


def breadcrumbs(path: str) -> list[tuple[str, str]]:
    """(folder name, path) pairs for navigating from the root to the current folder."""
    normalized = normalize_path(path)
    if not normalized:
        return []

    crumbs: list[tuple[str, str]] = []
    walked = ""
    for part in normalized.split("/"):
        walked = posixpath.join(walked, part) if walked else part
        crumbs.append((part, walked))
    return crumbs
