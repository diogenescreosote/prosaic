"""Ingest PDF attachments from an IMAP mailbox.

Gmail works over IMAP with an app password, which keeps the connector
free of provider-specific OAuth machinery. The session is a narrow
protocol matched by ``imaplib.IMAP4_SSL``, so the parsing and metadata
logic is tested against a fake session with real RFC 822 bytes while the
network layer stays one constructor call.
"""

from __future__ import annotations

import datetime
import email
import email.utils
import imaplib
from collections.abc import Iterator, Sequence
from typing import Protocol

from prosaic.ingest.source import FetchedDocument


class ImapSession(Protocol):
    """The slice of ``imaplib.IMAP4`` this connector uses.

    Return payloads are typed loosely because imaplib's responses are a
    zoo of bytes, tuples, and Nones; the connector narrows with
    isinstance checks at each use.
    """

    def select(self, mailbox: str, readonly: bool) -> tuple[str, Sequence[object]]: ...

    def uid(self, command: str, *args: str) -> tuple[str, Sequence[object]]: ...


class ImapFetchError(RuntimeError):
    """The server refused a select, search, or fetch."""


class ImapSource:
    """PDF attachments of messages matching an IMAP search."""

    def __init__(self, session: ImapSession, mailbox: str = "INBOX", search: str = "ALL") -> None:
        self.session = session
        self.mailbox = mailbox
        self.search = search

    @property
    def name(self) -> str:
        return "imap"

    def fetch(self) -> Iterator[FetchedDocument]:
        status, _ = self.session.select(self.mailbox, readonly=True)
        if status != "OK":
            raise ImapFetchError(f"cannot select mailbox {self.mailbox!r}: {status}")
        status, listing = self.session.uid("search", self.search)
        if status != "OK":
            raise ImapFetchError(f"search {self.search!r} failed in {self.mailbox!r}: {status}")
        first = listing[0] if listing else None
        uids = first.split() if isinstance(first, bytes) else []
        for uid in uids:
            yield from self._attachments(uid.decode())

    def _attachments(self, uid: str) -> Iterator[FetchedDocument]:
        status, payload = self.session.uid("fetch", uid, "(RFC822)")
        if status != "OK":
            raise ImapFetchError(f"fetch of uid {uid} failed: {status}")
        raw = next(
            (
                part[1]
                for part in payload
                if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes)
            ),
            None,
        )
        if raw is None:
            return
        message = email.message_from_bytes(raw)
        received = _message_date(message["Date"])
        for part in message.walk():
            if part.get_content_type() != "application/pdf":
                continue
            filename = part.get_filename() or f"attachment-{uid}.pdf"
            content = part.get_payload(decode=True)
            if not isinstance(content, bytes):
                continue
            yield FetchedDocument(
                origin=self.name,
                location=f"imap://{self.mailbox}/{uid}/{filename}",
                filename=filename,
                content=content,
                received=received,
            )


def _message_date(header: str | None) -> datetime.date | None:
    if header is None:
        return None
    try:
        return email.utils.parsedate_to_datetime(header).date()
    except ValueError:
        return None


def open_imap_source(
    host: str, username: str, password: str, mailbox: str = "INBOX", search: str = "ALL"
) -> ImapSource:
    """Connect over SSL and log in; Gmail accepts app passwords here."""
    session = imaplib.IMAP4_SSL(host)
    session.login(username, password)
    return ImapSource(session, mailbox=mailbox, search=search)
