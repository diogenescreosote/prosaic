#!/usr/bin/env python3
"""attest.py — cryptographic attestation for matter documents.

The protocol this implements (ADR-0022): a signing key is anchored on
paper (embedded, with a QR block, in a traditionally executed
document); everything after that is verified against THAT key, by
file, never against whatever happens to be in a keyring. Documents
are identified by two independent hashes (SHA-256 and SHA3-512, both
base64) so no single algorithm's failure orphans the record. A signed
MANIFEST names the currently operative version of every document —
the mutable pointer under the immutable anchor — so re-executing one
document never requires re-executing another.

Subcommands
    hash <file>...                     print the dual hashes
    sign <file>... --key <fpr>         detached armored sig -> <file>.sig.asc
    verify <file> --pubkey <key.asc>   verify <file>.sig.asc against that key only
    manifest write <out.md> <file>... --key <fpr>
                                       write + clearsign the manifest
    manifest verify <manifest.md> --pubkey <key.asc>
                                       verify the signature AND every hash
    timestamp <file>                   OpenTimestamps proof -> <file>.ots

gpg does the cryptography; this file does the protocol. Verification
builds a throwaway keyring holding only the expected key, so a
signature by any other key -- including a well-meaning one the user
also owns -- fails loudly.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST_HEADER = "# Document Manifest"
MANIFEST_STATEMENT = (
    "The files listed below, identified by BOTH hash values shown "
    "(Base64-encoded SHA-256 and SHA3-512), are the operative versions "
    "as of the signature date on this manifest. A file matching both "
    "hashes should be presumed authentic; a file matching neither, or "
    "only one, should not. This manifest supersedes every earlier "
    "manifest signed by the same key."
)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        raise SystemExit(f"{cmd[0]} is not installed (see system-dependencies.yaml)") from None


def dual_hashes(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    sha256 = base64.b64encode(hashlib.sha256(data).digest()).decode()
    sha3 = base64.b64encode(hashlib.sha3_512(data).digest()).decode()
    return sha256, sha3


# --- keyring isolation -------------------------------------------------------


def _isolated_gpg(pubkey: Path, home: str) -> list[str]:
    """A gpg invocation prefix whose keyring holds ONLY pubkey."""
    base = ["gpg", "--homedir", home, "--batch", "--no-default-keyring"]
    imp = _run([*base, "--import", str(pubkey)])
    if imp.returncode != 0:
        raise SystemExit(f"could not import {pubkey}: {imp.stderr.strip()}")
    return base


# --- subcommands -------------------------------------------------------------


def cmd_hash(args: argparse.Namespace) -> int:
    for name in args.files:
        p = Path(name)
        sha256, sha3 = dual_hashes(p)
        print(f"{p.name}")
        print(f"  SHA-256 (b64):  {sha256}")
        print(f"  SHA3-512 (b64): {sha3}")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    for name in args.files:
        p = Path(name)
        sig = p.with_name(p.name + ".sig.asc")
        cmd = [
            "gpg",
            "--batch",
            "--yes",
            "--armor",
            "--detach-sign",
            "--digest-algo",
            "SHA512",
            "--output",
            str(sig),
        ]
        if args.key:
            cmd += ["--local-user", args.key]
        proc = _run([*cmd, str(p)])
        if proc.returncode != 0:
            print(proc.stderr.strip(), file=sys.stderr)
            return 1
        print(f"signed: {sig}")
        if args.timestamp:
            _timestamp(sig)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    p = Path(args.file)
    sig = Path(args.sig) if args.sig else p.with_name(p.name + ".sig.asc")
    if not sig.exists():
        raise SystemExit(f"no signature at {sig}")
    with tempfile.TemporaryDirectory() as home:
        base = _isolated_gpg(Path(args.pubkey), home)
        proc = _run([*base, "--verify", str(sig), str(p)])
    ok = proc.returncode == 0
    detail = proc.stderr.strip().splitlines()
    for line in detail:
        if (
            "Signature made" in line
            or "Good signature" in line
            or "BAD signature" in line
            or "No public key" in line
        ):
            print(line)
    print(f"{'VERIFIED' if ok else 'FAILED'}: {p.name} against {args.pubkey}")
    return 0 if ok else 1


def _manifest_rows(files: list[str]) -> str:
    rows = ["| File | SHA-256 (Base64) | SHA3-512 (Base64) |", "|---|---|---|"]
    for name in sorted(files):
        p = Path(name)
        sha256, sha3 = dual_hashes(p)
        rows.append(f"| {p.name} | `{sha256}` | `{sha3}` |")
    return "\n".join(rows)


def cmd_manifest_write(args: argparse.Namespace) -> int:
    body = f"{MANIFEST_HEADER}\n\n{MANIFEST_STATEMENT}\n\n" + _manifest_rows(args.files) + "\n"
    out = Path(args.out)
    cmd = [
        "gpg",
        "--batch",
        "--yes",
        "--armor",
        "--clearsign",
        "--digest-algo",
        "SHA512",
        "--output",
        str(out),
    ]
    if args.key:
        cmd += ["--local-user", args.key]
    proc = subprocess.run(cmd, input=body, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr.strip(), file=sys.stderr)
        return 1
    print(f"manifest written and signed: {out}")
    if args.timestamp:
        _timestamp(out)
    return 0


MANIFEST_ROW = re.compile(r"^\| (?P<name>[^|]+) \| `(?P<sha256>[^`]+)` \| `(?P<sha3>[^`]+)` \|$")


def cmd_manifest_verify(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    with tempfile.TemporaryDirectory() as home:
        base = _isolated_gpg(Path(args.pubkey), home)
        proc = _run([*base, "--verify", str(manifest)])
    if proc.returncode != 0:
        print(f"FAILED: manifest signature does not verify against {args.pubkey}", file=sys.stderr)
        print(proc.stderr.strip(), file=sys.stderr)
        return 1
    print(f"manifest signature VERIFIED against {args.pubkey}")

    base_dir = manifest.parent if args.dir is None else Path(args.dir)
    failures = 0
    checked = 0
    for line in manifest.read_text().splitlines():
        m = MANIFEST_ROW.match(line.strip())
        if not m or m.group("name").strip() == "File":
            continue
        checked += 1
        target = base_dir / m.group("name").strip()
        if not target.exists():
            print(f"  MISSING: {target}")
            failures += 1
            continue
        sha256, sha3 = dual_hashes(target)
        if sha256 == m.group("sha256") and sha3 == m.group("sha3"):
            print(f"  ok: {target.name}")
        else:
            print(f"  HASH MISMATCH: {target.name}")
            failures += 1
    if checked == 0:
        print("  (manifest lists no files)", file=sys.stderr)
        return 1
    return 1 if failures else 0


def _timestamp(path: Path) -> None:
    """OpenTimestamps proof beside the file; degrade gracefully without ots."""
    if shutil.which("ots") is None:
        print(
            "  (timestamp skipped: ots not installed -- pip install opentimestamps-client)",
            file=sys.stderr,
        )
        return
    proc = _run(["ots", "stamp", str(path)])
    if proc.returncode == 0:
        print(f"timestamped: {path}.ots")
    else:
        print(f"  (timestamp failed: {proc.stderr.strip()[:200]})", file=sys.stderr)


def cmd_timestamp(args: argparse.Namespace) -> int:
    for name in args.files:
        _timestamp(Path(name))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Cryptographic attestation for matter documents")
    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("hash", help="print dual hashes (SHA-256 + SHA3-512, base64)")
    sp.add_argument("files", nargs="+")
    sp.set_defaults(func=cmd_hash)

    sp = sub.add_parser("sign", help="detached armored signature per file")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--key", help="signing key (fingerprint or uid)")
    sp.add_argument(
        "--timestamp", action="store_true", help="also stamp each signature with OpenTimestamps"
    )
    sp.set_defaults(func=cmd_sign)

    sp = sub.add_parser("verify", help="verify a detached signature against ONE key")
    sp.add_argument("file")
    sp.add_argument(
        "--pubkey", required=True, help="armored public key file the signature must match"
    )
    sp.add_argument("--sig", help="signature path (default: <file>.sig.asc)")
    sp.set_defaults(func=cmd_verify)

    man = sub.add_parser("manifest", help="signed manifest of operative documents")
    man_sub = man.add_subparsers(dest="subcommand", required=True)

    sp = man_sub.add_parser("write", help="write + clearsign a manifest")
    sp.add_argument("out")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--key", help="signing key (fingerprint or uid)")
    sp.add_argument("--timestamp", action="store_true")
    sp.set_defaults(func=cmd_manifest_write)

    sp = man_sub.add_parser("verify", help="verify manifest signature and every hash")
    sp.add_argument("manifest")
    sp.add_argument("--pubkey", required=True)
    sp.add_argument(
        "--dir", help="directory the listed files live in (default: beside the manifest)"
    )
    sp.set_defaults(func=cmd_manifest_verify)

    sp = sub.add_parser("timestamp", help="OpenTimestamps proof for a file")
    sp.add_argument("files", nargs="+")
    sp.set_defaults(func=cmd_timestamp)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
