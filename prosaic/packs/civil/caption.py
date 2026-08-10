"""The shared caption block of Judicial Council civil forms.

Every JC form opens with the same block: filer (or counsel) identity and
contact details, the court, the party names, and the case number. Forms
differ only in which AcroForm field names receive these values, so the
semantics are computed once here and each form module maps them to its
own field names.
"""

from __future__ import annotations

from dataclasses import dataclass

from prosaic.model import Address, Counsel, Matter, Party, PartyRole

_PLAINTIFF_SIDE = {PartyRole.PLAINTIFF, PartyRole.PETITIONER, PartyRole.CROSS_COMPLAINANT}


@dataclass(frozen=True, slots=True)
class Caption:
    attorney_lines: tuple[str, str, str]
    telephone: str
    fax: str
    email: str
    attorney_for: str
    court_county: str
    court_street: str
    court_mailing: str
    court_city_zip: str
    court_branch: str
    plaintiffs: str
    defendants: str
    case_number: str


def _street_and_city(address: Address) -> tuple[str, str]:
    return address.street, f"{address.city}, {address.state} {address.zip_code}"


def _counsel_for(matter: Matter, party_id: str) -> Counsel | None:
    for counsel in matter.counsel:
        if party_id in counsel.represents:
            return counsel
    return None


def _side(matter: Matter, roles: set[PartyRole]) -> str:
    return ", ".join(p.name.value for p in matter.parties if p.role in roles)


def _role_label(party: Party) -> str:
    return party.role.value.replace("_", "-").title()


def caption_problems(matter: Matter, filer: Party) -> list[str]:
    """What the caption block needs and the matter does not have."""
    problems = []
    if _counsel_for(matter, filer.id) is None and filer.address is None:
        problems.append(f"self-represented filer {filer.id} has no address for the caption")
    return problems


def caption_for(matter: Matter, filer: Party) -> Caption:
    """Caption values for a filing by ``filer``.

    Call ``caption_problems`` first; this raises only on programming error.
    """
    counsel = _counsel_for(matter, filer.id)
    if counsel is not None:
        name_line = f"{counsel.name}, SBN {counsel.bar_number}"
        if counsel.firm:
            name_line = f"{name_line}, {counsel.firm}"
        street, city = _street_and_city(counsel.address)
        attorney_for = f"{_role_label(filer)} {filer.name.value}"
        telephone, fax, email = counsel.phone, "", counsel.email
    else:
        if filer.address is None:
            raise ValueError(f"party {filer.id} has no address; check caption_problems first")
        name_line = filer.name.value
        street, city = _street_and_city(filer.address)
        attorney_for = "Self-represented"
        telephone, fax, email = "", "", ""

    return Caption(
        attorney_lines=(name_line, street, city),
        telephone=telephone,
        fax=fax,
        email=email,
        attorney_for=attorney_for,
        court_county=matter.court.county.upper(),
        court_street=matter.court.address.street,
        court_mailing="",
        court_city_zip=f"{matter.court.address.city}, {matter.court.address.state} "
        f"{matter.court.address.zip_code}",
        court_branch=matter.court.branch,
        plaintiffs=_side(matter, _PLAINTIFF_SIDE),
        defendants=_side(
            matter,
            {PartyRole.DEFENDANT, PartyRole.RESPONDENT, PartyRole.CROSS_DEFENDANT},
        ),
        case_number=matter.case_number.value if matter.case_number else "",
    )
