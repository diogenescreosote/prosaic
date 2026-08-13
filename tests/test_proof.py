"""The Proof (RON) client's promises, against a local mock of the
Business API surface we use.

Same discipline as the DocuSeal tests, deliberately NOT the same
code: the two services stay separate implementations (their
protocols differ — detailed_status lifecycles, base64-resource
documents, pre-signed final_document_url delivery), and each mock
pins its own client's payloads. The Proof client has not yet run
against a live account; these tests pin our side of the documented
contract until a fairfax-sandbox run confirms the rest.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT = REPO_ROOT / "proof-client" / "client.py"

PDF_BYTES = b"%PDF-1.4 fake instrument"


class MockProof(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: ClassVar[list[dict[str, Any]]] = []
    detailed_status = "complete"

    @property
    def route(self) -> str:
        return self.path.split("?", 1)[0]

    def _reply(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, payload: object = None) -> None:
        type(self).requests.append(
            {
                "method": self.command,
                "path": self.route,
                "auth": self.headers.get("ApiKey"),
                "payload": payload,
            }
        )

    def do_POST(self) -> None:  # the http.server API's casing
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or "{}")
        self._record(payload)
        if self.route == "/v1/transactions":
            self._reply(
                {
                    "id": "tx_777",
                    "detailed_status": "sent_to_signer",
                    "signer_info": [
                        {
                            "email": s.get("email"),
                            "transaction_access_link": f"https://mock/s/{i}",
                        }
                        for i, s in enumerate(payload.get("signers", []))
                    ],
                }
            )
        else:
            self._reply({"error": "unexpected"}, 404)

    def do_GET(self) -> None:  # the http.server API's casing
        self._record()
        base = f"http://{self.headers['Host']}"
        if self.route == "/v1/transactions/tx_777":
            self._reply(
                {
                    "id": "tx_777",
                    "detailed_status": type(self).detailed_status,
                    "documents": [
                        {
                            "document_name": "notarized.pdf",
                            "final_document_url": f"{base}/files/notarized.pdf",
                        }
                    ],
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

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def mock_api() -> object:
    MockProof.requests = []
    MockProof.detailed_status = "complete"
    server = HTTPServer(("127.0.0.1", 0), MockProof)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def run_proof(*args: str, url: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLIENT), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={
            "PROOF_URL": url,
            "PROOF_API_KEY": "proof-key-1",
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )


def test_send_creates_a_notarization_transaction(mock_api: str, tmp_path: Path) -> None:
    pdf = tmp_path / "trust.pdf"
    pdf.write_bytes(PDF_BYTES)
    proc = run_proof(
        "send", "trust.pdf", "--to", "Jane Roe <jane@example.com>", url=mock_api, cwd=tmp_path
    )
    assert proc.returncode == 0, proc.stderr

    req = next(r for r in MockProof.requests if r["path"] == "/v1/transactions")
    assert req["auth"] == "proof-key-1"
    doc = req["payload"]["documents"][0]
    assert doc["requirement"] == "notarization"
    import base64

    assert base64.b64decode(doc["resource"]) == PDF_BYTES
    signer = req["payload"]["signers"][0]
    assert signer == {"email": "jane@example.com", "first_name": "Jane", "last_name": "Roe"}

    receipt = json.loads((tmp_path / "trust.pdf.proof.json").read_text())
    assert receipt["transaction_id"] == "tx_777"
    assert receipt["signers"][0]["access_link"] == "https://mock/s/0"


def test_status_exit_codes(mock_api: str, tmp_path: Path) -> None:
    assert run_proof("status", "tx_777", url=mock_api, cwd=tmp_path).returncode == 0
    MockProof.detailed_status = "active"
    assert run_proof("status", "tx_777", url=mock_api, cwd=tmp_path).returncode == 2


def test_fetch_refuses_incomplete_then_delivers(mock_api: str, tmp_path: Path) -> None:
    MockProof.detailed_status = "active"
    proc = run_proof("fetch", "tx_777", url=mock_api, cwd=tmp_path)
    assert proc.returncode == 2
    assert not (tmp_path / "notarized.pdf").exists()

    MockProof.detailed_status = "complete"
    proc = run_proof("fetch", "tx_777", "--out", "got", url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "got" / "notarized.pdf").read_bytes() == PDF_BYTES


def test_poll_cycle_and_terminal_states(mock_api: str, tmp_path: Path) -> None:
    receipt = tmp_path / "trust.pdf.proof.json"
    receipt.write_text(json.dumps({"transaction_id": "tx_777"}))

    MockProof.detailed_status = "active"
    proc = run_proof("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0
    assert "still active" in proc.stderr
    assert not (tmp_path / "inbox").exists()

    MockProof.detailed_status = "complete"
    proc = run_proof("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    new_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("NEW ")]
    assert len(new_lines) == 1
    fetched = tmp_path / "inbox" / "proof" / "tx_777" / "notarized.pdf"
    assert fetched.read_bytes() == PDF_BYTES
    assert json.loads(receipt.read_text())["completed"] is True

    # a canceled transaction goes terminal and is never re-polled
    receipt2 = tmp_path / "other.pdf.proof.json"
    receipt2.write_text(json.dumps({"transaction_id": "tx_777"}))
    MockProof.detailed_status = "canceled"
    proc = run_proof("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert "CANCELED" in proc.stderr
    assert json.loads(receipt2.read_text())["terminal"] == "canceled"
    MockProof.requests.clear()
    run_proof("poll", str(tmp_path), url=mock_api, cwd=tmp_path)
    assert not MockProof.requests


def test_send_refuses_a_draft_stamped_pdf(mock_api: str, tmp_path: Path) -> None:
    from pypdf import PdfWriter

    pdf = tmp_path / "draft.pdf"
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    w.add_metadata({"/ProsaicDraftBanner": "DRAFT—NOT EXECUTED"})
    with pdf.open("wb") as fh:
        w.write(fh)
    proc = run_proof("send", "draft.pdf", "--to", "j@example.com", url=mock_api, cwd=tmp_path)
    assert proc.returncode != 0
    assert "refusing to send a draft" in proc.stderr


def _security_shim(tmp_path: Path, ref: str, key: str) -> str:
    """A fake `security` on PATH answering the Keychain lookup for one
    service name — credential-by-reference without a real Keychain."""
    shim_dir = tmp_path / "shim-bin"
    shim_dir.mkdir()
    shim = shim_dir / "security"
    shim.write_text(f'#!/bin/sh\nif [ "$3" = "{ref}" ]; then echo {key}; exit 0; fi\nexit 1\n')
    shim.chmod(0o755)
    return str(shim_dir)


def test_matter_credential_is_incorporated_by_reference(mock_api: str, tmp_path: Path) -> None:
    """Same discipline as DocuSeal (ADR-0031): matter.yaml names the
    Keychain item; the client resolves it; the key never enters the
    matter."""
    (tmp_path / "matter.yaml").write_text(
        "connectors:\n  proof:\n    credential: proof.test-matter\n"
    )
    proc = subprocess.run(
        [sys.executable, str(CLIENT), "status", "tx_777"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "PROOF_URL": mock_api,
            "PATH": _security_shim(tmp_path, "proof.test-matter", "matter-scoped-key")
            + ":/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )
    assert proc.returncode == 0, proc.stderr
    assert any(r["auth"] == "matter-scoped-key" for r in MockProof.requests)


def test_matter_without_credential_reference_refuses(tmp_path: Path) -> None:
    (tmp_path / "matter.yaml").write_text("connectors:\n  proof: {}\n")
    proc = subprocess.run(
        [sys.executable, str(CLIENT), "status", "tx_777"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PROOF_URL": "http://127.0.0.1:1", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode != 0
    assert "credential" in proc.stderr and "ADR-0031" in proc.stderr
