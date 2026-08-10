"""SUM-100: Summons.

Fills the parts a plaintiff completes when having a summons issued: the
party names, the court, and the contact line. The clerk's date line and
the person-served items at the foot are completed at issuance and at
service respectively, so they stay blank here. Three of the form's
embedded tooltips are stale text from the cross-complaint summons; the
mapping follows the printed form.
"""

from __future__ import annotations

from dataclasses import dataclass

from prosaic.forms.pack import FormValidationError
from prosaic.model import Matter, PartyRole
from prosaic.packs.civil.caption import caption_for, caption_problems

NUMBER = "SUM-100"
TITLE = "Summons"

_PREFIX = "SUM-100[0].Page1[0]"


@dataclass(frozen=True, slots=True)
class SummonsContext:
    """Issued at the request of one plaintiff-side party."""

    filer_party_id: str


def build_values(matter: Matter, context: SummonsContext) -> dict[str, str | bool]:
    filer = matter.party(context.filer_party_id)

    problems = caption_problems(matter, filer)
    if filer.role not in (PartyRole.PLAINTIFF, PartyRole.PETITIONER):
        problems.append(f"summons is issued for a plaintiff; {filer.id} is a {filer.role}")
    caption = caption_for(matter, filer)
    if not caption.defendants:
        problems.append("matter has no defendants to name in the notice")
    if not caption.plaintiffs:
        problems.append("matter has no plaintiffs")
    if problems:
        raise FormValidationError(NUMBER, problems)

    # The first court line is a narrow field beside the case-number box and
    # clips at about 38 characters, so the county joins the address line.
    court_line = "Superior Court of California,"
    court_rest = (
        f"County of {matter.court.county}, {caption.court_street}, {caption.court_city_zip}"
    )
    contact = ", ".join(
        part
        for part in (
            caption.attorney_lines[0],
            caption.attorney_lines[1],
            caption.attorney_lines[2],
            caption.telephone,
        )
        if part
    )
    return {
        f"{_PREFIX}.Notice[0].FillText25[0]": caption.defendants,
        f"{_PREFIX}.Notice[0].FillText180[0]": caption.plaintiffs,
        f"{_PREFIX}.Info[0].FillText3[0]": court_line,
        f"{_PREFIX}.Info[0].FillText2[0]": court_rest,
        f"{_PREFIX}.Info[0].CaseNumber[0].FillText26[0]": caption.case_number,
        f"{_PREFIX}.Info[0].FillText30[0]": contact,
    }
