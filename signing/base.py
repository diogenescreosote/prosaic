"""The signing interface every backend implements (ADR-0036).

The rest of the system talks to `Signer`, never to a backend. Today there
are two: `LocalSigner`, which applies a stored signature mark to a built
PDF here on this machine and attests the result, and `DocuSealSigner`,
which hands the document to a remote service and waits for humans.
DocuSign and others slot in the same way.

The two differ in a way the interface has to model honestly rather than
paper over: local signing is synchronous and returns a finished artifact,
while remote signing returns a receipt and completes minutes or days
later. So `request()` returns an outcome that is either COMPLETED --- the
signed file is on disk --- or PENDING, and a pending request is resolved
by `poll()`. A backend that can never be pending simply never returns it.

They also differ in what they may claim. Per ADR-0036 the local signer
produces a cryptographic attestation of its own output; a remote service
issues its own completion certificate and audit trail, and a second,
competing local record of the same signing event is worse than one
record. `produces_local_attestation` states which kind a backend is, so
callers never have to special-case on the backend's name.
"""

from __future__ import annotations

import datetime as _dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class SlotRole(str, Enum):
    """What a discovered blank wants written in it.

    The vocabulary is explicit about *form* as well as content, because
    the surrounding printed text is not interchangeable: "Executed this
    _____ day of" wants an ordinal, and a bare "Dated: ______" wants a
    whole date. Encoding which is which is the point --- the alternative
    is a human remembering at signing time, which is how an unmapped
    checkbox once stayed blank for the life of a form descriptor.
    """

    SIGNATURE_MARK = "signature_mark"
    DAY_ORDINAL = "day_ordinal"
    DAY_CARDINAL = "day_cardinal"
    MONTH_NAME = "month_name"
    YEAR_FULL = "year_full"
    YEAR_TWO_DIGIT = "year_two_digit"
    DATE_FULL = "date_full"
    NAME_PRINTED = "name_printed"
    LOCATION = "location"


@dataclass(frozen=True)
class Slot:
    """A place on a built PDF where signing writes something.

    `rect` is (x0, y0, x1, y1) in PDF points, top-left origin, as PyMuPDF
    reports it. `page` is zero-based. `anchor` records the printed text
    the slot was located from, so a failure to place is debuggable
    without opening the file.
    """

    page: int
    role: SlotRole
    rect: tuple[float, float, float, float]
    anchor: str = ""

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]


@dataclass
class SignRequest:
    """One document, one signer identity, one intent to be bound."""

    pdf: Path
    # Key into the signature store: `sc sign --as andrew_cone`.
    signer_key: str
    # The legal name printed beneath the mark, and the name the statement
    # of assent speaks in. Not necessarily the store key.
    signer_name: str
    # Date of execution written into the signature block. Defaults to
    # today at request time; overridable because a document may be
    # executed on a date the operator is reconstructing.
    date: _dt.date = field(default_factory=_dt.date.today)
    # GPG key (fingerprint or any gpg --local-user selector). None uses
    # gpg's default key, which is fine for a single-key keyring and a
    # footgun otherwise, so the CLI asks for it explicitly.
    gpg_key: str | None = None
    # Where the attestation record is written. Resolved by the caller so
    # this module never has to guess a matter's layout.
    audit_root: Path | None = None
    # Explicit destination for the signed artifact. When None the backend
    # picks one, and must not pick the input or a build directory.
    output: Path | None = None
    # Skip OpenTimestamps. The proof is worth having, but it needs the
    # network and a later `ots upgrade`, so it must be declinable.
    timestamp: bool = True


class Outcome(str, Enum):
    COMPLETED = "completed"
    PENDING = "pending"


@dataclass
class SignResult:
    outcome: Outcome
    # The signed artifact, when there is one. PENDING results have none.
    signed_pdf: Path | None = None
    # Directory holding the attestation, when the backend makes one.
    attestation_dir: Path | None = None
    # How a human refers to this signing event: the stamp nonce for
    # local signing, the submission id for a remote service.
    reference: str = ""
    detail: str = ""


class SignerError(RuntimeError):
    """A signing attempt failed in a way the operator must see.

    Raised rather than returned, because a half-signed document is not a
    result --- there is nothing a caller could usefully do with one.
    """


class Signer(ABC):
    """A backend that can put someone's signature on a document."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short stable identifier: 'local', 'docuseal'. Names the audit
        subdirectory, so it must not change once records exist."""

    @property
    @abstractmethod
    def produces_local_attestation(self) -> bool:
        """Whether this backend writes its own cryptographic attestation
        of the signed bytes (ADR-0036). False for services that issue
        their own certificate."""

    @abstractmethod
    def slots(self, pdf: Path) -> list[Slot]:
        """Every signature-block blank found in a built PDF.

        Read-only, and useful on its own: run it to see what a document
        offers before signing anything.
        """

    @abstractmethod
    def request(self, req: SignRequest) -> SignResult:
        """Sign, or ask for signature. See Outcome."""

    def poll(self, reference: str) -> SignResult:
        """Resolve a PENDING request. Synchronous backends never need it."""
        raise SignerError(
            f"{self.name} completes synchronously; there is nothing to poll"
        )
