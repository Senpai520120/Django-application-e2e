"""One storage interface for the file manager.

The views talk to this interface only and never learn where the files live.
The implementations sit on top of the stock `django.core.files.storage`:
`FileSystemStorage` locally, `S3Boto3Storage` from django-storages in
production. Adding a third backend means writing one more subclass and
returning it from `get_storage()`; templates and views stay untouched.
"""

from __future__ import annotations

import posixpath
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.utils import timezone

from files.paths import normalize_path

#: An empty folder in S3 is a zero-length object whose key ends with "/".
S3_DIR_MARKER_SUFFIX = "/"

#: How many keys S3 removes in a single delete_objects request.
S3_DELETE_BATCH = 1000


@dataclass(frozen=True)
class Entry:
    """One listing row: a file or a folder."""

    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified: datetime | None = None

    @property
    def sort_key(self) -> tuple[bool, str]:
        return (not self.is_dir, self.name.lower())


class StorageError(Exception):
    """An error safe to show to the user (its text reaches the UI)."""


class FileManagerStorage(ABC):
    """The storage contract. Both implementations must behave identically."""

    @abstractmethod
    def list_dir(self, path: str = "") -> list[Entry]:
        """Folder contents, sorted with folders first and files after."""

    @abstractmethod
    def make_dir(self, path: str) -> None:
        """Create a folder. Raises StorageError if it already exists."""

    @abstractmethod
    def save(self, path: str, file) -> str:
        """Write a file. Raises StorageError if one already exists."""

    @abstractmethod
    def open(self, path: str):
        """Open a file for reading."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete a file or a folder (folders are removed recursively)."""

    @abstractmethod
    def rename(self, path: str, new_name: str) -> str:
        """Rename a file or folder inside the same parent folder."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Whether a file or folder exists at this path."""

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """Whether the path is a folder."""

    @abstractmethod
    def size(self, path: str) -> int:
        """File size in bytes."""

    @abstractmethod
    def total_size(self) -> int:
        """Total size of the storage, used for the overall size limit."""


class LocalFileStorage(FileManagerStorage):
    """Files physically live on the server disk."""

    def __init__(self, location: str | Path):
        self._root = Path(location).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._storage = FileSystemStorage(location=str(self._root))

    def _absolute(self, path: str) -> Path:
        """Absolute path, checked to stay inside the root.

        `normalize_path` rejects `..` lexically, but a symlink can still lead
        outside once the path is resolved, so the result is checked too.
        """
        relative = normalize_path(path)
        target = (self._root / relative).resolve()
        if target != self._root and self._root not in target.parents:
            raise SuspiciousFileOperation("The path leaves the storage root.")
        return target

    def list_dir(self, path: str = "") -> list[Entry]:
        base = self._absolute(path)
        if not base.is_dir():
            raise StorageError("Folder not found.")

        relative = normalize_path(path)
        entries = []
        for child in base.iterdir():
            stat = child.stat()
            is_dir = child.is_dir()
            entries.append(
                Entry(
                    name=child.name,
                    path=(
                        posixpath.join(relative, child.name) if relative else child.name
                    ),
                    is_dir=is_dir,
                    size=None if is_dir else stat.st_size,
                    modified=(
                        timezone.make_aware(
                            datetime.fromtimestamp(stat.st_mtime),
                            timezone.get_default_timezone(),
                        )
                        if settings.USE_TZ
                        else datetime.fromtimestamp(stat.st_mtime)
                    ),
                )
            )
        return sorted(entries, key=lambda entry: entry.sort_key)

    def make_dir(self, path: str) -> None:
        target = self._absolute(path)
        if target.exists():
            raise StorageError("A folder or file with this name already exists.")
        target.mkdir(parents=True)

    def save(self, path: str, file) -> str:
        relative = normalize_path(path)
        if self.exists(relative):
            raise StorageError("A file with this name already exists.")
        return self._storage.save(relative, file)

    def open(self, path: str):
        target = self._absolute(path)
        if not target.is_file():
            raise StorageError("File not found.")
        return self._storage.open(normalize_path(path), "rb")

    def delete(self, path: str) -> None:
        relative = normalize_path(path)
        if not relative:
            raise StorageError("The root folder cannot be deleted.")

        target = self._absolute(relative)
        if not target.exists():
            raise StorageError("File or folder not found.")

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def rename(self, path: str, new_name: str) -> str:
        from files.paths import clean_name, parent_path

        relative = normalize_path(path)
        if not relative:
            raise StorageError("The root folder cannot be renamed.")

        source = self._absolute(relative)
        if not source.exists():
            raise StorageError("File or folder not found.")

        parent = parent_path(relative)
        new_relative = (
            posixpath.join(parent, clean_name(new_name))
            if parent
            else clean_name(new_name)
        )
        destination = self._absolute(new_relative)
        if destination.exists():
            raise StorageError("A file or folder with this name already exists.")

        source.rename(destination)
        return new_relative

    def exists(self, path: str) -> bool:
        return self._absolute(path).exists()

    def is_dir(self, path: str) -> bool:
        return self._absolute(path).is_dir()

    def size(self, path: str) -> int:
        target = self._absolute(path)
        if not target.is_file():
            raise StorageError("File not found.")
        return target.stat().st_size

    def total_size(self) -> int:
        return sum(f.stat().st_size for f in self._root.rglob("*") if f.is_file())


