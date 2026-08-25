"""DocuSeal behind the `Signer` interface.

This is an adapter, not a reimplementation: `docuseal-client/` and
`sc docuseal send|status|fetch` already talk to the service, and this
class exists so the rest of the system can hold a `Signer` without caring
which one it holds.

Two things it does differently from `LocalSigner`, both required rather
than incidental.

**It is asynchronous.** `request()` returns PENDING with a submission
reference; the signed document exists once humans have acted, and `poll()`
is how you find out. Local signing can never return PENDING, and remote
signing can rarely return COMPLETED on the first call.

**It writes no attestation.** Per ADR-0036, DocuSeal issues its own
completion certificate with an audit trail of who signed, when, and from
where. If a dispute ever arose about a DocuSeal-signed document, the thing
to produce is *their* certificate. A second local record of the same
signing event is not redundancy --- it is two records that can disagree,
and the local one would be the weaker of the two. So
`produces_local_attestation` is False, and the completion certificate is
filed under `audit_log/signatures/docuseal/` when fetched.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .base import (
    Outcome,
    SignerError,
    SignRequest,
    SignResult,
    Signer,
    Slot,
)
from . import slots as slots_mod

_ROOT = Path(__file__).resolve().parent.parent


class DocuSealSigner(Signer):
    @property
    def name(self) -> str:
        return "docuseal"

    @property
    def produces_local_attestation(self) -> bool:
        return False

    def slots(self, pdf: Path) -> list[Slot]:
        """The same printed-text discovery the local signer uses.

        Useful before sending: the slots are where DocuSeal's own fields
        should be positioned, so seeing them locally is how you check that
        a document is ready to go out.
        """
        return slots_mod.discover(pdf)

    def request(self, req: SignRequest) -> SignResult:
        result = self._cli("send", str(req.pdf))
        return SignResult(
            outcome=Outcome.PENDING,
            reference=result.strip().splitlines()[-1] if result.strip() else "",
            detail=(
                "sent to DocuSeal; the signed document and its completion "
                "certificate exist once the signers have acted. No local "
                "attestation is written for remote signing (ADR-0036)."
            ),
        )

    def poll(self, reference: str) -> SignResult:
        out = self._cli("status", reference)
        done = "completed" in out.lower()
        return SignResult(
            outcome=Outcome.COMPLETED if done else Outcome.PENDING,
            reference=reference,
            detail=out.strip(),
        )

    def _cli(self, *args: str) -> str:
        entry = _ROOT / "docuseal-client" / "client.py"
        if not entry.is_file():
            raise SignerError(f"no DocuSeal client at {entry}")
        proc = subprocess.run(
            [sys.executable, str(entry), *args], capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise SignerError(f"docuseal {args[0]} failed: {proc.stderr.strip()}")
        return proc.stdout
