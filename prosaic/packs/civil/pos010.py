"""POS-010: Proof of Service of Summons.

Field names verified against the official form (rev. January 1, 2007)
and its rendered layout. The form's mutually exclusive choices (manner
of service in item 5, the notice basis in item 6, declaration versus
sheriff's certification in items 8/9) are not radio groups: each option
is a separate checkbox field whose on-state happens to be numbered
/1-/4, so exclusivity is this module's job and exactly one is set. The
caption's ATTORNEY FOR field is literally named ``Nmae[0]`` in the PDF.
Item 2 offers one checkbox per common document plus 2f "other"; the
served titles go verbatim into 2f rather than being matched against the
preprinted labels. The page-2 header caption fields are read-only
(Acrobat copies them from page 1 by form script), so they are not
fillable here and stay blank. Only personal service (item 5a) by a
non-registered server (item 7e(1)) is implemented, and the server
always declares under penalty of perjury (item 8), never as sheriff or
marshal (item 9).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

from prosaic.forms.pack import FormValidationError
from prosaic.model import Address, Matter, PartyRole
from prosaic.packs.civil.caption import caption_for, caption_problems, court_block_fields

NUMBER = "POS-010"
TITLE = "Proof of Service of Summons"

_P1_CAPTION = "POS-010[0].Page1[0].P1Caption[0]"
_PAGE1 = "POS-010[0].Page1[0]"
_PAGE2 = "POS-010[0].Page2[0]"
_LIST6 = "POS-010[0].Page2[0].List6[0]"
_LIST7 = "POS-010[0].Page2[0].List7[0]"

_DEFENDANT_SIDE = {PartyRole.DEFENDANT, PartyRole.RESPONDENT, PartyRole.CROSS_DEFENDANT}


class NoticeBasis(StrEnum):
    """How the summons's "Notice to the Person Served" box was completed."""

    INDIVIDUAL = "individual"
    FICTITIOUS_NAME = "fictitious_name"
    ON_BEHALF_OF_ENTITY = "on_behalf_of_entity"


class EntityServiceSection(StrEnum):
    """The CCP section item 6d names for service on behalf of an entity."""

    CORPORATION_416_10 = "416.10"
    DEFUNCT_CORPORATION_416_20 = "416.20"
    ASSOCIATION_OR_PARTNERSHIP_416_40 = "416.40"
    MINOR_416_60 = "416.60"
    WARD_OR_CONSERVATEE_416_70 = "416.70"
    AUTHORIZED_PERSON_416_90 = "416.90"
    OTHER = "other"


_SECTION_CHECKBOX = {
    EntityServiceSection.CORPORATION_416_10: "CheckBox55[0]",
    EntityServiceSection.DEFUNCT_CORPORATION_416_20: "CheckBox56[0]",
    EntityServiceSection.ASSOCIATION_OR_PARTNERSHIP_416_40: "CheckBox58[0]",
    EntityServiceSection.MINOR_416_60: "CheckBox61[0]",
    EntityServiceSection.WARD_OR_CONSERVATEE_416_70: "CheckBox62[0]",
    EntityServiceSection.AUTHORIZED_PERSON_416_90: "CheckBox63[0]",
    EntityServiceSection.OTHER: "CheckBox65[0]",
}


@dataclass(frozen=True, slots=True)
class ProofOfServiceContext:
    """One completed personal service, as the server will swear to it."""

    filer_party_id: str
    served_party_id: str
    documents_served: tuple[str, ...]
    service_address: Address
    served_at: datetime.datetime
    notice_basis: NoticeBasis
    server_name: str
    server_address: Address
    server_phone: str
    signed_on: datetime.date
    fee_for_service: str = ""
    fictitious_name: str = ""
    entity_ccp_section: EntityServiceSection | None = None
    other_ccp_section: str = ""
    server_is_registered: bool = False


def _one_line(address: Address) -> str:
    return f"{address.street}, {address.city}, {address.state} {address.zip_code}"


