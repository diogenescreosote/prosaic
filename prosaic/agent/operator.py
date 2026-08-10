"""The operator loop.

A thin manual tool loop over the Messages API: the client is injected
behind a one-method protocol so tests drive the loop with scripted
responses, and the only capabilities the model has are the typed tools in
``Toolkit``. A refusal from the model's safety layer is raised to the
caller rather than silently rerouted — in a legal tool, the human decides
what happens next.
"""

from __future__ import annotations

from typing import Protocol

from anthropic.types import Message, MessageParam, TextBlock, ToolParam, ToolResultBlockParam

from prosaic.agent.prompts import SYSTEM_PROMPT
from prosaic.agent.toolkit import Toolkit
from prosaic.deadlines import CourtCalendar
from prosaic.forms.pack import FormPack
from prosaic.model import Matter

DEFAULT_MODEL = "claude-opus-5"


class MessageCreator(Protocol):
    """The slice of ``anthropic.Anthropic().messages`` the operator uses."""

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        system: str,
        tools: list[ToolParam],
        messages: list[MessageParam],
    ) -> Message: ...


class OperatorTurnLimitError(RuntimeError):
    """The model kept calling tools past the turn budget."""


class OperatorRefusedError(RuntimeError):
    """The model's safety layer declined; the human operator decides next steps."""


class Operator:
    """One conversation about one matter."""

    def __init__(
        self,
        client: MessageCreator,
        matter: Matter,
        calendar: CourtCalendar,
        pack: FormPack,
        *,
        model: str = DEFAULT_MODEL,
        max_turns: int = 10,
    ) -> None:
        self.client = client
        self.toolkit = Toolkit(matter, calendar, pack)
        self.model = model
        self.max_turns = max_turns

    def ask(self, question: str) -> str:
        messages: list[MessageParam] = [{"role": "user", "content": question}]
        for _ in range(self.max_turns):
            response = self.client.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=self.toolkit.definitions(),
                messages=messages,
            )
            if response.stop_reason == "refusal":
                raise OperatorRefusedError(
                    "the model declined this request; review it before rephrasing"
                )
            if response.stop_reason != "tool_use":
                return "".join(
                    block.text for block in response.content if isinstance(block, TextBlock)
                )
            messages.append({"role": "assistant", "content": response.content})
            results: list[ToolResultBlockParam] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                outcome = self.toolkit.execute(block.name, block.input)
                result: ToolResultBlockParam = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": outcome.text,
                }
                if outcome.is_error:
                    result["is_error"] = True
                results.append(result)
            messages.append({"role": "user", "content": results})
        raise OperatorTurnLimitError(f"no final answer within {self.max_turns} turns")
