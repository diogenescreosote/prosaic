"""CM-110: Case Management Statement.

The form runs 19 items over five pages; this module completes a subset
and leaves the rest blank: the caption (including the hearing notice
box), the UNLIMITED/LIMITED title checkboxes, item 1a (statement
submitted by one party), item 2a (complaint filing date), item 3a (all
parties served, appeared, or dismissed), item 4a (type of case as
pleaded in the complaint), item 5 (jury or nonjury trial), the item
10c(1) willing-to-participate-in-mediation checkbox, and the signature
block's date and first name line.

Quirks of the official form (rev. January 1, 2024): the short-caption
header fields on pages 2 through 5 are read-only text fields the form
computes from page 1, so they take no values here; a single date field
serves both signature name lines; and several partial names repeat
under different parents, so every field is addressed fully qualified.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from prosaic.forms.pack import FormValidationError
from prosaic.model import Matter
from prosaic.packs.civil.caption import (
    attorney_block_fields,
    caption_for,
    caption_problems,
    court_block_fields,
)
from prosaic.packs.civil.cm010 import AmountDemanded

NUMBER = "CM-110"
TITLE = "Case Management Statement"

_PAGE1 = "CM-110[0].Page1[0]"
_CAPTION = f"{_PAGE1}.P1Caption[0]"
_MEDIATION_WILLING = "CM-110[0].Page3[0].List10[0].Lic[0].Table1[0].Row1[0].sub1[0].limitedch[0]"
_SIGN = "CM-110[0].Page5[0].Sign[0]"


@dataclass(frozen=True, slots=True)
class CaseManagementContext:
    """One party's statement for an upcoming case management conference."""

    filer_party_id: str
    amount: AmountDemanded
    case_description: str
    signed_on: datetime.date
    hearing: datetime.datetime | None = None
    department: str = ""
    complaint_filed: datetime.date | None = None
    all_parties_served: bool = False
    requests_jury_trial: bool = False
    willing_to_mediate: bool = False


def build_values(matter: Matter, context: CaseManagementContext) -> dict[str, str | bool]:
    filer = matter.party(context.filer_party_id)

    problems = caption_problems(matter, filer)
    if not context.case_description.strip():
        problems.append("item 4a needs a description of the case; got none")
    if not matter.case_number:
        problems.append("a case management statement responds to a filed case; no case number")
    if problems:
        raise FormValidationError(NUMBER, problems)

    caption = caption_for(matter, filer)
    counsel = next((c for c in matter.counsel if filer.id in c.represents), None)
    signatory = counsel.name if counsel is not None else filer.name.value

    values: dict[str, str | bool] = {
        **attorney_block_fields(f"{_CAPTION}.AttyPartyInfo[0]", matter, filer),
        **court_block_fields(f"{_CAPTION}.CourtInfo[0]", caption),
        f"{_CAPTION}.TitlePartyName[0].Party1[0]": caption.plaintiffs,
        f"{_CAPTION}.TitlePartyName[0].Party2[0]": caption.defendants,
        f"{_CAPTION}.captionSub[0].CaseNumber[0].caseNumber[0]": caption.case_number,
        f"{_CAPTION}.FormTitle[0].limit12[0]"
        if context.amount is AmountDemanded.UNLIMITED
        else f"{_CAPTION}.FormTitle[0].limit12[1]": (
            "/1" if context.amount is AmountDemanded.UNLIMITED else "/2"
        ),
        f"{_PAGE1}.Note[0].Date1[0]": (
            context.hearing.strftime("%B %-d, %Y") if context.hearing else ""
        ),
        f"{_PAGE1}.Note[0].Time1[0]": (
            context.hearing.strftime("%-I:%M %p") if context.hearing else ""
        ),
        f"{_PAGE1}.Note[0].Dept1[0]": context.department,
        f"{_PAGE1}.List1[0].Lia[0].partystatement1[0]": "/1",
        f"{_PAGE1}.List1[0].Lia[0].TextField2[0]": filer.name.value,
        f"{_PAGE1}.List2[0].Lia[0].Date3[0]": (
            context.complaint_filed.strftime("%B %-d, %Y") if context.complaint_filed else ""
        ),
        f"{_PAGE1}.List4[0].Lia[0].Ch10[0]": "/Yes",
        f"{_PAGE1}.List4[0].Lia[0].FillText11[0]": context.case_description,
        "CM-110[0].Page2[0].List5[0].item5[0].jurytrial1[0]"
        if context.requests_jury_trial
        else "CM-110[0].Page2[0].List5[0].item5[0].jurytrial1[1]": (
            "/1" if context.requests_jury_trial else "/2"
        ),
        f"{_SIGN}.SigDate1[0]": context.signed_on.strftime("%B %-d, %Y"),
        f"{_SIGN}.SigName1[0]": signatory,
    }
    if context.all_parties_served:
        values[f"{_PAGE1}.List3[0].Lia[0].limitedee[0]"] = "/1"
    if context.willing_to_mediate:
        values[_MEDIATION_WILLING] = "/1"
    return values
