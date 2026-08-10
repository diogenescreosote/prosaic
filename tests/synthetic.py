"""Obviously synthetic case fixtures shared across the suite.

Everything here is fictional: Doe and Roe parties, an invented courthouse,
a case number in the right shape with no real referent.
"""

from __future__ import annotations

import datetime
import hashlib

from prosaic.deadlines import ServiceMethod
from prosaic.model import (
    Address,
    Counsel,
    Court,
    DocketEntry,
    DocumentKind,
    Exhibit,
    Fact,
    Matter,
    Party,
    PartyRole,
    ServiceEvent,
    SourceDocument,
)


def _sha256(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def doe_v_roe() -> Matter:
    """A small but fully cross-referenced contract matter."""
    complaint = SourceDocument(
        id="doc-complaint",
        title="Complaint for Breach of Contract",
        kind=DocumentKind.PLEADING,
        sha256=_sha256("doc-complaint"),
        page_count=12,
        received=datetime.date(2026, 1, 12),
        origin="filesystem",
        location="records/complaint.pdf",
    )
    answer = SourceDocument(
        id="doc-answer",
        title="Answer of Roe Logistics, Inc.",
        kind=DocumentKind.PLEADING,
        sha256=_sha256("doc-answer"),
        page_count=6,
        received=datetime.date(2026, 2, 20),
        origin="filesystem",
        location="records/answer.pdf",
    )
    return Matter(
        title="Doe v. Roe Logistics, Inc.",
        case_number=Fact.from_document("26CV012345", document_id="doc-complaint", page=1),
        court=Court(
            county="Alameda",
            branch="Doe Memorial Courthouse",
            address=Address(
                street="1000 Center Street",
                city="Oakland",
                state="CA",
                zip_code="94601",
            ),
            department="99",
        ),
        parties=[
            Party(
                id="doe",
                name=Fact.from_user("Jane Doe"),
                role=PartyRole.PLAINTIFF,
                self_represented=True,
                address=Address(
                    street="123 Example Lane",
                    city="Oakland",
                    state="CA",
                    zip_code="94601",
                ),
            ),
            Party(
                id="roe",
                name=Fact.from_document("Roe Logistics, Inc.", document_id="doc-complaint", page=1),
                role=PartyRole.DEFENDANT,
                is_organization=True,
            ),
        ],
        counsel=[
            Counsel(
                id="counsel-stone",
                name="Sam Stone",
                bar_number="123456",
                firm="Stone & Flint LLP",
                address=Address(
                    street="500 Flint Plaza",
                    city="Oakland",
                    state="CA",
                    zip_code="94612",
                ),
                phone="(510) 555-0100",
                email="sstone@stoneflint.example",
                represents=["roe"],
            )
        ],
        documents=[complaint, answer],
        docket=[
            DocketEntry(
                date=Fact.from_document(datetime.date(2026, 1, 12), "doc-complaint", 1),
                description="Complaint filed",
                filed_by="doe",
                document_id="doc-complaint",
            ),
            DocketEntry(
                date=Fact.from_document(datetime.date(2026, 2, 20), "doc-answer", 1),
                description="Answer filed",
                filed_by="roe",
                document_id="doc-answer",
            ),
        ],
        service_events=[
            ServiceEvent(
                document_id="doc-answer",
                served_on="doe",
                date=Fact.from_document(datetime.date(2026, 2, 20), "doc-answer", 6),
                method=ServiceMethod.MAIL_WITHIN_CALIFORNIA,
            )
        ],
        exhibits=[
            Exhibit(
                label="A",
                description="Services agreement dated January 5, 2026",
                document_id="doc-complaint",
                first_page=5,
                last_page=9,
            )
        ],
    )
