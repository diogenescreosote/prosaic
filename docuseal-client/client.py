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

`send` writes a receipt beside the PDF (<pdf>.docuseal.json): the
submission id, signers, and URLs — the record `status` and `fetch`
work from, and the thing a triage commit catalogs.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from docuseal import docuseal as ds

DEFAULT_URL = "https://api.docuseal.com"
CREDENTIAL_REF = "prosaic.docuseal"

# The enclosing matter's connectors.docuseal mapping, set by
# load_matter_config(). None means no matter.yaml was found (ad-hoc
# use outside any matter).
MATTER_CFG: dict | None = None
MATTER_YAML: Path | None = None


def load_matter_config(start: Path) -> None:
    """Configuration is the matter's, not prosaic's (ADR-0031): walk
    up from `start` to the enclosing matter.yaml and take its
    connectors.docuseal mapping — `credential:` (a Keychain item
    named by reference; the key material never enters the matter)
    and optionally `url:` for a per-matter deployment."""
    global MATTER_CFG, MATTER_YAML
    d = (start if start.is_dir() else start.parent).resolve()
    for parent in (d, *d.parents):
        f = parent / "matter.yaml"
        if f.exists():
            import yaml

            try:
                data = yaml.safe_load(f.read_text()) or {}
            except yaml.YAMLError as e:
                raise SystemExit(f"unreadable {f}: {e}") from None
            MATTER_CFG = (data.get("connectors") or {}).get("docuseal") or {}
            MATTER_YAML = f
            return


def keychain_lookup(ref: str) -> str | None:
    # Not gated on sys.platform: the question is whether a `security`
    # command exists on PATH (macOS Keychain, or a compatible shim on
    # another OS), not what the OS calls itself.
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", ref, "-w"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def api_base() -> str:
    # DOCUSEAL_URL is prosaic's original spelling; DOCUSEAL_SERVER is
    # the official CLI/skill's. Either works, so one configuration
    # serves sc docuseal, the docuseal CLI, and the vendored skill.
    # Inside a matter, matter.yaml's connectors.docuseal.url comes
    # next; the environment stays the explicit per-run override.
    env = os.environ.get("DOCUSEAL_URL") or os.environ.get("DOCUSEAL_SERVER")
    matter = (MATTER_CFG or {}).get("url")
    return (env or matter or DEFAULT_URL).rstrip("/")


def signing_base() -> str:
    """The web origin for signer links (/s/<slug>). The hosted API
    lives on api.docuseal.com but signers sign on docuseal.com; a
    self-hosted instance serves both from one origin, with the API
    mounted under /api. (A naive '/api' strip ate the 'api.'
    subdomain of the hosted service — caught by the first live
    test-mode run.)"""
    base = api_base()
    if base == DEFAULT_URL:
        return "https://docuseal.com"
    return base.removesuffix("/api")


def api_key() -> str:
    key = os.environ.get("DOCUSEAL_API_KEY")
    if key:
        return key
    if MATTER_YAML is not None:
        # Inside a matter the credential must be incorporated by
        # reference — even a prosaic-global key. The matter owns the
        # binding; prosaic and the Keychain just hold the mechanism
        # and the material.
        ref = (MATTER_CFG or {}).get("credential")
        if not ref:
            raise SystemExit(
                f"this matter does not say which DocuSeal credential it "
                f"uses. Add to {MATTER_YAML}:\n"
                f"  connectors:\n"
                f"    docuseal:\n"
                f"      credential: {CREDENTIAL_REF}   # or a matter-specific Keychain item\n"
                f"(key material stays in the Keychain; the matter holds "
                f"only the reference — ADR-0031)"
            )
        key = keychain_lookup(ref)
        if key:
            return key
        raise SystemExit(
            f"the matter references credential {ref!r} but the Keychain "
            f"has no such item: security add-generic-password -s {ref} "
            f"-a prosaic -w <key>"
        )
    key = keychain_lookup(CREDENTIAL_REF)
    if key:
        return key
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


DRAFT_METADATA_KEY = "/ProsaicDraftBanner"


def draft_banner_of(pdf: Path) -> str | None:
    """The DRAFT banner a prosaic build stamped into this PDF's
    metadata, or None for a --final build (or a foreign PDF)."""
    try:
        from pypdf import PdfReader

        info = PdfReader(str(pdf)).metadata or {}
        value = info.get(DRAFT_METADATA_KEY)
        return str(value) if value else None
    except Exception:
        return None