class S3FileStorage(FileManagerStorage):
    """Files live in S3. Folders are virtual: they are key prefixes."""

    def __init__(self, location: str = ""):
        from storages.backends.s3 import S3Storage

        self._location = location.strip("/")
        self._storage = S3Storage(location=self._location)

    @property
    def _bucket(self) -> str:
        return self._storage.bucket_name

    @property
    def _client(self):
        return self._storage.connection.meta.client

    def _key(self, path: str) -> str:
        """Full object key: the storage prefix plus the relative path."""
        relative = normalize_path(path)
        if self._location and relative:
            return f"{self._location}/{relative}"
        return self._location or relative

    def _dir_prefix(self, path: str) -> str:
        key = self._key(path)
        return f"{key}{S3_DIR_MARKER_SUFFIX}" if key else ""

    def _iter_keys(self, prefix: str):
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            yield from page.get("Contents", ())

    def list_dir(self, path: str = "") -> list[Entry]:
        prefix = self._dir_prefix(path)
        relative = normalize_path(path)

        if relative and not self.is_dir(relative):
            raise StorageError("Folder not found.")

        entries: list[Entry] = []
        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/")

        for page in pages:
            for common in page.get("CommonPrefixes", ()):
                name = common["Prefix"][len(prefix) :].rstrip("/")
                if not name:
                    continue
                entries.append(
                    Entry(
                        name=name,
                        path=posixpath.join(relative, name) if relative else name,
                        is_dir=True,
                    )
                )
            for obj in page.get("Contents", ()):
                name = obj["Key"][len(prefix) :]
                if not name:  # the folder marker itself
                    continue
                entries.append(
                    Entry(
                        name=name,
                        path=posixpath.join(relative, name) if relative else name,
                        is_dir=False,
                        size=obj["Size"],
                        modified=obj["LastModified"],
                    )
                )

        return sorted(entries, key=lambda entry: entry.sort_key)

    def make_dir(self, path: str) -> None:
        relative = normalize_path(path)
        if not relative:
            raise StorageError("Empty folder name.")
        if self.exists(relative):
            raise StorageError("A folder or file with this name already exists.")
        self._client.put_object(
            Bucket=self._bucket, Key=self._dir_prefix(relative), Body=b""
        )

    def save(self, path: str, file) -> str:
        relative = normalize_path(path)
        if self.exists(relative):
            raise StorageError("A file with this name already exists.")
        return self._storage.save(relative, file)

    def open(self, path: str):
        relative = normalize_path(path)
        if not self._file_exists(relative):
            raise StorageError("File not found.")
        return self._storage.open(relative, "rb")

    def delete(self, path: str) -> None:
        relative = normalize_path(path)
        if not relative:
            raise StorageError("The root folder cannot be deleted.")

        if self._file_exists(relative):
            self._storage.delete(relative)
            return

        if not self.is_dir(relative):
            raise StorageError("File or folder not found.")

        self._delete_prefix(self._dir_prefix(relative))

    def _delete_prefix(self, prefix: str) -> None:
        batch: list[dict[str, str]] = []
        for obj in self._iter_keys(prefix):
            batch.append({"Key": obj["Key"]})
            if len(batch) == S3_DELETE_BATCH:
                self._client.delete_objects(
                    Bucket=self._bucket, Delete={"Objects": batch}
                )
                batch = []
        if batch:
            self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": batch})

    def rename(self, path: str, new_name: str) -> str:
        from files.paths import clean_name, parent_path

        relative = normalize_path(path)
        if not relative:
            raise StorageError("The root folder cannot be renamed.")

        parent = parent_path(relative)
        cleaned = clean_name(new_name)
        new_relative = posixpath.join(parent, cleaned) if parent else cleaned

        if self.exists(new_relative):
            raise StorageError("A file or folder with this name already exists.")

        if self._file_exists(relative):
            self._copy(self._key(relative), self._key(new_relative))
            self._storage.delete(relative)
            return new_relative

        if not self.is_dir(relative):
            raise StorageError("File or folder not found.")

        old_prefix = self._dir_prefix(relative)
        new_prefix = self._dir_prefix(new_relative)
        keys = [obj["Key"] for obj in self._iter_keys(old_prefix)]
        for key in keys:
            self._copy(key, f"{new_prefix}{key[len(old_prefix) :]}")
        self._delete_prefix(old_prefix)
        return new_relative

    def _copy(self, source_key: str, target_key: str) -> None:
        self._client.copy_object(
            Bucket=self._bucket,
            CopySource={"Bucket": self._bucket, "Key": source_key},
            Key=target_key,
        )

    def _file_exists(self, path: str) -> bool:
        relative = normalize_path(path)
        return bool(relative) and self._storage.exists(relative)

    def exists(self, path: str) -> bool:
        relative = normalize_path(path)
        if not relative:
            return True
        return self._file_exists(relative) or self.is_dir(relative)

    def is_dir(self, path: str) -> bool:
        relative = normalize_path(path)
        if not relative:
            return True
        response = self._client.list_objects_v2(
            Bucket=self._bucket, Prefix=self._dir_prefix(relative), MaxKeys=1
        )
        return response.get("KeyCount", 0) > 0

    def size(self, path: str) -> int:
        relative = normalize_path(path)
        if not self._file_exists(relative):
            raise StorageError("File not found.")
        return self._storage.size(relative)

    def total_size(self) -> int:
        prefix = f"{self._location}/" if self._location else ""
        return sum(obj["Size"] for obj in self._iter_keys(prefix))


def get_storage() -> FileManagerStorage:
    """The storage chosen by settings. The only place a backend is picked."""
    backend = settings.FILE_MANAGER["BACKEND"]

    if backend == "local":
        return LocalFileStorage(settings.FILE_MANAGER["ROOT"])
    if backend == "s3":
        return S3FileStorage(location=settings.FILE_MANAGER["S3_LOCATION"])

    raise ImproperlyConfigured(
        f"Unknown file manager backend: {backend!r}. "
        "Allowed values of FILE_STORAGE_BACKEND: local, s3."
    )
