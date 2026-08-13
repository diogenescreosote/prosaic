"""The DocuSeal client's promises, exercised against a local mock API.

No network, no account: a thread-local HTTP server plays the DocuSeal
API, and what is pinned is prosaic's side of the contract — the auth
header on every request, the exact payload shapes, the receipt
written beside the sent document, the status exit codes, and fetch
bringing back both the signed documents and the audit log. The same
client runs against cloud or self-hosted (ADR-0023) because only
DOCUSEAL_URL changes, which is exactly how the mock stands in here.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCUSEAL = REPO_ROOT / "docuseal-client" / "client.py"

PDF_BYTES = b"%PDF-1.4 fake test document"


class MockDocuSeal(BaseHTTPRequestHandler):
    """A minimal DocuSeal API double. Records every request.

    HTTP/1.1 with Content-Length on purpose: the official SDK touches
    conn.sock after reading the response, which a closing HTTP/1.0
    server sets to None — the mock must keep the real API's manners.
    """

    protocol_version = "HTTP/1.1"
    requests: ClassVar[list[dict[str, Any]]] = []
    submission_status = "completed"

    def _reply(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @property
    def route(self) -> str:
        # The SDK appends "?<query>" to every request path, empty
        # query included; compare on the bare route.
        return self.path.split("?", 1)[0]

    def _record(self, payload: object = None) -> None:
        type(self).requests.append(
            {
                "method": self.command,
                "path": self.route,
                "auth": self.headers.get("X-Auth-Token"),
                "payload": payload,
            }
        )

    def do_POST(self) -> None:  # the http.server API's casing
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or "{}")
        self._record(payload)
        if self.route == "/submissions/pdf":
            self._reply(
                [
                    {
                        "submission_id": 123,
                        "email": s.get("email"),
                        "role": s.get("role"),
                        "slug": f"slug{i}",
                        "status": "sent",
                    }
                    for i, s in enumerate(payload.get("submitters", []))
                ]
            )
        else:
            self._reply({"error": "unexpected"}, 404)

    def do_GET(self) -> None:  # the http.server API's casing
        self._record()
        base = f"http://{self.headers['Host']}"
        if self.route == "/submissions/123/documents":
            self._reply({"documents": [{"name": "signed.pdf", "url": f"{base}/files/signed.pdf"}]})
        elif self.route == "/submissions/123":
            self._reply(
                {
                    "id": 123,
                    "status": type(self).submission_status,
                    "submitters": [
                        {
                            "email": "jane@example.com",
                            "status": type(self).submission_status,
                            "completed_at": "2026-08-12T00:00:00Z",
                        }
                    ],
                    "documents": [{"name": "signed.pdf", "url": f"{base}/files/signed.pdf"}],
                    "audit_log_url": f"{base}/files/audit.pdf",
                }
            )
        elif self.route.startswith("/files/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", str(len(PDF_BYTES)))
            self.end_headers()
            self.wfile.write(PDF_BYTES)
        else:
            self._reply({"error": "unexpected"}, 404)

    def log_message(self, *args: object) -> None:  # quiet
        pass


@pytest.fixture
def mock_api() -> object:
    MockDocuSeal.requests = []
    MockDocuSeal.submission_status = "completed"
    server = HTTPServer(("127.0.0.1", 0), MockDocuSeal)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def run_docuseal(*args: str, url: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DOCUSEAL), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={
            "DOCUSEAL_URL": url,
            "DOCUSEAL_API_KEY": "test-key-123",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )


def test_send_posts_the_document_and_writes_a_receipt(mock_api: str, tmp_path: Path) -> None:
    pdf = tmp_path / "will.pdf"
    pdf.write_bytes(PDF_BYTES)
    proc = run_docuseal(
        "send", "will.pdf", "--to", "Jane Roe <jane@example.com>", url=mock_api, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr

    req = next(r for r in MockDocuSeal.requests if r["path"] == "/submissions/pdf")
    assert req["auth"] == "test-key-123"
    sent = base64.b64decode(req["payload"]["documents"][0]["file"])
    assert sent == PDF_BYTES, "the uploaded document must be byte-identical"
    submitter = req["payload"]["submitters"][0]
    assert submitter == {"name": "Jane Roe", "email": "jane@example.com", "role": "Signer"}
    assert req["payload"]["send_email"] is True

    receipt = json.loads((tmp_path / "will.pdf.docuseal.json").read_text())
    assert receipt["submission_id"] == 123
    assert receipt["submitters"][0]["email"] == "jane@example.com"


def test_signing_order_maps_to_numbered_roles(mock_api: str, tmp_path: Path) -> None:
    pdf = tmp_path / "trust.pdf"
    pdf.write_bytes(PDF_BYTES)
    proc = run_docuseal(
        "send",
        "trust.pdf",
        "--to",
        "Jane Roe <jane@example.com>",
        "--to",
        "notary@example.com",
        url=mock_api,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    req = next(r for r in MockDocuSeal.requests if r["path"] == "/submissions/pdf")
    roles = [s["role"] for s in req["payload"]["submitters"]]
    assert roles == ["Signer 1", "Signer 2"]


def test_status_exit_codes_distinguish_done_from_pending(mock_api: str, tmp_path: Path) -> None:
    assert run_docuseal("status", "123", url=mock_api, cwd=tmp_path).returncode == 0
    MockDocuSeal.submission_status = "pending"
    assert run_docuseal("status", "123", url=mock_api, cwd=tmp_path).returncode == 2


def test_fetch_brings_back_documents_and_audit_log(mock_api: str, tmp_path: Path) -> None:
    proc = run_docuseal("fetch", "123", "--out", "signed", url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "signed" / "signed.pdf").read_bytes() == PDF_BYTES
    assert (tmp_path / "signed" / "submission-123-audit-log.pdf").exists()


def test_fetch_refuses_an_incomplete_submission(mock_api: str, tmp_path: Path) -> None:
    MockDocuSeal.submission_status = "pending"
    proc = run_docuseal("fetch", "123", url=mock_api, cwd=tmp_path)
    assert proc.returncode == 2
    assert not list(tmp_path.iterdir()), "nothing may be written for a pending submission"


def test_missing_api_key_is_a_clear_error(tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(PDF_BYTES)
    proc = subprocess.run(
        [sys.executable, str(DOCUSEAL), "send", "doc.pdf", "--to", "x@example.com"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "DOCUSEAL_URL": "http://127.0.0.1:1"},
    )
    assert proc.returncode != 0
    # No env key: either the clear how-to-configure error, or -- on a
    # machine whose Keychain really holds a prosaic.docuseal entry --
    # the unreachable-API error from the sentinel URL. Both prove the
    # key was never defaulted silently.
    assert "DOCUSEAL_API_KEY" in proc.stderr or "unreachable" in proc.stderr


def test_send_refuses_a_draft_stamped_pdf(mock_api: str, tmp_path: Path) -> None:
    """The default-draft policy's outbound guard: a PDF whose metadata
    carries the prosaic draft key does not go into the world without
    --allow-draft."""
    from pypdf import PdfWriter

    pdf = tmp_path / "draft.pdf"
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    w.add_metadata({"/ProsaicDraftBanner": "DRAFT—NOT EXECUTED"})
    with pdf.open("wb") as fh:
        w.write(fh)

    proc = run_docuseal("send", "draft.pdf", "--to", "jane@example.com", url=mock_api, cwd=tmp_path)
    assert proc.returncode != 0
    assert "refusing to send a draft" in proc.stderr
    assert not (tmp_path / "draft.pdf.docuseal.json").exists()

    proc = run_docuseal(
        "send", "draft.pdf", "--to", "jane@example.com", "--allow-draft", url=mock_api, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr


def test_envelope_signers_roster(mock_api: str, tmp_path: Path) -> None:
    """The declarative path: signing roster from envelopes.yaml, in
    document order, instead of emails retyped from a conversation."""
    (tmp_path / "envelopes.yaml").write_text(
        "envelopes:\n"
        "  note:\n"
        "    sources: [note.md]\n"
        "    signers:\n"
        "      - name: Jane Roe\n"
        "        email: jane@example.com\n"
        "        note: Borrower\n"
        "      - name: Sue Smith\n"
        "        email: sue@example.com\n"
        "        note: Lender\n"
    )
    (tmp_path / "note.pdf").write_bytes(PDF_BYTES)
    proc = run_docuseal("send", "note.pdf", "--envelope", "note", url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    req = next(r for r in MockDocuSeal.requests if r["path"] == "/submissions/pdf")
    subs = req["payload"]["submitters"]
    assert [s["email"] for s in subs] == ["jane@example.com", "sue@example.com"]
    assert [s["role"] for s in subs] == ["Signer 1", "Signer 2"]


def test_envelope_and_to_are_mutually_exclusive(mock_api: str, tmp_path: Path) -> None:
    (tmp_path / "note.pdf").write_bytes(PDF_BYTES)
    proc = run_docuseal(
        "send",
        "note.pdf",
        "--envelope",
        "note",
        "--to",
        "x@example.com",
        url=mock_api,
        cwd=tmp_path,
    )
    assert proc.returncode != 0
    assert "not both" in proc.stderr


def test_signer_count_must_match_the_documents_tags(mock_api: str, tmp_path: Path) -> None:
    """A two-signer instrument sent to one signer is a defective
    ceremony waiting to happen; the embedded tags know the truth."""
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "two.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 700, "{{Signature 1;role=Signer 1;type=signature}}")
    c.drawString(72, 650, "{{Signature 2;role=Signer 2;type=signature}}")
    c.save()

    proc = run_docuseal("send", "two.pdf", "--to", "only@example.com", url=mock_api, cwd=tmp_path)
    assert proc.returncode != 0
    assert "signer mismatch" in proc.stderr
    assert "expect 2" in proc.stderr


def test_poll_fetches_completed_and_skips_done(mock_api: str, tmp_path: Path) -> None:
    """The connector engine: a pending receipt whose submission
    completed gets its documents pulled into inbox/docuseal/ with NEW
    lines for triage, and the receipt is marked so it never polls
    again; an already-completed receipt is not touched."""
    (tmp_path / "out" / "note").mkdir(parents=True)
    receipt = tmp_path / "out" / "note" / "note.pdf.docuseal.json"
    receipt.write_text(json.dumps({"submission_id": 123, "document": "note.pdf"}))
    done = tmp_path / "out" / "note" / "old.pdf.docuseal.json"
    done.write_text(json.dumps({"submission_id": 999, "completed": True}))

    proc = run_docuseal("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    new_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("NEW ")]
    assert len(new_lines) == 2, proc.stdout  # signed.pdf + audit log
    fetched = tmp_path / "inbox" / "docuseal" / "123"
    assert (fetched / "signed.pdf").read_bytes() == PDF_BYTES
    assert (fetched / "submission-123-audit-log.pdf").exists()
    updated = json.loads(receipt.read_text())
    assert updated["completed"] is True
    assert len(updated["fetched"]) == 2
    # 999 was never queried: only /submissions/123 traffic
    assert not any("/999" in r["path"] for r in MockDocuSeal.requests)


def test_poll_leaves_pending_submissions_alone(mock_api: str, tmp_path: Path) -> None:
    MockDocuSeal.submission_status = "pending"
    receipt = tmp_path / "doc.pdf.docuseal.json"
    receipt.write_text(json.dumps({"submission_id": 123}))
    proc = run_docuseal("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "NEW " not in proc.stdout
    assert not (tmp_path / "inbox").exists()
    updated = json.loads(receipt.read_text())
    assert updated.get("completed") is not True
    assert updated["last_status"] == "pending"


def test_poll_marks_declined_terminal_and_stops(mock_api: str, tmp_path: Path) -> None:
    """DocuSeal's lifecycle is pending/completed/declined/expired: a
    declined ceremony is a fact, not a retry."""
    MockDocuSeal.submission_status = "declined"
    receipt = tmp_path / "doc.pdf.docuseal.json"
    receipt.write_text(json.dumps({"submission_id": 123}))
    proc = run_docuseal("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "DECLINED" in proc.stderr
    updated = json.loads(receipt.read_text())
    assert updated["terminal"] == "declined"

    MockDocuSeal.requests.clear()
    proc = run_docuseal("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0
    assert not MockDocuSeal.requests, "terminal receipts are never re-polled"


def _security_shim(tmp_path: Path, ref: str, key: str) -> str:
    """A fake `security` on PATH: answers the Keychain lookup for one
    service name, so tests exercise credential-by-reference without a
    real Keychain."""
    shim_dir = tmp_path / "shim-bin"
    shim_dir.mkdir()
    shim = shim_dir / "security"
    shim.write_text(f'#!/bin/sh\nif [ "$3" = "{ref}" ]; then echo {key}; exit 0; fi\nexit 1\n')
    shim.chmod(0o755)
    return str(shim_dir)


def test_matter_credential_is_incorporated_by_reference(mock_api: str, tmp_path: Path) -> None:
    """Inside a matter, the key binding lives in matter.yaml as a
    Keychain reference (ADR-0031): the client resolves the named
    item, and the material never appears in the matter."""
    (tmp_path / "matter.yaml").write_text(
        "connectors:\n  docuseal:\n    credential: docuseal.test-matter\n"
    )
    proc = subprocess.run(
        [sys.executable, str(DOCUSEAL), "status", "123"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "DOCUSEAL_URL": mock_api,
            "PATH": _security_shim(tmp_path, "docuseal.test-matter", "matter-scoped-key")
            + ":/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert any(r["auth"] == "matter-scoped-key" for r in MockDocuSeal.requests)


def test_matter_without_credential_reference_refuses(tmp_path: Path) -> None:
    """A matter that declares the connector but names no credential
    gets a refusal telling it what to add — a global key is fine, but
    only incorporated by reference, never assumed."""
    (tmp_path / "matter.yaml").write_text("connectors:\n  docuseal: {}\n")
    proc = subprocess.run(
        [sys.executable, str(DOCUSEAL), "status", "123"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"DOCUSEAL_URL": "http://127.0.0.1:1", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode != 0
    assert "credential" in proc.stderr and "ADR-0031" in proc.stderr


def test_signing_base_hosted_vs_self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Signer links: hosted API (api.docuseal.com) signs on
    docuseal.com; a self-hosted instance strips only a trailing /api
    — never the 'api.' subdomain (the first live test-mode run
    caught exactly that mangling)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("docuseal_client", DOCUSEAL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    monkeypatch.delenv("DOCUSEAL_SERVER", raising=False)
    monkeypatch.setenv("DOCUSEAL_URL", "https://api.docuseal.com")
    assert mod.signing_base() == "https://docuseal.com"
    monkeypatch.setenv("DOCUSEAL_URL", "https://sign.example.com/api")
    assert mod.signing_base() == "https://sign.example.com"
