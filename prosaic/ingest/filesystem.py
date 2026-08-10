"""Ingest documents from a local directory."""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from pathlib import Path

from prosaic.ingest.source import FetchedDocument


class FilesystemSource:
    """Documents matching a glob under one directory, recursively.

    The received date is the file's modification time: the best available
    signal for when a copy landed on disk, and often wrong for scans of
    older documents — which is why ``received`` stays a plain fact the
    operator can correct rather than something trusted downstream.
    """

    def __init__(self, root: Path, pattern: str = "*.pdf") -> None:
        if not root.is_dir():
            raise NotADirectoryError(f"filesystem source root {root} is not a directory")
        self.root = root
        self.pattern = pattern

    @property
    def name(self) -> str:
        return "filesystem"

    def fetch(self) -> Iterator[FetchedDocument]:
        for path in sorted(self.root.rglob(self.pattern)):
            if not path.is_file():
                continue
            modified = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=datetime.UTC)
            yield FetchedDocument(
                origin=self.name,
                location=str(path),
                filename=path.name,
                content=path.read_bytes(),
                received=modified.date(),
            )
