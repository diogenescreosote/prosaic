"""Root pytest configuration for prosaic.

Test layers:
- ``pleading/tests``            unit/component tests (fast, deterministic)
- ``tests/scenarios/<name>``    scenario tests: whole fixture matters,
                                real operations, many independent checks
- ``@pytest.mark.ai``           checks judged by a headless agent session
                                via cli/agent-run (skipped without an
                                agent CLI or with PROSAIC_AI_TESTS=0)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "pleading"))
sys.path.insert(0, str(REPO))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "ai: judged by a headless LLM; skipped when unavailable")


def pytest_collection_modifyitems(
    config: pytest.Config,  # noqa: ARG001 — pytest matches hook arguments by name
    items: list[pytest.Item],
) -> None:
    from tests.harness.ai import ai_available

    if ai_available():
        return
    skip = pytest.mark.skip(reason="AI judge unavailable (no agent CLI or PROSAIC_AI_TESTS=0)")
    for item in items:
        if "ai" in item.keywords:
            item.add_marker(skip)
