"""Writing the attestation record for one local signing event.

Layout, one directory per event, under `<matter>/audit_log/signatures/local/`:

    2026-08-25_declaration_andrew_cone_4823-9012-3391v1/
        statement.txt        the claim, in plain language, with the digests
        statement.txt.asc    the same, clearsigned by the signer's GPG key
        statement.txt.asc.ots  OpenTimestamps proof of the clearsigned claim
        attestation.json     the same facts, for machines
        <document>.pdf       the exact attested bytes

The GPG signature covers the **statement**, not the PDF directly, and
that is the point: the legally meaningful content is the sentence saying
whose signature it is and that they intend to be bound. Detached-signing
the PDF would authenticate the file while leaving the assertion about it
unsigned. The statement names the document by both digests, so signing
the statement binds the claim to the bytes.

Per ADR-0036 the attested bytes are retained here, deliberately
duplicating whatever copy lives in `staging/` or `pleadings/`. Those
copies get renamed, superseded and moved; an attestation whose subject
has been altered asserts nothing.

`ots` produces a calendar-server commitment immediately and a Bitcoin
attestation only after a few hours, so the `.ots` file must be upgraded
later (`ots upgrade`) and the upgraded file retained. Until then the
proof rests on the calendar operator, which is a weaker claim than the
one it will eventually support. `verify()` says so when it sees an
un-upgraded proof.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .base import SignerError

_ROOT = Path(__file__).resolve().parent.parent
_attest_mod = None


def _attest():
    """crypto/attest.py, loaded by path.

    It is a subprocess-invoked script with no package around it, so there
    is no import path to it. Loading by location keeps one implementation
    of the dual-hash convention (ADR-0022) rather than a second copy here
    that could drift from it.
    """
    global _attest_mod
    if _attest_mod is None:
        path = _ROOT / "crypto" / "attest.py"
        spec = importlib.util.spec_from_file_location("prosaic_attest", path)
        if spec is None or spec.loader is None:
            raise SignerError(f"cannot load {path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _attest_mod = mod
    return _attest_mod


STATEMENT_TITLE = "STATEMENT OF SIGNATURE AND ASSENT"


@dataclass
class Attestation:
    reference: str
    document: str
    sha256_b64: str
    sha3_512_b64: str
    signer_name: str
    signer_key: str
    gpg_key: str | None
    signed_at: str
    statement_file: str
    signature_file: str | None
    timestamp_file: str | None
    signer_backend: str = "local"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def event_dir(audit_root: Path, backend: str, pdf: Path, reference: str,
              when: _dt.date) -> Path:
    return (
        audit_root
        / "signatures"
        / backend
        / f"{when.isoformat()}_{_slug(pdf.stem)}_{reference}"
    )


def render_statement(a: Attestation) -> str:
    """The human-readable claim that gets signed.

    Wording follows crypto/attest.py's manifest statement in one
    important respect --- a file matching only one of the two hashes is
    explicitly *not* the document --- because that is the sentence that
    makes dual hashing mean anything to a reader who is not a
    cryptographer.
    """
    return f"""{STATEMENT_TITLE}

I, {a.signer_name}, state:

1.  I applied my signature to the document identified below, on the date
    and at the time stated, using software under my control on my own
    computer.

2.  That document is identified by BOTH hash values shown. A file
    matching both is the document I signed. A file matching neither, or
    only one of the two, is not.

3.  I adopted that signature as my own, and I intend to be bound by the
    text appearing above it.

    Document:     {a.document}
    Reference:    {a.reference}
    SHA-256:      {a.sha256_b64}
    SHA3-512:     {a.sha3_512_b64}
    Signed at:    {a.signed_at}
    Signing key:  {a.gpg_key or "(gpg default key)"}

