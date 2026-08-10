"""The LLM operator.

The model reads the case, drafts prose, and explains; the engine computes,
validates, and renders. Structurally, the deadline engine is reachable from
here only through ``Toolkit``'s typed compute_deadline tool — there is no
code path by which model output becomes a date.
"""

from prosaic.agent.operator import (
    DEFAULT_MODEL,
    MessageCreator,
    Operator,
    OperatorRefusedError,
    OperatorTurnLimitError,
)
from prosaic.agent.toolkit import DeadlineRuleName, Toolkit, ToolResult

__all__ = [
    "DEFAULT_MODEL",
    "DeadlineRuleName",
    "MessageCreator",
    "Operator",
    "OperatorRefusedError",
    "OperatorTurnLimitError",
    "ToolResult",
    "Toolkit",
]
