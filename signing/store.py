"""Where signature images live, and the one rule about it.

A signature image is the most abusable artifact this system touches:
possessing the file is functionally the ability to sign as that person.
So the store lives outside every repository, and `resolve()` refuses to
hand back a mark that sits inside a git work tree with a remote.

That guard is not paranoia about a hypothetical. This codebase is a fork
of a public repository with merges running between them, and the matter
repositories push to backup remotes. A signature committed once is a
signature published, and no later deletion unpublishes it.

Layout:

    ~/.config/prosaic/signatures/andrew_cone.pdf          the mark
    ~/.config/prosaic/signatures/andrew_cone.meta.yaml    who it belongs to

Override the directory with PROSAIC_SIGNATURE_DIR. A mark may be PDF
(preferred when the source is vector --- it renders at any resolution and
carries real transparency) or PNG/JPEG; see marks.py for how the
background is handled in each case.

The sidecar binds a mark to an identity:

    name: Andrew Cone
    gpg_key: F15991EE...1844

`sc sign apply --as andrew_cone` then needs neither `--name` nor
`--gpg-key`. That matters beyond convenience: the fingerprint typed on a
command line is the one thing in the attestation nobody would notice was
wrong, and a mark whose key is recorded once cannot later be signed with
somebody else's key by accident.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .base import SignerError

_ENV = "PROSAIC_SIGNATURE_DIR"
# PDF first: when a vector source exists it is the better one, so a store
# holding both andrew_cone.pdf and andrew_cone.png uses the PDF.
_SUFFIXES = (".pdf", ".PDF", ".png", ".PNG", ".jpg", ".jpeg", ".JPG", ".JPEG")


def store_dir() -> Path:
    override = os.environ.get(_ENV)
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "prosaic" / "signatures"


def _in_git_repo_with_remote(path: Path) -> str | None:
    """The remote URL, if `path` is inside a git work tree that has one.

    Uses -C on the containing directory so a bare path that does not yet
    exist cannot confuse rev-parse.
    """
    try:
        top = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if top.returncode != 0:
            return None
        remotes = subprocess.run(
            ["git", "-C", str(path.parent), "remote", "-v"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        # No git installed: nothing to check, and nothing to leak into.
        return None
    first = remotes.stdout.strip().splitlines()
    return first[0].strip() if first else None


def available() -> list[str]:
    d = store_dir()
    if not d.is_dir():
        return []
    keys = {p.stem for p in d.iterdir() if p.suffix in _SUFFIXES}
    return sorted(keys)


def metadata(key: str) -> dict[str, str]:
    """The mark's sidecar, or {} if it has none.

    Deliberately forgiving: a missing or malformed sidecar means the
    caller must supply `--name` and `--gpg-key`, which is a worse
    experience but not a broken one. A *wrong* sidecar is the dangerous
    case, and no amount of parsing strictness detects that.
    """
    path = store_dir() / f"{key}.meta.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {str(k): str(v) for k, v in loaded.items() if v is not None}


def resolve(key: str) -> Path:
    """The image file for a signature key, or a loud failure.

    Refuses a mark inside a git work tree with a remote --- see the module
    docstring. The refusal names the remote, because the useful next step
    is to move the file, and knowing where it would have gone is what
    makes that urgent.
    """
    if "/" in key or "\\" in key or key.startswith("."):
        raise SignerError(
            f"signature key {key!r} must be a bare name, not a path"
        )
    d = store_dir()
    for suffix in _SUFFIXES:
        candidate = d / f"{key}{suffix}"
        if candidate.is_file():
            remote = _in_git_repo_with_remote(candidate)
            if remote:
                raise SignerError(
                    f"refusing to use {candidate}: it is inside a git work "
                    f"tree with a remote ({remote}). A committed signature "
                    f"is a published signature. Move it to {store_dir()} "
                    f"(or set {_ENV}) and keep it out of version control."
                )
            return candidate

    have = available()
    hint = f" Available: {', '.join(have)}." if have else (
        f" The store {d} is empty or absent."
    )
    raise SignerError(f"no signature image for {key!r} in {d}.{hint}")
