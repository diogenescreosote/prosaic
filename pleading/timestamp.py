#!/usr/bin/env python3
"""RFC 3161 timestamp one or more PDFs using the freetsa.org free TSA.

Usage:
    python timestamp.py file.pdf [file2.pdf ...]
    python timestamp.py out/stip_to_seal/*.pdf

For each PDF, produces a <stem>.tsr sidecar file in the same directory.
If the sidecar already exists and the PDF has not changed since it was
created, the file is skipped.

Log format:
    Message sent  2026-05-30 09:51:42
    Certified     126 ms later
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import urllib.request
import urllib.error

DEFAULT_TSA_URL = "http://freetsa.org/tsr"
# Overridable for testing / alternate TSAs without editing the script.
TSA_URL = os.environ.get("PROSAIC_TSA_URL", DEFAULT_TSA_URL)
HASH_ALG = "sha256"
# OID for sha256 (2.16.840.1.101.3.4.2.1)
SHA256_OID = bytes([
    0x30, 0x31,           # SEQUENCE
    0x30, 0x0d,           # SEQUENCE
    0x06, 0x09,           # OID
    0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01,
    0x05, 0x00,           # NULL
    0x04, 0x20,           # OCTET STRING (32 bytes)
])


def _tlv(tag: int, content: bytes) -> bytes:
    """Minimal BER TLV encoder (single-byte tags, long-form length if needed)."""
    n = len(content)
    if n < 0x80:
        length = bytes([n])
    elif n < 0x100:
        length = bytes([0x81, n])
    elif n < 0x10000:
        length = bytes([0x82, n >> 8, n & 0xFF])
    else:
        raise ValueError("Content too large")
    return bytes([tag]) + length + content


def build_tsq(digest: bytes) -> bytes:
    """Build a minimal RFC 3161 TimeStampReq for sha256 without nonce."""
    # MessageImprint ::= SEQUENCE { hashAlgorithm AlgorithmIdentifier, hashedMessage OCTET STRING }
    msg_imprint = SHA256_OID + digest
    msg_imprint_seq = _tlv(0x30, msg_imprint)

    # TimeStampReq ::= SEQUENCE { version INTEGER (1), messageImprint MessageImprint,
    #                              certReq BOOLEAN DEFAULT FALSE }
    version = _tlv(0x02, b"\x01")  # INTEGER 1
    cert_req = _tlv(0x01, b"\xff")  # BOOLEAN TRUE (request the cert chain)

    body = version + msg_imprint_seq + cert_req
    return _tlv(0x30, body)


def timestamp_file(path: Path) -> bool:
    """Timestamp one PDF. Returns True on success (or fresh sidecar), False on failure."""
    sidecar = path.with_suffix(".tsr")

    # Skip if sidecar is newer than the PDF.
    if sidecar.exists() and sidecar.stat().st_mtime >= path.stat().st_mtime:
        print(f"  {path.name}: already timestamped, skipping")
        return True

    digest = hashlib.sha256(path.read_bytes()).digest()
    tsq = build_tsq(digest)

    sent_dt = datetime.now(timezone.utc).astimezone()
    sent_str = sent_dt.strftime("%Y-%m-%d %H:%M:%S")
    print(f"  {path.name}")
    print(f"    Message sent  {sent_str}")

    t0 = time.monotonic()
    try:
        req = urllib.request.Request(
            TSA_URL,
            data=tsq,
            headers={"Content-Type": "application/timestamp-query"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            tsr = resp.read()
    except urllib.error.HTTPError as e:
        print(f"    ERROR: HTTP {e.code} from TSA ({e.reason})", file=sys.stderr)
        print(f"    NOTE: If you see 403 in a browser, that is expected — "
              f"the endpoint only accepts POST requests.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"    ERROR: {e}", file=sys.stderr)
        return False

    elapsed_ms = (time.monotonic() - t0) * 1000

    if elapsed_ms < 1000:
        elapsed_str = f"{elapsed_ms:.0f} ms later"
    elif elapsed_ms < 60_000:
        elapsed_str = f"{elapsed_ms / 1000:.1f} seconds later"
    else:
        elapsed_str = f"{elapsed_ms / 60_000:.1f} minutes later"

    print(f"    Certified     {elapsed_str}")

    sidecar.write_bytes(tsr)
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: timestamp.py file.pdf [file2.pdf ...]", file=sys.stderr)
        sys.exit(1)

    paths = [Path(p) for p in sys.argv[1:]]
    errors = 0
    for p in paths:
        if not p.exists():
            print(f"  ERROR: not found: {p}", file=sys.stderr)
            errors += 1
            continue
        if p.suffix.lower() != ".pdf":
            print(f"  WARNING: skipping non-PDF: {p}")
            continue
        if not timestamp_file(p):
            errors += 1

    # A batch that timestamped nothing must not look successful in
    # scripts/CI: any per-file failure makes the whole run exit nonzero.
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
