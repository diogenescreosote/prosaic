"""MC-031: Attached Declaration.

The continuation counterpart of MC-030: a short-title caption instead of
the full attorney block, because the form attaches to another paper. The
six capacity checkboxes are independent fields (each with on-state /1),
unlike MC-030's radio group.
"""

from __future__ import annotations

from prosaic.forms.pack import FormValidationError
from prosaic.model import Matter, PartyRole
from prosaic.packs.civil.caption import caption_for, caption_problems
from prosaic.packs.civil.mc030 import DeclarationContext

NUMBER = "MC-031"
TITLE = "Attached Declaration"

_CAPACITY_FIELD = {
    PartyRole.PLAINTIFF: "CheckBox6",
    PartyRole.PETITIONER: "CheckBx6",
    PartyRole.DEFENDANT: "ChckBox6",
    PartyRole.RESPONDENT: "Chck6",
}


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
    values: dict[str, str | bool] = {
        "FillText10": caption.plaintiffs,
        "FillText9": caption.defendants,
        "FillText11": caption.case_number,
        "FillText8": context.body,
        "FillText14": context.signed_on.strftime("%B %-d, %Y"),
        "FillText7": declarant.name.value,
    }
    capacity_field = _CAPACITY_FIELD.get(declarant.role)
    if capacity_field is None:
        values["Ck6"] = True
        values["FillText13"] = declarant.role.value.replace("_", "-")
    else:
        values[capacity_field] = True
    return values
