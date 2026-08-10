"""The typed tool surface between the model and the engine.

Each tool is a schema plus a handler bound to one matter, one court
calendar, and one form pack. Handlers parse the model's JSON input with
pydantic before touching the engine, and every failure returns an error
tool result rather than raising — the model gets a chance to correct
itself, and the loop never dies on a malformed call.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, fields, is_dataclass
from enum import StrEnum

from anthropic.types import ToolParam
from pydantic import BaseModel, ValidationError

from prosaic.deadlines import (
    CourtCalendar,
    Deadline,
    ServiceMethod,
    case_management_statement_deadline,
    complaint_service_deadline,
    demurrer_deadline,
    earliest_motion_hearing,
    motion_filing_deadline,
    opposition_deadline,
    reply_deadline,
)
from prosaic.forms.pack import FormPack
from prosaic.model import Matter


class DeadlineRuleName(StrEnum):
    DEMURRER = "demurrer"
    MOTION_FILING = "motion_filing"
    EARLIEST_MOTION_HEARING = "earliest_motion_hearing"
    OPPOSITION = "opposition"
    REPLY = "reply"
    COMPLAINT_SERVICE = "complaint_service"
    CASE_MANAGEMENT_STATEMENT = "case_management_statement"


class ComputeDeadlineInput(BaseModel):
    rule: DeadlineRuleName
    trigger_date: datetime.date
    service_method: ServiceMethod = ServiceMethod.PERSONAL


def run_rule(
    rule: DeadlineRuleName,
    trigger: datetime.date,
    method: ServiceMethod,
    calendar: CourtCalendar,
) -> Deadline:
    """Dispatch a named rule to the engine. The CLI and the toolkit share this."""
    match rule:
        case DeadlineRuleName.DEMURRER:
            return demurrer_deadline(trigger, method, calendar)
        case DeadlineRuleName.MOTION_FILING:
            return motion_filing_deadline(trigger, method, calendar)
        case DeadlineRuleName.EARLIEST_MOTION_HEARING:
            return earliest_motion_hearing(trigger, method, calendar)
        case DeadlineRuleName.OPPOSITION:
            return opposition_deadline(trigger, calendar)
        case DeadlineRuleName.REPLY:
            return reply_deadline(trigger, calendar)
        case DeadlineRuleName.COMPLAINT_SERVICE:
            return complaint_service_deadline(trigger, calendar)
        case DeadlineRuleName.CASE_MANAGEMENT_STATEMENT:
            return case_management_statement_deadline(trigger, calendar)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """What a handler produced: text for the model, and whether it failed."""

    text: str
    is_error: bool = False


class Toolkit:
    """The tools one operator session exposes, bound to its case."""

    def __init__(self, matter: Matter, calendar: CourtCalendar, pack: FormPack) -> None:
        self.matter = matter
        self.calendar = calendar
        self.pack = pack

    def definitions(self) -> list[ToolParam]:
        return [
            {
                "name": "matter_summary",
                "description": (
                    "Read the structured case model: parties, counsel, court, case "
                    "number, documents, docket entries, and service events. Call this "
                    "before answering questions about the state of the case."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "compute_deadline",
                "description": (
                    "Compute a statutory deadline with the deterministic date engine. "
                    "This is the only source of dates. The trigger_date is the rule's "
                    "trigger: the date service was complete (demurrer), the hearing "
                    "date (motion_filing, opposition, reply), the date papers are "
                    "served (earliest_motion_hearing), the complaint filing date "
                    "(complaint_service), or the conference date "
                    "(case_management_statement)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "rule": {
                            "type": "string",
                            "enum": [rule.value for rule in DeadlineRuleName],
                        },
                        "trigger_date": {
                            "type": "string",
                            "description": "ISO 8601 date, e.g. 2026-10-02",
                        },
                        "service_method": {
                            "type": "string",
                            "enum": [method.value for method in ServiceMethod],
                            "description": (
                                "How the triggering paper was or will be served; "
                                "defaults to personal service. Only affects rules "
                                "with statutory service extensions."
                            ),
                        },
                    },
                    "required": ["rule", "trigger_date"],
                },
            },
            {
                "name": "list_forms",
                "description": (
                    "List the Judicial Council forms this pack can fill, with the "
                    "fields each form's context requires. Rendering happens through "
                    "the CLI; use this to tell the user what is available and what "
                    "information a form needs."
                ),
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ]

    def execute(self, name: str, tool_input: object) -> ToolResult:
        if name == "matter_summary":
            return ToolResult(json.dumps(self._matter_summary(), indent=1))
        if name == "compute_deadline":
            return self._compute_deadline(tool_input)
        if name == "list_forms":
            return ToolResult(json.dumps(self._list_forms(), indent=1))
        return ToolResult(f"unknown tool: {name}", is_error=True)

    def _matter_summary(self) -> dict[str, object]:
        matter = self.matter
        return {
            "title": matter.title,
            "case_number": matter.case_number.value if matter.case_number else None,
            "court": {
                "county": matter.court.county,
                "branch": matter.court.branch,
                "department": matter.court.department,
            },
            "parties": [
                {
                    "id": party.id,
                    "name": party.name.value,
                    "role": party.role.value,
                    "self_represented": party.self_represented,
                }
                for party in matter.parties
            ],
            "documents": [
                {
                    "id": document.id,
                    "title": document.title,
                    "kind": document.kind.value,
                    "received": document.received.isoformat() if document.received else None,
                    "pages": document.page_count,
                }
                for document in matter.documents
            ],
            "docket": [
                {
                    "date": entry.date.value.isoformat(),
                    "description": entry.description,
                    "filed_by": entry.filed_by,
                }
                for entry in matter.docket
            ],
            "service_events": [
                {
                    "document_id": event.document_id,
                    "served_on": event.served_on,
                    "date": event.date.value.isoformat(),
                    "method": event.method.value,
                }
                for event in matter.service_events
            ],
        }

    def _compute_deadline(self, tool_input: object) -> ToolResult:
        try:
            parsed = ComputeDeadlineInput.model_validate(tool_input)
        except ValidationError as error:
            return ToolResult(f"invalid compute_deadline input: {error}", is_error=True)
        try:
            deadline = run_rule(
                parsed.rule, parsed.trigger_date, parsed.service_method, self.calendar
            )
        except ValueError as error:
            return ToolResult(f"the date engine rejected the computation: {error}", is_error=True)
        return ToolResult(
            json.dumps(
                {
                    "date": deadline.date.isoformat(),
                    "citation": deadline.citation,
                    "description": deadline.description,
                }
            )
        )

    def _list_forms(self) -> list[dict[str, object]]:
        return [
            {
                "number": form.number,
                "title": form.title,
                # is_dataclass narrows for the type checker; every pack context is one
                "context_fields": (
                    [field.name for field in fields(form.context_type)]
                    if is_dataclass(form.context_type)
                    else []
                ),
            }
            for form in self.pack.forms
        ]
