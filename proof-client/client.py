#!/usr/bin/env python3
"""client.py — remote online notarization through Proof (proof.com).

Proof is the RON platform (formerly Notarize) whose Business API
takes a document plus signer, connects the signer to a commissioned
online notary by video, and returns the notarized document. This
client deliberately mirrors the DocuSeal client's workflow shape —
send / status / fetch / poll, receipts, connector — WITHOUT
generalizing the two into one abstraction: they are different
services with different protocols, and a premature "e-sign
interface" would flatten exactly the differences that matter
(detailed_status lifecycles, notarial journals, document delivery).

    send <pdf> --to "Name <email>"     create + activate a transaction
    status <transaction_id>            detailed status (exit 0 = complete)
    fetch <transaction_id> [--out D]   completed notarized document(s)
    poll [matter_dir]                  connector engine over *.proof.json

API mechanics (dev.proof.com): base https://api.proof.com (sandbox:
https://api.fairfax.proof.com, override with PROOF_URL), auth header
``ApiKey``, POST /v1/transactions with base64 documents marked
``requirement: notarization``, GET /v1/transactions/{id} whose
``detailed_status`` runs draft → sent_to_signer → active → complete
(or expired / canceled), completed documents via
``documents[].final_document_url``. NOT yet exercised against a live
Proof account — first real use should run against the fairfax
sandbox and this notice removed once it has.

The API key is a named credential per ADR-0012: PROOF_API_KEY in the
environment, else the macOS Keychain entry ``prosaic.proof``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://api.proof.com"
CREDENTIAL_REF = "prosaic.proof"
TERMINAL_FAILURES = ("expired", "canceled", "rejected")
DRAFT_METADATA_KEY = "/ProsaicDraftBanner"


def api_base() -> str:
    return os.environ.get("PROOF_URL", DEFAULT_URL).rstrip("/")


def api_key() -> str:
    key = os.environ.get("PROOF_API_KEY")
    if key:
        return key
    if sys.platform == "darwin":
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", CREDENTIAL_REF, "-w"],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    raise SystemExit(
        f"no Proof API key: set PROOF_API_KEY, or store one in the "
        f"Keychain (security add-generic-password -s {CREDENTIAL_REF} "
        f"-a prosaic -w <key>)"
    )


def request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{api_base()}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"ApiKey": api_key(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        raise SystemExit(f"Proof API {method} {path}: HTTP {e.code}: {body}") from None
    except urllib.error.URLError as e:
        raise SystemExit(f"Proof unreachable at {api_base()}: {e.reason}") from None


def download(url: str, dest: Path) -> None:
    # final_document_url links are pre-signed; no auth header needed.
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def draft_banner_of(pdf: Path) -> str | None:
    try:
        from pypdf import PdfReader

        info = PdfReader(str(pdf)).metadata or {}
        value = info.get(DRAFT_METADATA_KEY)
        return str(value) if value else None
    except Exception:
        return None


def parse_signer(spec: str) -> dict:
    spec = spec.strip()
    if "<" in spec and spec.endswith(">"):
        name, _, email = spec.rpartition("<")
        parts = name.strip().split()
        rec: dict = {"email": email[:-1].strip()}
        if parts:
            rec["first_name"] = parts[0]
        if len(parts) > 1:
            rec["last_name"] = " ".join(parts[1:])
        return rec
    return {"email": spec}


def cmd_send(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    if not pdf.exists():
        raise SystemExit(f"no such file: {pdf}")
    banner = draft_banner_of(pdf)
    if banner and not args.allow_draft:
        raise SystemExit(
            f"refusing to send a draft for notarization: this PDF is "
            f"stamped {banner!r}. Rebuild with --final, or pass "
            f"--allow-draft to deliberately send the draft."
        )

    payload = {
        "transaction_name": args.name or pdf.stem,
        "signers": [parse_signer(s) for s in args.to],
        "documents": [
            {
                "resource": base64.b64encode(pdf.read_bytes()).decode(),
                "requirement": "notarization",
                "filename": pdf.name,
            }
        ],
        "suppress_email": bool(args.no_email),
    }
    tx = request("POST", "/v1/transactions", payload)
    tx_id = tx.get("id")

    receipt = {
        "transaction_id": tx_id,
        "document": pdf.name,
        "api": api_base(),
        "detailed_status": tx.get("detailed_status") or tx.get("status"),
        "signers": [
            {
                "email": s.get("email"),
                "access_link": s.get("transaction_access_link"),
            }
            for s in (tx.get("signer_info") or tx.get("signers") or [])
        ],
    }
    receipt_path = pdf.with_name(pdf.name + ".proof.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"transaction {tx_id} created; receipt: {receipt_path}")
    for s in receipt["signers"]:
        print(f"  {s['email']}: {s.get('access_link') or '(emailed)'}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    tx = request("GET", f"/v1/transactions/{args.transaction_id}")
    status = tx.get("detailed_status") or tx.get("status", "unknown")
    print(f"transaction {args.transaction_id}: {status}")
    return 0 if status == "complete" else 2


def _fetch_documents(tx_id: str, out: Path) -> list[str]:
    tx = request("GET", f"/v1/transactions/{tx_id}?document_url_version=v1")
    status = tx.get("detailed_status") or tx.get("status", "unknown")
    if status != "complete":
        print(f"transaction is {status}, not complete; nothing fetched", file=sys.stderr)
        return []
    out.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    for i, doc in enumerate(tx.get("documents", [])):
        url = doc.get("final_document_url") or doc.get("signed_url")
        if not url:
            continue
        name = doc.get("document_name") or doc.get("name") or f"notarized-{i + 1}.pdf"
        dest = out / name
        download(url, dest)
        fetched.append(str(dest))
    return fetched


def cmd_fetch(args: argparse.Namespace) -> int:
    fetched = _fetch_documents(args.transaction_id, Path(args.out or "."))
    for f in fetched:
        print(f"fetched: {f}")
    if not fetched:
        return 2
    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    """Connector engine over *.proof.json receipts: fetch completed
    notarizations into inbox/proof/<id>/, printing NEW lines for
    triage; expired/canceled transactions go terminal."""
    matter = Path(args.matter_dir or ".").resolve()
    receipts = [
        p for p in matter.rglob("*.proof.json") if ".git" not in p.parts and "inbox" not in p.parts
    ]
    pending = 0
    for receipt_path in sorted(receipts):
        try:
            receipt = json.loads(receipt_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARN: unreadable receipt {receipt_path}: {e}", file=sys.stderr)
            continue
        if receipt.get("completed") or receipt.get("terminal"):
            continue
        tx_id = receipt.get("transaction_id")
        if not tx_id:
            print(f"WARN: receipt without transaction_id: {receipt_path}", file=sys.stderr)
            continue
        tx = request("GET", f"/v1/transactions/{tx_id}?document_url_version=v1")
        status = tx.get("detailed_status") or tx.get("status", "unknown")
        receipt["last_status"] = status
        if status in TERMINAL_FAILURES:
            receipt["terminal"] = status
            receipt["completed"] = False
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
            print(
                f"proof: transaction {tx_id} {status.upper()} -- no "
                f"notarized documents will come; re-send if still wanted",
                file=sys.stderr,
            )
            continue
        if status != "complete":
            pending += 1
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
            print(f"proof: transaction {tx_id} still {status}", file=sys.stderr)
            continue

        out = matter / "inbox" / "proof" / str(tx_id)
        out.mkdir(parents=True, exist_ok=True)
        fetched: list[str] = []
        for i, doc in enumerate(tx.get("documents", [])):
            url = doc.get("final_document_url") or doc.get("signed_url")
            if not url:
                continue
            name = doc.get("document_name") or doc.get("name") or f"notarized-{i + 1}.pdf"
            dest = out / name
            download(url, dest)
            fetched.append(str(dest))
            print(f"NEW {dest}")
        receipt["completed"] = True
        receipt["fetched"] = fetched
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"proof: transaction {tx_id} complete; {len(fetched)} file(s) fetched to {out}",
            file=sys.stderr,
        )
    if pending:
        print(f"proof: {pending} transaction(s) still pending", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Remote online notarization via Proof (proof.com)")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("send", help="create a notarization transaction from a PDF")
    sp.add_argument("pdf")
    sp.add_argument(
        "--to",
        action="append",
        required=True,
        help='signer, "Name <email>" (repeatable)',
    )
    sp.add_argument("--name", help="transaction name (default: the file stem)")
    sp.add_argument(
        "--no-email", action="store_true", help="suppress Proof's signer notification email"
    )
    sp.add_argument(
        "--allow-draft", action="store_true", help="send even though the PDF carries a DRAFT banner"
    )
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("status", help="detailed status (exit 0 when complete)")
    sp.add_argument("transaction_id")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("fetch", help="notarized document(s) for a complete transaction")
    sp.add_argument("transaction_id")
    sp.add_argument("--out", help="destination directory (default: .)")
    sp.set_defaults(func=cmd_fetch)

    sp = sub.add_parser("poll", help="check pending receipts; fetch completed notarizations")
    sp.add_argument("matter_dir", nargs="?", default=".")
    sp.set_defaults(func=cmd_poll)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
