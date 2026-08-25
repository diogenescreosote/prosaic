"""Signing backends behind one interface (ADR-0036).

    from signing import get_signer, SignRequest
    signer = get_signer("local")
    result = signer.request(SignRequest(pdf=..., signer_key="andrew_cone", ...))

`get_signer` is the only place a backend name turns into a class, so
adding DocuSign means adding a module and one entry here.
"""

from __future__ import annotations

from .base import (
    Outcome,
    Signer,
    SignerError,
    SignRequest,
    SignResult,
    Slot,
    SlotRole,
)

__all__ = [
    "Outcome",
    "Signer",
    "SignerError",
    "SignRequest",
    "SignResult",
    "Slot",
    "SlotRole",
    "get_signer",
    "backends",
]


def backends() -> tuple[str, ...]:
    return ("local", "docuseal")


def get_signer(name: str, **kwargs) -> Signer:
    if name == "local":
        from .local import LocalSigner

        return LocalSigner(**kwargs)
    if name == "docuseal":
        from .docuseal import DocuSealSigner

        return DocuSealSigner()
    raise SignerError(
        f"unknown signing backend {name!r}; have {', '.join(backends())}"
    )