def envelope_signers(envelope: str) -> list[dict]:
    """The signing roster declared in the matter's envelopes.yaml:

        envelopes:
          note:
            sources: [...]
            signers:              # signing order = signature-block order
              - name: Jane Roe
                email: jane@example.com
                note: Borrower    # human annotation; role stays Signer N

    Declarative intent beats emails retyped from a conversation, and
    the roster is versioned with the matter."""
    import yaml

    path = Path("envelopes.yaml")
    if not path.exists():
        raise SystemExit(
            "--envelope needs an envelopes.yaml in the working directory (run from the matter)"
        )
    data = yaml.safe_load(path.read_text()) or {}
    entry = (data.get("envelopes") or {}).get(envelope)
    if entry is None:
        raise SystemExit(f"no envelope {envelope!r} in envelopes.yaml")
    signers = entry.get("signers")
    if not signers:
        raise SystemExit(
            f"envelope {envelope!r} declares no signers: add a signers: "
            f"list (name, email, optional note) in signing order"
        )
    out = []
    for s in signers:
        if not s.get("email"):
            raise SystemExit(f"envelope {envelope!r}: every signer needs an email")
        rec = {"email": s["email"]}
        if s.get("name"):
            rec["name"] = s["name"]
        out.append(rec)
    return out


def field_sidecar(pdf: Path) -> dict | None:
    """The build's <pdf>.fields.json — field geometry the renderer
    computed, kept out of the PDF so the text layer stays clean."""
    path = pdf.with_name(pdf.name + ".fields.json")
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"unreadable field sidecar {path}: {e}") from None
    if not data.get("fields"):
        return None
    return data


def sidecar_api_fields(sidecar: dict) -> list[dict]:
    """Sidecar geometry (points, top-left origin) as the API's field
    objects (page-fraction areas, 1-based pages)."""
    pw = float(sidecar["page_width"])
    ph = float(sidecar["page_height"])
    return [
        {
            "name": f["name"],
            "type": f["type"],
            "role": f["role"],
            "areas": [
                {
                    "x": round(f["x"] / pw, 4),
                    "y": round(f["y_top"] / ph, 4),
                    "w": round(f["w"] / pw, 4),
                    "h": round(f["h"] / ph, 4),
                    "page": f["page"],
                }
            ],
        }
        for f in sidecar["fields"]
    ]


def tagged_role_count(pdf: Path) -> int | None:
    """How many distinct Signer roles the document declares — from the
    field sidecar when the build wrote one, else from embedded text
    tags (the esign: tags mode the free web UI needs), else None."""
    sidecar = field_sidecar(pdf)
    if sidecar:
        return len({f["role"] for f in sidecar["fields"]})
    if not shutil.which("pdftotext"):
        return None
    text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    roles = set(re.findall(r"\{\{Signature (\d+);role=Signer \d+;", text))
    return len(roles) if roles else None


def cmd_send(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    if not pdf.exists():
        raise SystemExit(f"no such file: {pdf}")
    banner = draft_banner_of(pdf)
    if banner and not args.allow_draft:
        raise SystemExit(
            f"refusing to send a draft: this PDF is stamped "
            f"{banner!r}. Rebuild with --final for the version that "
            f"goes into the world, or pass --allow-draft to "
            f"deliberately circulate the draft."
        )
    configure_sdk()

    if args.envelope and args.to:
        raise SystemExit("give --envelope OR --to, not both")
    if args.envelope:
        submitters = envelope_signers(args.envelope)
    elif args.to:
        submitters = [parse_signer(s) for s in args.to]
    else:
        raise SystemExit(
            "who signs? --envelope <name> (the signers: "
            'roster in envelopes.yaml) or --to "Name <email>"'
        )
    for i, sub in enumerate(submitters):
        sub["role"] = f"Signer {i + 1}" if len(submitters) > 1 else "Signer"

    expected = tagged_role_count(pdf)
    if expected is not None and expected != len(submitters):
        raise SystemExit(
            f"signer mismatch: the document's field tags expect {expected} "
            f"signer(s), {len(submitters)} given. Signing order is the "
            f"document's signature-block order; fix the roster (or the "
            f"document) before sending."
        )

    document: dict = {
        "name": pdf.name,
        "file": base64.b64encode(pdf.read_bytes()).decode(),
    }
    sidecar = field_sidecar(pdf)
    if sidecar:
        document["fields"] = sidecar_api_fields(sidecar)
    payload = {
        "name": args.name or pdf.stem,
        "documents": [document],
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

    if not sidecar and shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
        if "{{" not in text:
            print(
                "WARNING: no field sidecar and no {{...}} tags in the "
                "document; signers will have to place their own fields "
                "(prosaic builds write <pdf>.fields.json automatically)",
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
                "sign_url": (f"{signing_base()}/s/{e['slug']}" if e.get("slug") else None),
            }
            for e in entries
        ],
    }
    receipt_path = pdf.with_name(pdf.name + ".docuseal.json")
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