def build_values(matter: Matter, context: ProofOfServiceContext) -> dict[str, str | bool]:
    filer = matter.party(context.filer_party_id)
    served = matter.party(context.served_party_id)

    problems = caption_problems(matter, filer)
    if not matter.case_number:
        problems.append("matter has no case number")
    if served.role not in _DEFENDANT_SIDE:
        problems.append(
            f"service of summons is proved on a defendant; {served.id} is a {served.role}"
        )
    if not context.documents_served:
        problems.append("item 2 lists the documents served; none were given")
    if context.server_is_registered:
        problems.append(
            "registered process servers are not supported: "
            "item 7e(3) needs registration details this context does not carry"
        )
    if context.notice_basis is NoticeBasis.FICTITIOUS_NAME and not context.fictitious_name:
        problems.append("fictitious-name service gives the fictitious name for items 3b and 6b")
    if (
        context.notice_basis is NoticeBasis.ON_BEHALF_OF_ENTITY
        and context.entity_ccp_section is None
    ):
        problems.append("service on behalf of an entity names the CCP section in item 6d")
    if context.entity_ccp_section is EntityServiceSection.OTHER and not context.other_ccp_section:
        problems.append("an 'other' CCP section in item 6d spells out the section relied on")
    if problems:
        raise FormValidationError(NUMBER, problems)

    caption = caption_for(matter, filer)
    signed = context.signed_on.strftime("%B %-d, %Y")
    values: dict[str, str | bool] = {
        f"{_P1_CAPTION}.AttyPartyInfo[0].TextField1[0]": "\n".join(caption.attorney_lines),
        f"{_P1_CAPTION}.AttyPartyInfo[0].Phone[0]": caption.telephone,
        f"{_P1_CAPTION}.AttyPartyInfo[0].Fax[0]": caption.fax,
        f"{_P1_CAPTION}.AttyPartyInfo[0].Email[0]": caption.email,
        f"{_P1_CAPTION}.AttyPartyInfo[0].Nmae[0]": caption.attorney_for,
        **court_block_fields(f"{_P1_CAPTION}.CourtInfo[0]", caption),
        f"{_P1_CAPTION}.TitlePartyName[0].Party1[0]": caption.plaintiffs,
        f"{_P1_CAPTION}.TitlePartyName[0].Party2[0]": caption.defendants,
        f"{_P1_CAPTION}.CaseNumber1[0].CaseNumber[0]": caption.case_number,
        f"{_PAGE1}.List2[0].Lif[0].limited124[0]": "/1",
        f"{_PAGE1}.List2[0].Lif[0].TextField66[0]": ", ".join(context.documents_served),
        f"{_PAGE1}.List3[0].Lia[0].FillText1[0]": served.name.value,
        f"{_PAGE1}.List4[0].item4[0].FillText18[0]": _one_line(context.service_address),
        f"{_PAGE1}.List5[0].Lia[0].Ch1[0]": "/1",
        f"{_PAGE1}.List5[0].Lia[0].SubLista[0].LI1[0].FillText20[0]": (
            context.served_at.strftime("%B %-d, %Y")
        ),
        f"{_PAGE1}.List5[0].Lia[0].SubLista[0].LI2[0].FillText21[0]": (
            context.served_at.strftime("%-I:%M %p")
        ),
        f"{_LIST7}.Lia[0].Field1[0]": context.server_name,
        f"{_LIST7}.Lib[0].Field2[0]": _one_line(context.server_address),
        f"{_LIST7}.Lic[0].Field3[0]": context.server_phone,
        f"{_LIST7}.Lid[0].DecimalField11[0]": context.fee_for_service,
        f"{_LIST7}.Lie[0].subListe[0].Li1[0].Ch30[0]": "/1",
        f"{_PAGE2}.List8[0].item8[0].declare1[0]": "/1",
        f"{_PAGE2}.Sign[0].SigDate[0]": signed,
        f"{_PAGE2}.Sign[0].SigName[0]": context.server_name,
    }
    if context.notice_basis is NoticeBasis.INDIVIDUAL:
        values[f"{_LIST6}.Lia[0].CheckBox40[0]"] = "/1"
    elif context.notice_basis is NoticeBasis.FICTITIOUS_NAME:
        values[f"{_PAGE1}.List3[0].Lib[0].limited2[0]"] = "/1"
        values[f"{_PAGE1}.List3[0].Lib[0].TextField16[0]"] = context.fictitious_name
        values[f"{_LIST6}.Lib[0].CheckBox41[0]"] = "/2"
        values[f"{_LIST6}.Lib[0].TextField40[0]"] = context.fictitious_name
    elif context.entity_ccp_section is not None:  # ON_BEHALF_OF_ENTITY; validated above
        values[f"{_LIST6}.Lid[0].CheckBox45[0]"] = "/4"
        values[f"{_LIST6}.Lid[0].specify[0]"] = served.name.value
        values[f"{_LIST6}.Lid[0].{_SECTION_CHECKBOX[context.entity_ccp_section]}"] = "/1"
        if context.entity_ccp_section is EntityServiceSection.OTHER:
            values[f"{_LIST6}.Lid[0].other[0]"] = context.other_ccp_section
    return values
