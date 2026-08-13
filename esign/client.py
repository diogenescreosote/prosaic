#!/usr/bin/env python3
"""docuseal.py — send documents for signature and bring back what was signed.

One interface, two deployments (ADR-0023): DOCUSEAL_URL selects the
hosted service (https://api.docuseal.com, the default) or a
self-hosted instance's API endpoint, and nothing else changes. The
API key is a named credential per ADR-0012: DOCUSEAL_API_KEY in the
environment wins, else the macOS Keychain generic password
`prosaic.docuseal` — the key is referenced, never written to config
or logs.

Subcommands
    send <pdf> --to "Name <email>" [--to ...]   create a submission, email signers
    status <submission_id>                      per-signer state
    fetch <submission_id> [--out DIR]           signed PDFs + audit log, when done

Signature field placement uses DocuSeal's text tags: a document whose
text contains {{Signature;role=Signer 1}} (or plain {{Signature}})
gets a field there. The pleading language can put such tags in
source; a PDF without any tags still sends, with a warning, and the
signer places their signature manually.

`send` writes a receipt beside the PDF (<pdf>.esign.json): the
submission id, signers, and URLs — the record `status` and `fetch`
work from, and the thing a triage commit catalogs.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from docuseal import docuseal as ds

DEFAULT_URL = "https://api.docuseal.com"
CREDENTIAL_REF = "prosaic.docuseal"


def api_base() -> str:
    # DOCUSEAL_URL is prosaic's original spelling; DOCUSEAL_SERVER is
    # the official CLI/skill's. Either works, so one configuration
    # serves sc esign, the docuseal CLI, and the vendored skill.
    return (
        os.environ.get("DOCUSEAL_URL") or os.environ.get("DOCUSEAL_SERVER") or DEFAULT_URL
    ).rstrip("/")


def api_key() -> str:
    key = os.environ.get("DOCUSEAL_API_KEY")
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
        f"no DocuSeal API key: set DOCUSEAL_API_KEY, or store one in the "
        f"Keychain (security add-generic-password -s {CREDENTIAL_REF} "
        f"-a prosaic -w <key>)"
    )


def configure_sdk() -> None:
    """Point the official SDK (pypi.org/project/docuseal) at the
    configured deployment. The SDK owns the HTTP contract; prosaic
    owns the workflow around it."""
    ds.url = api_base()
    ds.key = api_key()
    ds.open_timeout = 60
    ds.read_timeout = 120


def sdk_call(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # the SDK raises per-status exception types
        raise SystemExit(f"DocuSeal API ({api_base()}): {e}") from None


def download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"X-Auth-Token": api_key()})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def parse_signer(spec: str) -> dict:
    """'Jane Roe <jane@example.com>' or bare 'jane@example.com'."""
    spec = spec.strip()
    if "<" in spec and spec.endswith(">"):
        name, _, email = spec.rpartition("<")
        return {"name": name.strip(), "email": email[:-1].strip()}
    return {"email": spec}


def cmd_send(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    if not pdf.exists():
        raise SystemExit(f"no such file: {pdf}")
    configure_sdk()

    submitters = [parse_signer(s) for s in args.to]
    for i, sub in enumerate(submitters):
        sub["role"] = f"Signer {i + 1}" if len(submitters) > 1 else "Signer"

    payload = {
        "name": args.name or pdf.stem,
        "documents": [
            {
                "name": pdf.name,
                "file": base64.b64encode(pdf.read_bytes()).decode(),
            }
        ],
        "submitters": submitters,
        "send_email": not args.no_email,
    }
    if args.subject or args.message:
        payload["message"] = {"subject": args.subject, "body": args.message}
    submission = sdk_call(ds.create_submission_from_pdf, payload)

    # The API returns the submitter list; normalize either shape.
    entries = (
        submission if isinstance(submission, list) else submission.get("submitters", [submission])
    )
    submission_id = entries[0].get("submission_id") or submission.get("id")

    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
        if "{{" not in text:
            print(
                "WARNING: no {{...}} field tags detected in the document; "
                "signers will have to place their own fields "
                "(prosaic signature blocks embed tags automatically)",
                file=sys.stderr,
            )

    receipt = {
        "submission_id": submission_id,
        "document": pdf.name,
        "api": api_base(),
        "submitters": [
            {
                "email": e.get("email"),
                "slug": e.get("slug"),
                "role": e.get("role"),
                "status": e.get("status"),
                "sign_url": (
                    f"{api_base().replace('/api', '')}/s/{e['slug']}" if e.get("slug") else None
                ),
            }
            for e in entries
        ],
    }
    receipt_path = pdf.with_name(pdf.name + ".esign.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"submission {submission_id} created; receipt: {receipt_path}")
    for e in receipt["submitters"]:
        print(f"  {e['email']} ({e.get('role')}): {e.get('sign_url') or '(emailed)'}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    configure_sdk()
    sub = sdk_call(ds.get_submission, args.submission_id)
    print(f"submission {args.submission_id}: {sub.get('status', 'unknown')}")
    for s in sub.get("submitters", []):
        stamp = s.get("completed_at") or s.get("opened_at") or s.get("sent_at") or ""
        print(f"  {s.get('email')}: {s.get('status')} {stamp}")
    return 0 if sub.get("status") == "completed" else 2


def cmd_fetch(args: argparse.Namespace) -> int:
    configure_sdk()
    sub = sdk_call(ds.get_submission, args.submission_id)
    if sub.get("status") != "completed":
        print(
            f"submission is {sub.get('status', 'unknown')}, not completed; nothing fetched",
            file=sys.stderr,
        )
        return 2
    out = Path(args.out or ".")
    out.mkdir(parents=True, exist_ok=True)
    docs = sdk_call(ds.get_submission_documents, args.submission_id)
    doc_list = docs.get("documents") if isinstance(docs, dict) else docs
    if not doc_list:
        doc_list = sub.get("documents", [])
    got = 0
    for doc in doc_list:
        dest = out / doc["name"]
        download(doc["url"], dest)
        print(f"fetched: {dest}")
        got += 1
    audit_url = sub.get("audit_log_url")
    if audit_url:
        dest = out / f"submission-{args.submission_id}-audit-log.pdf"
        download(audit_url, dest)
        print(f"fetched: {dest}")
        got += 1
    if not got:
        print("completed submission exposed no documents", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Send documents for e-signature via DocuSeal")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("send", help="create a submission from a PDF and email signers")
    sp.add_argument("pdf")
    sp.add_argument(
        "--to",
        action="append",
        required=True,
        help='signer, "Name <email>" (repeatable, in signing order)',
    )
    sp.add_argument("--name", help="template name (default: the file stem)")
    sp.add_argument("--subject", help="email subject")
    sp.add_argument("--message", help="email body")
    sp.add_argument(
        "--no-email", action="store_true", help="create the submission but let me deliver the links"
    )
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("status", help="per-signer state (exit 0 when completed)")
    sp.add_argument("submission_id")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("fetch", help="signed PDFs + audit log for a completed submission")
    sp.add_argument("submission_id")
    sp.add_argument("--out", help="destination directory (default: .)")
    sp.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
