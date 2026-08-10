"""Connectors and intake: filesystem, IMAP against a fake session, dedup."""

from __future__ import annotations

import datetime
import io
from email.message import EmailMessage
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from prosaic.ingest import (
    FilesystemSource,
    ImapFetchError,
    ImapSource,
    ingest,
    normalize,
)
from prosaic.ingest.source import FetchedDocument
from prosaic.model import DocumentKind
from tests.synthetic import doe_v_roe


def _pdf(pages: int) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    for _ in range(pages):
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def test_filesystem_source_walks_recursively(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "order.pdf").write_bytes(_pdf(2))
    (tmp_path / "nested" / "answer.pdf").write_bytes(_pdf(1))
    (tmp_path / "notes.txt").write_text("not matched")

    fetched = list(FilesystemSource(tmp_path).fetch())
    assert [item.filename for item in fetched] == ["answer.pdf", "order.pdf"]
    assert all(item.origin == "filesystem" for item in fetched)
    assert all(item.received is not None for item in fetched)


def test_filesystem_source_requires_a_directory(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        FilesystemSource(tmp_path / "missing")


def test_normalize_hashes_and_counts_pages() -> None:
    content = _pdf(3)
    document = normalize(
        FetchedDocument(
            origin="filesystem",
            location="records/order.pdf",
            filename="order.pdf",
            content=content,
            received=datetime.date(2026, 3, 1),
        )
    )
    assert document.page_count == 3
    assert document.kind is DocumentKind.OTHER
    assert document.id == f"doc-{document.sha256[:12]}"


def test_normalize_treats_non_pdf_bytes_as_one_page() -> None:
    document = normalize(
        FetchedDocument(
            origin="filesystem",
            location="records/photo.pdf",
            filename="photo.pdf",
            content=b"not a pdf at all",
            received=None,
        )
    )
    assert document.page_count == 1


def test_ingest_deduplicates_by_content_hash() -> None:
    matter = doe_v_roe()
    content = _pdf(1)
    copies = [
        FetchedDocument(
            origin="filesystem",
            location=f"records/copy{n}.pdf",
            filename=f"copy{n}.pdf",
            content=content,
            received=None,
        )
        for n in (1, 2)
    ]
    updated, added = ingest(matter, copies)
    assert len(added) == 1
    assert len(updated.documents) == len(matter.documents) + 1

    again, added_again = ingest(updated, copies)
    assert added_again == []
    assert again is updated


class FakeImapSession:
    """Canned responses shaped like imaplib's."""

    def __init__(self, messages: dict[str, bytes]) -> None:
        self.messages = messages

    def select(self, mailbox: str, readonly: bool) -> tuple[str, list[bytes | None]]:
        if mailbox == "Broken":
            return "NO", [None]
        assert readonly
        return "OK", [str(len(self.messages)).encode()]

    def uid(self, command: str, *args: str) -> tuple[str, list[bytes | tuple[bytes, bytes] | None]]:
        if command == "search":
            return "OK", [b" ".join(uid.encode() for uid in self.messages)]
        uid = args[0]
        return "OK", [(f"{uid} (RFC822)".encode(), self.messages[uid]), b")"]


def _message_with_pdf(filename: str, content: bytes) -> bytes:
    message = EmailMessage()
    message["From"] = "clerk@example.org"
    message["Date"] = "Mon, 2 Mar 2026 10:15:00 -0800"
    message["Subject"] = "Conformed copies"
    message.set_content("Attached.")
    message.add_attachment(content, maintype="application", subtype="pdf", filename=filename)
    return bytes(message)


def test_imap_source_yields_pdf_attachments_with_message_dates() -> None:
    source = ImapSource(FakeImapSession({"7": _message_with_pdf("minute-order.pdf", _pdf(2))}))
    fetched = list(source.fetch())
    assert len(fetched) == 1
    assert fetched[0].filename == "minute-order.pdf"
    assert fetched[0].location == "imap://INBOX/7/minute-order.pdf"
    assert fetched[0].received == datetime.date(2026, 3, 2)
    assert normalize(fetched[0]).page_count == 2


def test_imap_source_skips_messages_without_pdfs() -> None:
    message = EmailMessage()
    message["Date"] = "Mon, 2 Mar 2026 10:15:00 -0800"
    message.set_content("No attachment here.")
    source = ImapSource(FakeImapSession({"9": bytes(message)}))
    assert list(source.fetch()) == []


def test_imap_source_raises_on_refused_mailbox() -> None:
    source = ImapSource(FakeImapSession({}), mailbox="Broken")
    with pytest.raises(ImapFetchError, match="Broken"):
        list(source.fetch())
