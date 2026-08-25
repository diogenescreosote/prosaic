#!/usr/bin/env python3
"""sign.py --- apply a signature to a built document and attest it (ADR-0036).

Subcommands
    slots <pdf>                       what signature blanks the document has
    marks                             signature images available to sign with
    apply <pdf> --as KEY --name NAME  sign, stamp, attest
    verify <attestation-dir>          re-check a recorded signing event

`apply` never modifies its input and never writes into a build directory.
The signed artifact is a new file, and the exact bytes of that file are
what the attestation covers --- see ADR-0036 for why attesting an artifact
beats trying to make the build reproducible.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signing import SignRequest, SignerError, get_signer  # noqa: E402
from signing import audit, slots as slots_mod, store  # noqa: E402


def _matter_root(start: Path) -> Path | None:
    for parent in [start.resolve(), *start.resolve().parents]:
        if (parent / "matter.yaml").is_file():
            return parent
    return None


def cmd_slots(args: argparse.Namespace) -> int:
    signer = get_signer("local", include_form_lines=args.include_form_lines)
    found = signer.slots(Path(args.pdf))
    print(f"{Path(args.pdf).name}: {len(found)} slot(s)")
    print(slots_mod.describe(found))
    return 0


def cmd_marks(_args: argparse.Namespace) -> int:
    have = store.available()
    print(f"signature store: {store.store_dir()}")
    if not have:
        print("  (empty --- drop a PNG of the signature in, named <key>.png)")
        return 0
    for key in have:
        print(f"  {key}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    pdf = Path(args.pdf)
    audit_root = Path(args.audit_root) if args.audit_root else None
    if audit_root is None:
        root = _matter_root(pdf)
        if root is None:
            raise SystemExit(
                "cannot find the matter root (no matter.yaml above "
                f"{pdf}); pass --audit-root explicitly"
            )
        audit_root = root / "audit_log"

    when = (
        _dt.date.fromisoformat(args.date) if args.date else _dt.date.today()
    )
    req = SignRequest(
        pdf=pdf,
        signer_key=args.signer_key,
        signer_name=args.name,
        date=when,
        gpg_key=args.gpg_key,
        audit_root=audit_root,
        output=Path(args.output) if args.output else None,
        timestamp=not args.no_timestamp,
    )
    signer = get_signer(
        args.backend, **({"include_form_lines": args.include_form_lines}
                        if args.backend == "local" else {})
    )
    result = signer.request(req)

    print(f"outcome:      {result.outcome.value}")
    if result.signed_pdf:
        print(f"signed:       {result.signed_pdf}")
    print(f"reference:    {result.reference}")
    if result.attestation_dir:
        print(f"attestation:  {result.attestation_dir}")
    if result.detail:
        print(f"              {result.detail}")
    if not signer.produces_local_attestation:
        print(
            "  note: this backend issues its own completion certificate; no "
            "local attestation was written (ADR-0036)."
        )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    pubkey = Path(args.pubkey) if args.pubkey else None
    problems = audit.verify(directory, pubkey)
    if not problems:
        print(f"VERIFIED: {directory.name}")
        return 0
    print(f"PROBLEMS: {directory.name}")
    for p in problems:
        print(f"  - {p}")
    return 1


def main() -> None:
    p = argparse.ArgumentParser(prog="sc sign", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("slots", help="list the signature blanks in a PDF")
    sp.add_argument("pdf")
    sp.add_argument("--include-form-lines", action="store_true",
                    help="also anchor on Judicial Council signature labels")
    sp.set_defaults(func=cmd_slots)

    sp = sub.add_parser("marks", help="list available signature images")
    sp.set_defaults(func=cmd_marks)

    sp = sub.add_parser("apply", help="sign a document and attest it")
    sp.add_argument("pdf")
    sp.add_argument("--as", dest="signer_key", required=True,
                    metavar="KEY", help="signature image key (see `marks`)")
    sp.add_argument("--name", required=True,
                    help="legal name for the statement of assent")
    sp.add_argument("--gpg-key", default=None,
                    help="gpg key to sign the statement with (fingerprint)")
    sp.add_argument("--date", default=None, metavar="YYYY-MM-DD",
                    help="date of execution (default: today)")
    sp.add_argument("-o", "--output", default=None,
                    help="destination PDF (default: <matter>/staging/...)")
    sp.add_argument("--audit-root", default=None,
                    help="default: <matter>/audit_log")
    sp.add_argument("--backend", default="local", help="local | docuseal")
    sp.add_argument("--include-form-lines", action="store_true")
    sp.add_argument("--no-timestamp", action="store_true",
                    help="skip OpenTimestamps (needs network)")
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("verify", help="re-check a recorded signing event")
    sp.add_argument("directory")
    sp.add_argument("--pubkey", default=None)
    sp.set_defaults(func=cmd_verify)

    args = p.parse_args()
    try:
        raise SystemExit(args.func(args))
    except SignerError as exc:
        raise SystemExit(f"error: {exc}") from None


if __name__ == "__main__":
    main()
