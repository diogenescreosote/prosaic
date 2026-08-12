"""The attestation protocol's promises, exercised against real gpg.

What is pinned here is the protocol, not gpg: verification succeeds
only against the named key file (a keyring is not a trust anchor),
tampering one byte fails the verify, a manifest vouches for exact
bytes, and hashes match independently computed values. Tests skip
without gpg; nothing else in the suite needs it.
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ATTEST = REPO_ROOT / "crypto" / "attest.py"

pytestmark = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg not installed")


def run_attest(
    *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ATTEST), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


@pytest.fixture(scope="module")
def signer() -> Iterator[dict[str, str]]:
    """A throwaway signing key in an isolated GNUPGHOME.

    tempfile.mkdtemp, not tmp_path: gpg-agent binds a unix socket
    inside the home directory, and pytest tmp paths overflow the
    socket path limit (~104 bytes on macOS).
    """
    home = Path(tempfile.mkdtemp(prefix="attest"))
    gnupg = home / "gnupg"
    gnupg.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(gnupg), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
    gen = subprocess.run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-gen-key",
            "Test Signer <signer@example.com>",
            "ed25519",
            "sign",
            "1y",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert gen.returncode == 0, gen.stderr
    pubkey = home / "pubkey.asc"
    exp = subprocess.run(
        ["gpg", "--batch", "--armor", "--export", "signer@example.com"],
        capture_output=True,
        text=True,
        env=env,
    )
    pubkey.write_text(exp.stdout)
    yield {
        "home": str(home),
        "pubkey": str(pubkey),
        "uid": "signer@example.com",
        "GNUPGHOME": str(gnupg),
        "PATH": env["PATH"],
    }
    shutil.rmtree(home, ignore_errors=True)


def sign_env(signer: dict[str, str]) -> dict[str, str]:
    return {"GNUPGHOME": signer["GNUPGHOME"], "PATH": signer["PATH"]}


def test_hash_matches_independent_computation(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_bytes(b"known content\n")
    proc = run_attest("hash", "doc.txt", cwd=tmp_path)
    assert proc.returncode == 0
    expected256 = base64.b64encode(hashlib.sha256(b"known content\n").digest()).decode()
    expected3 = base64.b64encode(hashlib.sha3_512(b"known content\n").digest()).decode()
    assert expected256 in proc.stdout
    assert expected3 in proc.stdout


def test_sign_verify_round_trip(tmp_path: Path, signer: dict[str, str]) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("the operative document\n")
    proc = run_attest("sign", "doc.txt", "--key", signer["uid"], cwd=tmp_path, env=sign_env(signer))
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "doc.txt.sig.asc").exists()

    proc = run_attest(
        "verify", "doc.txt", "--pubkey", signer["pubkey"], cwd=tmp_path, env=sign_env(signer)
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "VERIFIED" in proc.stdout


def test_one_flipped_byte_fails_verification(tmp_path: Path, signer: dict[str, str]) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("the operative document\n")
    run_attest("sign", "doc.txt", "--key", signer["uid"], cwd=tmp_path, env=sign_env(signer))
    doc.write_text("the operative document?\n")
    proc = run_attest(
        "verify", "doc.txt", "--pubkey", signer["pubkey"], cwd=tmp_path, env=sign_env(signer)
    )
    assert proc.returncode == 1
    assert "FAILED" in proc.stdout


def test_verification_is_pinned_to_the_named_key(tmp_path: Path, signer: dict[str, str]) -> None:
    """A good signature by the WRONG key must fail: the paper-anchored
    key is the trust anchor, not whatever a keyring contains."""
    doc = tmp_path / "doc.txt"
    doc.write_text("content\n")
    run_attest("sign", "doc.txt", "--key", signer["uid"], cwd=tmp_path, env=sign_env(signer))

    other_home = Path(tempfile.mkdtemp(prefix="attesto"))
    other_gnupg = other_home / "g"
    other_gnupg.mkdir(mode=0o700)
    env = {"GNUPGHOME": str(other_gnupg), "PATH": signer["PATH"]}
    subprocess.run(
        [
            "gpg",
            "--batch",
            "--pinentry-mode",
            "loopback",
            "--passphrase",
            "",
            "--quick-gen-key",
            "Other <other@example.com>",
            "ed25519",
            "sign",
            "1y",
        ],
        capture_output=True,
        env=env,
        check=True,
    )
    exp = subprocess.run(
        ["gpg", "--batch", "--armor", "--export", "other@example.com"],
        capture_output=True,
        text=True,
        env=env,
    )
    other_key = tmp_path / "other.asc"
    other_key.write_text(exp.stdout)

    proc = run_attest(
        "verify", "doc.txt", "--pubkey", str(other_key), cwd=tmp_path, env=sign_env(signer)
    )
    shutil.rmtree(other_home, ignore_errors=True)
    assert proc.returncode == 1
    assert "FAILED" in proc.stdout


def test_manifest_round_trip_and_tamper_detection(tmp_path: Path, signer: dict[str, str]) -> None:
    (tmp_path / "a.txt").write_text("alpha\n")
    (tmp_path / "b.txt").write_text("beta\n")
    proc = run_attest(
        "manifest",
        "write",
        "MANIFEST.md",
        "a.txt",
        "b.txt",
        "--key",
        signer["uid"],
        cwd=tmp_path,
        env=sign_env(signer),
    )
    assert proc.returncode == 0, proc.stderr

    proc = run_attest(
        "manifest",
        "verify",
        "MANIFEST.md",
        "--pubkey",
        signer["pubkey"],
        cwd=tmp_path,
        env=sign_env(signer),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("ok:") == 2

    (tmp_path / "b.txt").write_text("beta, revised\n")
    proc = run_attest(
        "manifest",
        "verify",
        "MANIFEST.md",
        "--pubkey",
        signer["pubkey"],
        cwd=tmp_path,
        env=sign_env(signer),
    )
    assert proc.returncode == 1
    assert "HASH MISMATCH: b.txt" in proc.stdout


def test_edited_manifest_fails_signature_verification(
    tmp_path: Path, signer: dict[str, str]
) -> None:
    """The mutable pointer is mutable only by the keyholder: editing a
    hash row inside the signed manifest breaks the clearsign."""
    (tmp_path / "a.txt").write_text("alpha\n")
    run_attest(
        "manifest",
        "write",
        "MANIFEST.md",
        "a.txt",
        "--key",
        signer["uid"],
        cwd=tmp_path,
        env=sign_env(signer),
    )
    manifest = tmp_path / "MANIFEST.md"
    manifest.write_text(
        manifest.read_text().replace("alpha", "omega", 1).replace("| a.txt |", "| c.txt |")
    )
    proc = run_attest(
        "manifest",
        "verify",
        "MANIFEST.md",
        "--pubkey",
        signer["pubkey"],
        cwd=tmp_path,
        env=sign_env(signer),
    )
    assert proc.returncode == 1
    assert "signature does not verify" in proc.stderr
