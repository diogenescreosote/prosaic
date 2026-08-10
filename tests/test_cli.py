"""The CLI, driven through typer's test runner."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import prosaic.cli.main as cli
from prosaic.agent.operator import MessageCreator
from tests.synthetic import doe_v_roe

runner = CliRunner()


def test_deadline_command_prints_the_engine_result() -> None:
    result = runner.invoke(
        cli.app, ["deadline", "motion_filing", "2026-10-02", "--method", "electronic"]
    )
    assert result.exit_code == 0
    assert "2026-09-04" in result.output
    assert "1005(b)" in result.output


def test_deadline_command_fails_loudly_outside_calendar_coverage() -> None:
    result = runner.invoke(cli.app, ["deadline", "demurrer", "2031-01-01"])
    assert result.exit_code == 1
    assert "coverage" in result.output


def test_forms_command_lists_the_pack() -> None:
    result = runner.invoke(cli.app, ["forms"])
    assert result.exit_code == 0
    for number in ("CM-010", "CM-110", "SUM-100", "POS-010", "MC-030", "MC-031"):
        assert number in result.output


def test_holidays_command_lists_a_covered_year() -> None:
    result = runner.invoke(cli.app, ["holidays", "2026"])
    assert result.exit_code == 0
    assert "2026-07-03" in result.output  # Independence Day observed
    assert len(result.output.strip().splitlines()) == 14


def test_holidays_command_rejects_uncovered_years() -> None:
    result = runner.invoke(cli.app, ["holidays", "1999"])
    assert result.exit_code == 1
    assert "coverage" in result.output


def test_ask_command_loads_the_matter_and_runs_the_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from anthropic.types import Message, TextBlock, Usage

    class OneAnswerClient:
        def create(self, **_: object) -> Message:
            return Message.model_construct(
                id="msg_test",
                type="message",
                role="assistant",
                model="claude-opus-5",
                content=[TextBlock.model_construct(type="text", text="Two parties.")],
                stop_reason="end_turn",
                stop_sequence=None,
                usage=Usage.model_construct(input_tokens=1, output_tokens=1),
            )

    def fake_client() -> MessageCreator:
        return OneAnswerClient()

    monkeypatch.setattr(cli, "_anthropic_client", fake_client)

    matter_file = tmp_path / "matter.json"
    matter_file.write_text(doe_v_roe().model_dump_json())
    result = runner.invoke(cli.app, ["ask", str(matter_file), "How many parties?"])
    assert result.exit_code == 0
    assert "Two parties." in result.output
