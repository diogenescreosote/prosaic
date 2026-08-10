"""The operator loop and its typed tool surface, driven by a scripted client."""

from __future__ import annotations

import json

import pytest
from anthropic.types import ContentBlock, Message, StopReason, TextBlock, ToolUseBlock, Usage

from prosaic.agent import (
    Operator,
    OperatorRefusedError,
    OperatorTurnLimitError,
    Toolkit,
)
from prosaic.deadlines import california_court_calendar
from prosaic.packs.civil import CIVIL_PACK
from tests.synthetic import doe_v_roe

CAL = california_court_calendar()


def _message(content: list[ContentBlock], stop_reason: StopReason) -> Message:
    return Message.model_construct(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-opus-5",
        content=content,
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage.model_construct(input_tokens=10, output_tokens=10),
    )


def _text(text: str) -> TextBlock:
    return TextBlock.model_construct(type="text", text=text)


def _tool_use(name: str, tool_input: dict[str, object]) -> ToolUseBlock:
    return ToolUseBlock.model_construct(
        type="tool_use", id="toolu_test", name=name, input=tool_input
    )


class ScriptedClient:
    """Returns canned responses and records every request it receives."""

    def __init__(self, responses: list[Message]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    def create(self, **request: object) -> Message:
        self.requests.append(request)
        return self.responses[len(self.requests) - 1]


def _operator(client: ScriptedClient, max_turns: int = 10) -> Operator:
    return Operator(client, doe_v_roe(), CAL, CIVIL_PACK, max_turns=max_turns)


def test_plain_answer_needs_no_tools() -> None:
    client = ScriptedClient([_message([_text("A demurrer tests the pleading.")], "end_turn")])
    answer = _operator(client).ask("What is a demurrer?")
    assert answer == "A demurrer tests the pleading."
    assert len(client.requests) == 1


def test_deadline_answers_flow_through_the_engine() -> None:
    client = ScriptedClient(
        [
            _message(
                [
                    _tool_use(
                        "compute_deadline",
                        {
                            "rule": "motion_filing",
                            "trigger_date": "2026-10-02",
                            "service_method": "electronic",
                        },
                    )
                ],
                "tool_use",
            ),
            _message([_text("File and serve by September 4, 2026.")], "end_turn"),
        ]
    )
    answer = _operator(client).ask("When must I file my motion?")
    assert "September 4, 2026" in answer

    followup = client.requests[1]["messages"]
    assert isinstance(followup, list)
    tool_result = followup[-1]["content"][0]
    payload = json.loads(tool_result["content"])
    assert payload["date"] == "2026-09-04"  # the engine's date, not the model's
    assert "1005(b)" in payload["citation"]


def test_malformed_tool_input_returns_an_error_result() -> None:
    client = ScriptedClient(
        [
            _message(
                [_tool_use("compute_deadline", {"rule": "motion_filing", "trigger_date": "soon"})],
                "tool_use",
            ),
            _message([_text("Let me correct that.")], "end_turn"),
        ]
    )
    _operator(client).ask("When must I file?")
    followup = client.requests[1]["messages"]
    assert isinstance(followup, list)
    tool_result = followup[-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "invalid compute_deadline input" in tool_result["content"]


def test_unknown_tool_returns_an_error_result() -> None:
    toolkit = Toolkit(doe_v_roe(), CAL, CIVIL_PACK)
    outcome = toolkit.execute("write_check", {})
    assert outcome.is_error
    assert "unknown tool" in outcome.text


def test_refusal_is_raised_to_the_human() -> None:
    client = ScriptedClient([_message([], "refusal")])
    with pytest.raises(OperatorRefusedError):
        _operator(client).ask("...")


def test_turn_limit_is_enforced() -> None:
    looping = _message(
        [_tool_use("compute_deadline", {"rule": "reply", "trigger_date": "2026-10-02"})],
        "tool_use",
    )
    client = ScriptedClient([looping, looping])
    with pytest.raises(OperatorTurnLimitError):
        _operator(client, max_turns=2).ask("...")


def test_matter_summary_reads_the_case_model() -> None:
    toolkit = Toolkit(doe_v_roe(), CAL, CIVIL_PACK)
    summary = json.loads(toolkit.execute("matter_summary", {}).text)
    assert summary["case_number"] == "26CV012345"
    assert [party["name"] for party in summary["parties"]] == ["Jane Doe", "Roe Logistics, Inc."]
    assert summary["service_events"][0]["method"] == "mail_within_california"


def test_list_forms_reports_the_pack() -> None:
    toolkit = Toolkit(doe_v_roe(), CAL, CIVIL_PACK)
    forms = json.loads(toolkit.execute("list_forms", {}).text)
    assert {form["number"] for form in forms} == {
        "CM-010",
        "CM-110",
        "SUM-100",
        "POS-010",
        "MC-030",
        "MC-031",
    }
    declaration = next(form for form in forms if form["number"] == "MC-030")
    assert "declarant_party_id" in declaration["context_fields"]


@pytest.mark.parametrize(
    ("rule", "trigger", "expected"),
    [
        ("demurrer", "2026-05-22", "2026-06-22"),
        ("opposition", "2026-10-02", "2026-09-18"),
        ("reply", "2026-10-02", "2026-09-24"),
        ("complaint_service", "2026-01-05", "2026-03-06"),
        ("case_management_statement", "2026-04-20", "2026-04-03"),
        ("earliest_motion_hearing", "2026-09-09", "2026-10-02"),
    ],
)
def test_every_rule_dispatches_to_the_engine(rule: str, trigger: str, expected: str) -> None:
    toolkit = Toolkit(doe_v_roe(), CAL, CIVIL_PACK)
    outcome = toolkit.execute("compute_deadline", {"rule": rule, "trigger_date": trigger})
    assert not outcome.is_error
    assert json.loads(outcome.text)["date"] == expected


def test_out_of_coverage_dates_surface_as_tool_errors() -> None:
    toolkit = Toolkit(doe_v_roe(), CAL, CIVIL_PACK)
    outcome = toolkit.execute(
        "compute_deadline", {"rule": "demurrer", "trigger_date": "2031-01-01"}
    )
    assert outcome.is_error
    assert "rejected the computation" in outcome.text
