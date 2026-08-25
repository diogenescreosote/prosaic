"""Signing here, on this machine, with a stored signature image.

This is the backend ADR-0036 describes: it takes one already-built PDF,
draws the signature and the date into the blanks the build left, stamps a
reference nonce, writes a *new* file, and attests those exact bytes.

It deliberately does not participate in the build. `sc build --sign NAME`
already exists and renders a cursive *font* into signature blocks; that is
a convenience for drafts and produces no attestation, no reference and no
retained artifact. The two are different operations and should not be
confused: one makes a document look signed, this one records that a
person signed it.

Because the artifact is what gets attested, the output file is never the
input file and never lands in a build directory --- `out/` is destroyed by
the next `make`, and signatures saved there have been lost that way
before.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import fitz

from . import audit, marks, slots as slots_mod, stamp, store
from .base import (
    Outcome,
    SignerError,
    SignRequest,
    SignResult,
    Signer,
    Slot,
    SlotRole,
)

# Pleading body type. The date written into a blank should look like the
# sentence around it, not like a form fill.
_BODY_FONT = "tiro"
_BODY_SIZE = 12.0


_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{_ORDINAL_SUFFIX.get(n % 10, 'th')}"


def _slot_text(role: SlotRole, when: _dt.date, name: str, location: str) -> str | None:
    return {
        SlotRole.DAY_ORDINAL: _ordinal(when.day),
        SlotRole.DAY_CARDINAL: str(when.day),
        SlotRole.MONTH_NAME: when.strftime("%B"),
        SlotRole.YEAR_FULL: str(when.year),
        SlotRole.YEAR_TWO_DIGIT: f"{when.year % 100:02d}",
        SlotRole.DATE_FULL: f"{when.strftime('%B')} {when.day}, {when.year}",
        SlotRole.NAME_PRINTED: name,
        SlotRole.LOCATION: location,
    }.get(role)


class LocalSigner(Signer):
    def __init__(self, include_form_lines: bool = False) -> None:
        self._include_form_lines = include_form_lines

    @property
    def name(self) -> str:
        return "local"

    @property
    def produces_local_attestation(self) -> bool:
        return True

    def slots(self, pdf: Path) -> list[Slot]:
        found = slots_mod.discover(pdf)
        if self._include_form_lines:
            found += slots_mod.jc_signature_lines(pdf)
        return sorted(found, key=lambda s: (s.page, s.rect[1], s.rect[0]))

    def request(self, req: SignRequest) -> SignResult:
        if not req.pdf.is_file():
            raise SignerError(f"no such document: {req.pdf}")
        if req.audit_root is None:
            raise SignerError(
                "no audit root: the attestation has nowhere to go, and an "
                "unrecorded signature is what this backend exists to avoid"
            )

        image = store.resolve(req.signer_key)
        mark = marks.prepare(image)

        found = self.slots(req.pdf)
        marks_found = [s for s in found if s.role is SlotRole.SIGNATURE_MARK]
        if not marks_found:
            raise SignerError(
                f"{req.pdf.name} has no signature line. Signature blocks are "
                "found by their printed text, so a document built before "
                "\\signblock existed, or one whose blocks were removed, "
                "offers nothing to sign. Run with --slots to see what was "
                "found."
            )

        out = self._output_path(req)
        when = _dt.datetime.now().astimezone()

        with fitz.open(req.pdf) as doc:
            for slot in found:
                page = doc[slot.page]
                if slot.role is SlotRole.SIGNATURE_MARK:
                    rect = marks.place_rect(mark, slot.rect)
                    page.insert_image(fitz.Rect(*rect), stream=mark.png,
                                      keep_proportion=True, overlay=True)
                    continue
                text = _slot_text(slot.role, req.date, req.signer_name, "")
                if not text:
                    continue
                x0, _y0, _x1, y1 = slot.rect
                page.insert_text(
                    (x0 + 1.0, y1 - 1.5),
                    text,
                    fontname=_BODY_FONT,
                    fontsize=_BODY_SIZE,
                    color=(0, 0, 0),
                )

            reference = stamp.new_nonce()
            skipped = stamp.apply(doc, reference)
            out.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(out), garbage=3, deflate=True)

        if skipped:
            pages = ", ".join(str(p + 1) for p in skipped)
            print(
                f"  note: no clear space for the reference stamp on page(s) "
                f"{pages}; those pages carry no stamp",
            )

        directory, att = audit.write(
            audit_root=req.audit_root,
            backend=self.name,
            pdf=out,
            reference=reference,
            signer_name=req.signer_name,
            signer_key=req.signer_key,
            gpg_key=req.gpg_key,
            when=when,
            timestamp=req.timestamp,
        )
        return SignResult(
            outcome=Outcome.COMPLETED,
            signed_pdf=out,
            attestation_dir=directory,
            reference=reference,
            detail=(
                f"{len(marks_found)} signature(s), "
                f"{len(found) - len(marks_found)} date field(s); "
                f"attested as {att.reference}"
            ),
        )

    # -- output location ---------------------------------------------------

    def _output_path(self, req: SignRequest) -> Path:
        if req.output:
            out = Path(req.output)
        else:
            root = _matter_root(req.pdf) or req.pdf.parent.parent
            out = (
                root
                / "staging"
                / f"{req.date.isoformat()}_{req.pdf.stem}_SIGNED.pdf"
            )
        if out.resolve() == req.pdf.resolve():
            raise SignerError(
                "refusing to sign a document in place: the unsigned build is "
                "the only thing that can be rebuilt, and the signed artifact "
                "is the only thing that can be attested"
            )
        if "out" in out.resolve().parts:
            raise SignerError(
                f"refusing to write a signed document into a build directory "
                f"({out}). The next build destroys it --- which is how signed "
                "documents have been lost here before. Pass -o, or let the "
                "default staging/ location be used."
            )
        return out


def _matter_root(start: Path) -> Path | None:
    """Nearest ancestor containing matter.yaml."""
    for parent in [start.resolve(), *start.resolve().parents]:
        if (parent / "matter.yaml").is_file():
            return parent
    return None
