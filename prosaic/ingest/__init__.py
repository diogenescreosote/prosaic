"""Connectors and intake.

Implemented sources: a local filesystem directory, and IMAP mailboxes
(which covers Gmail via app passwords). Both yield ``FetchedDocument``s
through the same protocol; ``ingest`` hashes, deduplicates, and adds them
to a matter.
"""

from prosaic.ingest.filesystem import FilesystemSource
from prosaic.ingest.imap import ImapFetchError, ImapSession, ImapSource, open_imap_source
from prosaic.ingest.intake import ingest, normalize
from prosaic.ingest.source import FetchedDocument, RecordSource

__all__ = [
    "FetchedDocument",
    "FilesystemSource",
    "ImapFetchError",
    "ImapSession",
    "ImapSource",
    "RecordSource",
    "ingest",
    "normalize",
    "open_imap_source",
]
