"""CM-010: Civil Case Cover Sheet.

The item-1 case-type list is 44 independent checkboxes; exactly one is
checked. Their on-states mostly run /N+1 in widget order, but the July 2026
revision inserted Song-Beverly as /17 (shifting the rest of the contract
column) and gave eminent domain /44, so the table below is written out
literally rather than computed. Two internal names on the official form
mislead: ``HearingDate`` is the JUDGE line and ``HearingDept`` is DEPT.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import StrEnum

from prosaic.forms.pack import FormValidationError
from prosaic.model import Matter
from prosaic.packs.civil.caption import caption_for, caption_problems

NUMBER = "CM-010"
TITLE = "Civil Case Cover Sheet"

_CAPTION = "CM-010[0].Page1[0].P1Caption[0]"
_LIST1 = "CM-010[0].Page1[0].List1[0]"
_PAGE2 = "CM-010[0].Page2[0]"


class AmountDemanded(StrEnum):
    UNLIMITED = "unlimited"  # exceeds $35,000
    LIMITED = "limited"


class CaseType(StrEnum):
    AUTO = "auto"
    UNINSURED_MOTORIST = "uninsured_motorist"
    ASBESTOS = "asbestos"
    PRODUCT_LIABILITY = "product_liability"
    MEDICAL_MALPRACTICE = "medical_malpractice"
    OTHER_PI_PD_WD = "other_pi_pd_wd"
    BUSINESS_TORT = "business_tort"
    CIVIL_RIGHTS = "civil_rights"
    DEFAMATION = "defamation"
    FRAUD = "fraud"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    PROFESSIONAL_NEGLIGENCE = "professional_negligence"
    OTHER_NON_PI_PD_WD_TORT = "other_non_pi_pd_wd_tort"
    WRONGFUL_TERMINATION = "wrongful_termination"
    OTHER_EMPLOYMENT = "other_employment"
    BREACH_OF_CONTRACT_WARRANTY = "breach_of_contract_warranty"
    SONG_BEVERLY_MOTOR_VEHICLE = "song_beverly_motor_vehicle"
    RULE_3_740_COLLECTIONS = "rule_3_740_collections"
    OTHER_COLLECTIONS = "other_collections"
    INSURANCE_COVERAGE = "insurance_coverage"
    OTHER_CONTRACT = "other_contract"
    EMINENT_DOMAIN = "eminent_domain"
    WRONGFUL_EVICTION = "wrongful_eviction"
    OTHER_REAL_PROPERTY = "other_real_property"
    UNLAWFUL_DETAINER_COMMERCIAL = "unlawful_detainer_commercial"
    UNLAWFUL_DETAINER_RESIDENTIAL = "unlawful_detainer_residential"
    UNLAWFUL_DETAINER_DRUGS = "unlawful_detainer_drugs"
    ASSET_FORFEITURE = "asset_forfeiture"
    PETITION_RE_ARBITRATION_AWARD = "petition_re_arbitration_award"
    WRIT_OF_MANDATE = "writ_of_mandate"
    OTHER_JUDICIAL_REVIEW = "other_judicial_review"
    EDD_DECISION_REVIEW = "edd_decision_review"
    ANTITRUST_TRADE_REGULATION = "antitrust_trade_regulation"
    CONSTRUCTION_DEFECT = "construction_defect"
    MASS_TORT = "mass_tort"
    SECURITIES_LITIGATION = "securities_litigation"
    ENVIRONMENTAL_TOXIC_TORT = "environmental_toxic_tort"
    GROUNDWATER_ADJUDICATION = "groundwater_adjudication"
    COMPLEX_INSURANCE_COVERAGE = "complex_insurance_coverage"
    ENFORCEMENT_OF_JUDGMENT = "enforcement_of_judgment"
    RICO = "rico"
    OTHER_COMPLAINT = "other_complaint"
    PARTNERSHIP_AND_CORPORATE_GOVERNANCE = "partnership_and_corporate_governance"
    OTHER_PETITION = "other_petition"


_CASE_TYPE_STATE: dict[CaseType, tuple[int, str]] = {
    CaseType.AUTO: (0, "/1"),
    CaseType.UNINSURED_MOTORIST: (1, "/2"),
    CaseType.ASBESTOS: (2, "/3"),
    CaseType.PRODUCT_LIABILITY: (3, "/4"),
    CaseType.MEDICAL_MALPRACTICE: (4, "/5"),
    CaseType.OTHER_PI_PD_WD: (5, "/6"),
    CaseType.BUSINESS_TORT: (6, "/7"),
    CaseType.CIVIL_RIGHTS: (7, "/8"),
    CaseType.DEFAMATION: (8, "/9"),
    CaseType.FRAUD: (9, "/10"),
    CaseType.INTELLECTUAL_PROPERTY: (10, "/11"),
    CaseType.PROFESSIONAL_NEGLIGENCE: (11, "/12"),
    CaseType.OTHER_NON_PI_PD_WD_TORT: (12, "/13"),
    CaseType.WRONGFUL_TERMINATION: (13, "/14"),
    CaseType.OTHER_EMPLOYMENT: (14, "/15"),
    CaseType.BREACH_OF_CONTRACT_WARRANTY: (15, "/16"),
    CaseType.SONG_BEVERLY_MOTOR_VEHICLE: (20, "/17"),
    CaseType.RULE_3_740_COLLECTIONS: (16, "/18"),
    CaseType.OTHER_COLLECTIONS: (17, "/19"),
    CaseType.INSURANCE_COVERAGE: (18, "/20"),
    CaseType.OTHER_CONTRACT: (19, "/21"),
    CaseType.EMINENT_DOMAIN: (21, "/44"),
    CaseType.WRONGFUL_EVICTION: (22, "/22"),
    CaseType.OTHER_REAL_PROPERTY: (23, "/23"),
    CaseType.UNLAWFUL_DETAINER_COMMERCIAL: (24, "/24"),
    CaseType.UNLAWFUL_DETAINER_RESIDENTIAL: (25, "/25"),
    CaseType.UNLAWFUL_DETAINER_DRUGS: (26, "/26"),
    CaseType.ASSET_FORFEITURE: (27, "/27"),
    CaseType.PETITION_RE_ARBITRATION_AWARD: (28, "/28"),
    CaseType.WRIT_OF_MANDATE: (29, "/29"),
    CaseType.OTHER_JUDICIAL_REVIEW: (30, "/30"),
    CaseType.EDD_DECISION_REVIEW: (31, "/31"),
    CaseType.ANTITRUST_TRADE_REGULATION: (32, "/32"),
    CaseType.CONSTRUCTION_DEFECT: (33, "/33"),
    CaseType.MASS_TORT: (34, "/34"),
    CaseType.SECURITIES_LITIGATION: (35, "/35"),
    CaseType.ENVIRONMENTAL_TOXIC_TORT: (36, "/36"),
    CaseType.GROUNDWATER_ADJUDICATION: (37, "/37"),
    CaseType.COMPLEX_INSURANCE_COVERAGE: (38, "/38"),
    CaseType.ENFORCEMENT_OF_JUDGMENT: (39, "/39"),
    CaseType.RICO: (40, "/40"),
    CaseType.OTHER_COMPLAINT: (41, "/41"),
    CaseType.PARTNERSHIP_AND_CORPORATE_GOVERNANCE: (42, "/42"),
    CaseType.OTHER_PETITION: (43, "/43"),
}


class ComplexityFactor(StrEnum):
    SEPARATELY_REPRESENTED_PARTIES = "separately_represented_parties"
    EXTENSIVE_MOTION_PRACTICE = "extensive_motion_practice"
    SUBSTANTIAL_DOCUMENTARY_EVIDENCE = "substantial_documentary_evidence"
    LARGE_NUMBER_OF_WITNESSES = "large_number_of_witnesses"
    COORDINATION_WITH_RELATED_ACTIONS = "coordination_with_related_actions"
    POSTJUDGMENT_SUPERVISION = "postjudgment_supervision"


# The lowercase "lie" in factor e is the official form's own naming.
_FACTOR_WIDGET = {
    ComplexityFactor.SEPARATELY_REPRESENTED_PARTIES: "Lia[0].Choice1[0]",
    ComplexityFactor.EXTENSIVE_MOTION_PRACTICE: "Lib[0].Choice2[0]",
    ComplexityFactor.SUBSTANTIAL_DOCUMENTARY_EVIDENCE: "Lic[0].Choice3[0]",
    ComplexityFactor.LARGE_NUMBER_OF_WITNESSES: "Lid[0].Choice4[0]",
    ComplexityFactor.COORDINATION_WITH_RELATED_ACTIONS: "lie[0].Choice5[0]",
    ComplexityFactor.POSTJUDGMENT_SUPERVISION: "Lif[0].Choice6[0]",
}


class Remedy(StrEnum):
    MONETARY = "monetary"
    NONMONETARY = "nonmonetary"
    PUNITIVE = "punitive"


_REMEDY_FIELD = {
    Remedy.MONETARY: f"{_PAGE2}.List3[0].Item3[0].Lia[0].Ch1[0]",
    Remedy.NONMONETARY: f"{_PAGE2}.List3[0].Item3[0].Lib[0].Ch2[0]",
    Remedy.PUNITIVE: f"{_PAGE2}.List3[0].Item3[0].Lic[0].Ch3[0]",
}


@dataclass(frozen=True, slots=True)
class CoverSheetContext:
    """The choices item 1 through 6 need from the filing party."""

    filer_party_id: str
    case_type: CaseType
    amount: AmountDemanded
    remedies: frozenset[Remedy]
    causes_of_action: int
    is_class_action: bool
    signed_on: datetime.date
    is_complex: bool = False
    complexity_factors: frozenset[ComplexityFactor] = field(default_factory=frozenset)


def build_values(matter: Matter, context: CoverSheetContext) -> dict[str, str | bool]:
    filer = matter.party(context.filer_party_id)

    problems = caption_problems(matter, filer)
    if context.causes_of_action < 1:
        problems.append("a complaint states at least one cause of action")
    if not context.remedies:
        problems.append("check at least one remedy in item 3")
    if context.complexity_factors and not context.is_complex:
        problems.append("complexity factors are only marked when the case is complex")
    if problems:
        raise FormValidationError(NUMBER, problems)

    caption = caption_for(matter, filer)
    city, state, zip_code = "", "", ""
    address = filer.address if filer.address else None
    counsel = next((c for c in matter.counsel if filer.id in c.represents), None)
    if counsel is not None:
        address = counsel.address
    if address is not None:
        city, state, zip_code = address.city, address.state, address.zip_code

    index, state_name = _CASE_TYPE_STATE[context.case_type]
    values: dict[str, str | bool] = {
        f"{_CAPTION}.AttyPartyInfo[0].Name[0]": (
            counsel.name if counsel is not None else filer.name.value
        ),
        f"{_CAPTION}.AttyPartyInfo[0].AttyBarNo[0]": (
            counsel.bar_number if counsel is not None else ""
        ),
        f"{_CAPTION}.AttyPartyInfo[0].AttyFirm[0]": counsel.firm if counsel is not None else "",
        f"{_CAPTION}.AttyPartyInfo[0].Street[0]": address.street if address is not None else "",
        f"{_CAPTION}.AttyPartyInfo[0].City[0]": city,
        f"{_CAPTION}.AttyPartyInfo[0].State[0]": state,
        f"{_CAPTION}.AttyPartyInfo[0].Zip[0]": zip_code,
        f"{_CAPTION}.AttyPartyInfo[0].Phone[0]": caption.telephone,
        f"{_CAPTION}.AttyPartyInfo[0].Fax[0]": caption.fax,
        f"{_CAPTION}.AttyPartyInfo[0].Email[0]": caption.email,
        f"{_CAPTION}.AttyPartyInfo[0].AttyFor[0]": caption.attorney_for,
        f"{_CAPTION}.CourtInfo[0].CrtCounty[0]": caption.court_county,
        f"{_CAPTION}.CourtInfo[0].CrtStreet[0]": caption.court_street,
        f"{_CAPTION}.CourtInfo[0].CrtMailingAdd[0]": caption.court_mailing,
        f"{_CAPTION}.CourtInfo[0].CrtCityZip[0]": caption.court_city_zip,
        f"{_CAPTION}.CourtInfo[0].CrtBranch[0]": caption.court_branch,
        f"{_CAPTION}.TitlePartyName[0].Party1[0]": matter.title,
        f"{_CAPTION}.csn[0].CaseNumber[0]": caption.case_number,
        f"{_CAPTION}.HearingInfo[0].HearingDept[0]": matter.court.department,
        f"{_CAPTION}.FormTitle[0].Civil[0].limited1[0]"
        if context.amount is AmountDemanded.UNLIMITED
        else f"{_CAPTION}.FormTitle[0].Civil[0].limited1[1]": (
            "/1" if context.amount is AmountDemanded.UNLIMITED else "/2"
        ),
        f"{_LIST1}.Item1Check[{index}]": state_name,
        f"{_PAGE2}.List2[0].is1[0]" if context.is_complex else f"{_PAGE2}.List2[0].is1[1]": (
            "/1" if context.is_complex else "/2"
        ),
        f"{_PAGE2}.List4[0].FillText1[0]": str(context.causes_of_action),
        f"{_PAGE2}.List5[0].is[0]" if context.is_class_action else f"{_PAGE2}.List5[0].is[1]": (
            "/1" if context.is_class_action else "/2"
        ),
        f"{_PAGE2}.SigDate[0]": context.signed_on.strftime("%B %-d, %Y"),
        f"{_PAGE2}.SigName[0]": counsel.name if counsel is not None else filer.name.value,
    }
    for factor in context.complexity_factors:
        values[f"{_PAGE2}.List2[0].Item2[0].{_FACTOR_WIDGET[factor]}"] = True
    for remedy in context.remedies:
        values[_REMEDY_FIELD[remedy]] = True
    return values
