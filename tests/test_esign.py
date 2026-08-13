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
DOCUSEAL = REPO_ROOT / "esign" / "client.py"

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


def run_esign(*args: str, url: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DOCUSEAL), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={"DOCUSEAL_URL": url, "DOCUSEAL_API_KEY": "test-key-123", "PATH": "/usr/bin:/bin"},
    )


def test_send_posts_the_document_and_writes_a_receipt(mock_api: str, tmp_path: Path) -> None:
    pdf = tmp_path / "will.pdf"
    pdf.write_bytes(PDF_BYTES)
    proc = run_esign(
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

    receipt = json.loads((tmp_path / "will.pdf.esign.json").read_text())
    assert receipt["submission_id"] == 123
    assert receipt["submitters"][0]["email"] == "jane@example.com"


def test_signing_order_maps_to_numbered_roles(mock_api: str, tmp_path: Path) -> None:
    pdf = tmp_path / "trust.pdf"
    pdf.write_bytes(PDF_BYTES)
    proc = run_esign(
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
    assert run_esign("status", "123", url=mock_api, cwd=tmp_path).returncode == 0
    MockDocuSeal.submission_status = "pending"
    assert run_esign("status", "123", url=mock_api, cwd=tmp_path).returncode == 2


def test_fetch_brings_back_documents_and_audit_log(mock_api: str, tmp_path: Path) -> None:
    proc = run_esign("fetch", "123", "--out", "signed", url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "signed" / "signed.pdf").read_bytes() == PDF_BYTES
    assert (tmp_path / "signed" / "submission-123-audit-log.pdf").exists()


def test_fetch_refuses_an_incomplete_submission(mock_api: str, tmp_path: Path) -> None:
    MockDocuSeal.submission_status = "pending"
    proc = run_esign("fetch", "123", url=mock_api, cwd=tmp_path)
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
