"""MC-030: Declaration.

Field names verified against the widget geometry of the official form
(rev. January 1, 2006) and its rendered layout. The capacity boxes at the
foot are one standalone checkbox ("Attorney for") plus a five-way radio
group whose on-states run /1 Plaintiff, /2 Petitioner, /3 Defendant,
/4 Respondent, /5 Other.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from prosaic.forms.pack import FormValidationError
from prosaic.model import Matter, PartyRole
from prosaic.packs.civil.caption import caption_for, caption_problems

NUMBER = "MC-030"
TITLE = "Declaration"

_CAPACITY_STATE = {
    PartyRole.PLAINTIFF: "/1",
    PartyRole.PETITIONER: "/2",
    PartyRole.DEFENDANT: "/3",
    PartyRole.RESPONDENT: "/4",
}


@dataclass(frozen=True, slots=True)
class DeclarationContext:
    """One declaration: who declares, what they say, when they signed."""

    declarant_party_id: str
    body: str
    signed_on: datetime.date


def build_values(matter: Matter, context: DeclarationContext) -> dict[str, str | bool]:
    declarant = matter.party(context.declarant_party_id)

    problems = caption_problems(matter, declarant)
    if not context.body.strip():
        problems.append("declaration body is empty")
    if not matter.case_number:
        problems.append("matter has no case number")
    if problems:
        raise FormValidationError(NUMBER, problems)

    caption = caption_for(matter, declarant)
    capacity = _CAPACITY_STATE.get(declarant.role, "/5")
    values: dict[str, str | bool] = {
        "FillText35": caption.attorney_lines[0],
        "FillText34": caption.attorney_lines[1],
        "FillText32": caption.attorney_lines[2],
        "FillText31": caption.telephone,
        "FillText30": caption.fax,
        "FillText36": caption.email,
        "FillText29": caption.attorney_for,
        "FillText27": caption.court_county,
        "FillText26": caption.court_street,
        "FillText25": caption.court_mailing,
        "FillText24": caption.court_city_zip,
        "FillText23": caption.court_branch,
        "FillText22": caption.plaintiffs,
        "FillText21": caption.defendants,
        "FillText15": caption.case_number,
        "FillText19": context.body,
        "FillText20": context.signed_on.strftime("%B %-d, %Y"),
        "FillText18": declarant.name.value,
        "CheckBx 2": capacity,
    }
    if capacity == "/5":
        values["FillText1885"] = declarant.role.value.replace("_", "-")
    return values
