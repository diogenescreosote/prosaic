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


def pytest_addoption(parser: pytest.Parser, pluginmanager: pytest.PytestPluginManager) -> None:
    """Accept xdist's options when xdist is absent or disabled.

    pyproject's addopts asks for ``--numprocesses=auto --dist=loadgroup``
    (long forms: pytest reserves ``-n`` for plugins). Without
    pytest-xdist (an environment not yet re-synced, a bare python with
    pytest) or with it switched off (``-p no:xdist``), those would be
    unrecognized arguments and nothing would run; here they are
    accepted and ignored, and the suite runs serially in-process.
    """
    if pluginmanager.has_plugin("xdist"):
        return
    group = parser.getgroup("xdist", "xdist absent: these options are accepted and ignored")
    group.addoption("--numprocesses", dest="numprocesses", default=None)
    group.addoption("--dist", dest="dist", default="no")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "ai: judged by a headless LLM; skipped when unavailable")
    config.addinivalue_line(
        "markers",
        "xdist_group(name): run every test sharing the name on one worker, in order",
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config,  # noqa: ARG001 — pytest matches hook arguments by name
    items: list[pytest.Item],
) -> None:
    # Serialize the AI judge. A burst of concurrent judgments trips
    # transient auth and rate-limit failures (tests/harness/ai.py), so
    # under xdist every `ai` test shares one worker. tryfirst: xdist
    # reads the group mark in its own hook of this name.
    for item in items:
        if item.get_closest_marker("ai") and not item.get_closest_marker("xdist_group"):
            item.add_marker(pytest.mark.xdist_group("ai-judge"))

    from tests.harness.ai import ai_available

    if ai_available():
        return
    skip = pytest.mark.skip(reason="AI judge unavailable (no agent CLI or PROSAIC_AI_TESTS=0)")
    for item in items:
        if "ai" in item.keywords:
            item.add_marker(skip)