This statement says nothing about whether the document was filed or
served, and nothing about any signature but my own.
"""


def _clearsign(statement: Path, gpg_key: str | None) -> Path | None:
    """Clearsign the statement, letting gpg prompt for the passphrase.

    Deliberately no `--batch`: it suppresses pinentry, so a
    passphrase-protected key fails with "Inappropriate ioctl for device"
    rather than asking. Signing is an interactive act here --- a human is
    present, and being asked for the passphrase is a feature, since it is
    the moment the signature is actually authorised. GPG_TTY is exported
    for the same reason: without it, terminal pinentry cannot open.
    """
    out = statement.with_name(statement.name + ".asc")
    cmd = ["gpg", "--yes", "--armor", "--clearsign",
           "--digest-algo", "SHA512", "--output", str(out)]
    if gpg_key:
        cmd += ["--local-user", gpg_key]

    env = dict(os.environ)
    if "GPG_TTY" not in env and sys.stdin.isatty():
        try:
            env["GPG_TTY"] = os.ttyname(sys.stdin.fileno())
        except OSError:
            pass

    try:
        proc = subprocess.run([*cmd, str(statement)], text=True,
                              capture_output=True, env=env)
    except FileNotFoundError:
        raise SignerError(
            "gpg is not installed, so the statement of assent cannot be "
            "signed --- and an unsigned attestation asserts nothing"
        ) from None
    if proc.returncode != 0:
        detail = proc.stderr.strip()
        hint = ""
        if "ioctl" in detail or "Inappropriate" in detail:
            hint = (
                "\n\ngpg could not prompt for the key passphrase because "
                "there is no terminal attached. Run this from an interactive "
                "shell, or configure a GUI pinentry."
            )
        raise SignerError(
            "gpg could not sign the statement of assent --- the attestation "
            f"would assert nothing without it:\n{detail}{hint}"
        )
    return out


def write(
    *,
    audit_root: Path,
    backend: str,
    pdf: Path,
    reference: str,
    signer_name: str,
    signer_key: str,
    gpg_key: str | None,
    when: _dt.datetime,
    timestamp: bool,
) -> tuple[Path, Attestation]:
    """Record one signing event. `pdf` must already be the final bytes."""
    directory = event_dir(audit_root, backend, pdf, reference, when.date())
    directory.mkdir(parents=True, exist_ok=True)

    retained = directory / pdf.name
    retained.write_bytes(pdf.read_bytes())

    sha256, sha3 = _attest().dual_hashes(retained)
    att = Attestation(
        reference=reference,
        document=pdf.name,
        sha256_b64=sha256,
        sha3_512_b64=sha3,
        signer_name=signer_name,
        signer_key=signer_key,
        gpg_key=gpg_key,
        signed_at=when.isoformat(timespec="seconds"),
        statement_file="statement.txt",
        signature_file=None,
        timestamp_file=None,
        signer_backend=backend,
    )

    statement = directory / "statement.txt"
    statement.write_text(render_statement(att), encoding="utf-8")

    try:
        signed = _clearsign(statement, gpg_key)
    except SignerError:
        # Leave no half-built record. The retained copy and the statement
        # were written before the signature was attempted; without the
        # signature they assert nothing, and a directory that looks like
        # an attestation but contains none is worse than no directory.
        shutil.rmtree(directory, ignore_errors=True)
        raise
    if signed is not None:
        att.signature_file = signed.name
        if timestamp:
            _attest()._timestamp(signed)
            ots = signed.with_name(signed.name + ".ots")
            if ots.exists():
                att.timestamp_file = ots.name

    (directory / "attestation.json").write_text(
        json.dumps(asdict(att), indent=2) + "\n", encoding="utf-8"
    )
    return directory, att


def verify(directory: Path, pubkey: Path | None = None) -> list[str]:
    """Re-check one recorded event. Returns human-readable problems.

    An empty list means the retained bytes still match both recorded
    digests and, where a public key was supplied, the statement's
    signature verifies against that key alone.
    """
    problems: list[str] = []
    meta_path = directory / "attestation.json"
    if not meta_path.is_file():
        return [f"{directory}: no attestation.json"]
    meta = json.loads(meta_path.read_text())

    retained = directory / meta["document"]
    if not retained.is_file():
        problems.append(
            f"attested document {meta['document']} is missing --- an "
            "attestation whose subject is gone asserts nothing"
        )
    else:
        sha256, sha3 = _attest().dual_hashes(retained)
        if sha256 != meta["sha256_b64"]:
            problems.append("SHA-256 of the retained document does not match")
        if sha3 != meta["sha3_512_b64"]:
            problems.append("SHA3-512 of the retained document does not match")

    sig = meta.get("signature_file")
    if not sig:
        problems.append("statement was never signed")
    elif pubkey is not None:
        # Against a throwaway keyring holding ONLY the expected key, per
        # ADR-0022. Verifying against the ambient keyring would accept a
        # signature by any key the operator happens to hold --- including
        # a well-meaning one of their own --- which is the failure mode
        # that makes verification feel done without being done.
        import tempfile

        with tempfile.TemporaryDirectory() as home:
            base = _attest()._isolated_gpg(Path(pubkey), home)
            proc = subprocess.run(
                [*base, "--verify", str(directory / sig)],
                capture_output=True, text=True,
            )
        if proc.returncode != 0:
            problems.append(
                f"statement signature does not verify against {pubkey}"
            )
    elif sig:
        problems.append(
            "signature present but not checked: pass --pubkey to verify it "
            "against a pinned key"
        )

    ots = meta.get("timestamp_file")
    if ots and (directory / ots).is_file():
        proc = subprocess.run(
            ["ots", "info", str(directory / ots)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and "pending" in proc.stdout.lower():
            problems.append(
                "timestamp is still a calendar-server commitment; run "
                "`ots upgrade` to obtain the Bitcoin attestation and keep "
                "the upgraded file"
            )
    return problems