def cmd_poll(args: argparse.Namespace) -> int:
    """Walk the matter for DocuSeal receipts, check each pending
    submission, and fetch what completed into inbox/docuseal/ — the
    connector engine (specs/docuseal.md): prints "NEW <abs path>" per
    fetched file for the sync/triage pipeline, updates each receipt
    so a completed submission is never polled again."""
    matter = Path(args.matter_dir or ".").resolve()
    receipts = [
        p
        for p in matter.rglob("*.docuseal.json")
        if ".git" not in p.parts and "inbox" not in p.parts
    ]
    if not receipts:
        return 0
    configure_sdk()
    pending = 0
    for receipt_path in sorted(receipts):
        try:
            receipt = json.loads(receipt_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARN: unreadable receipt {receipt_path}: {e}", file=sys.stderr)
            continue
        if receipt.get("completed") or receipt.get("terminal"):
            continue
        sid = receipt.get("submission_id")
        if not sid:
            print(f"WARN: receipt without submission_id: {receipt_path}", file=sys.stderr)
            continue
        sub = sdk_call(ds.get_submission, sid)
        status = sub.get("status", "unknown")
        receipt["last_status"] = status
        # DocuSeal's documented lifecycle: pending, completed,
        # declined, expired. Declined and expired are terminal: mark
        # the receipt so it never polls again, and say so loudly --
        # a dead ceremony is a fact the matter needs, not a retry.
        if status in ("declined", "expired"):
            receipt["terminal"] = status
            receipt["completed"] = False
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
            print(
                f"docuseal: submission {sid} {status.upper()} -- no "
                f"documents will come; re-send if still wanted",
                file=sys.stderr,
            )
            continue
        if status != "completed":
            pending += 1
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
            print(f"docuseal: submission {sid} still {status}", file=sys.stderr)
            continue

        out = matter / "inbox" / "docuseal" / str(sid)
        out.mkdir(parents=True, exist_ok=True)
        docs = sdk_call(ds.get_submission_documents, sid)
        doc_list = docs.get("documents") if isinstance(docs, dict) else docs
        if not doc_list:
            doc_list = sub.get("documents", [])
        fetched = []
        for doc in doc_list:
            dest = out / doc["name"]
            download(doc["url"], dest)
            fetched.append(str(dest))
            print(f"NEW {dest}")
        audit_url = sub.get("audit_log_url")
        if audit_url:
            dest = out / f"submission-{sid}-audit-log.pdf"
            download(audit_url, dest)
            fetched.append(str(dest))
            print(f"NEW {dest}")
        receipt["completed"] = True
        receipt["fetched"] = fetched
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"docuseal: submission {sid} completed; {len(fetched)} file(s) fetched to {out}",
            file=sys.stderr,
        )
    if pending:
        print(f"docuseal: {pending} submission(s) still pending", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Send documents for e-signature via DocuSeal")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("send", help="create a submission from a PDF and email signers")
    sp.add_argument("pdf")
    sp.add_argument(
        "--envelope",
        help="take the signing roster from this envelope's signers: list in envelopes.yaml",
    )
    sp.add_argument(
        "--to",
        action="append",
        help='signer, "Name <email>" (repeatable, in signing order)',
    )
    sp.add_argument("--name", help="template name (default: the file stem)")
    sp.add_argument("--subject", help="email subject")
    sp.add_argument("--message", help="email body")
    sp.add_argument(
        "--no-email", action="store_true", help="create the submission but let me deliver the links"
    )
    sp.add_argument(
        "--allow-draft", action="store_true", help="send even though the PDF carries a DRAFT banner"
    )
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("status", help="per-signer state (exit 0 when completed)")
    sp.add_argument("submission_id")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser(
        "poll",
        help="check every pending receipt in a matter; fetch completed "
        "submissions into inbox/docuseal/ (the connector engine)",
    )
    sp.add_argument("matter_dir", nargs="?", default=".")
    sp.set_defaults(func=cmd_poll)

    sp = sub.add_parser("fetch", help="signed PDFs + audit log for a completed submission")
    sp.add_argument("submission_id")
    sp.add_argument("--out", help="destination directory (default: .)")
    sp.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    start = Path(getattr(args, "matter_dir", None) or getattr(args, "pdf", None) or ".")
    load_matter_config(start)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
