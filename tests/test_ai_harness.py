"""The AI judge harness itself (design/adr/0008).

The judged scenario tests cannot check these properties: they need a
reachable judge to run at all, and the failure modes here are precisely
the ones that fire when it is unreachable. So the harness gets ordinary
deterministic tests, with the CLI stubbed.

Two of these pin bugs that shipped and were caught in an actual run:

- ``_cache_key`` hashed each artifact's absolute path, and the rendered
  prompt it also hashed embeds those paths a second time. Scenario
  artifacts live under ``tmp_path_factory`` directories that change every
  run, so the key never repeated, the cache never hit, and every
  invocation re-judged everything -- creating the burst of back-to-back
  CLI calls whose transient failures were the flakiness being blamed on
  the artifacts.
- An unreachable judge returned ``score=0.0, passed=False``, which is
  indistinguishable from a real verdict of zero. Scenario tests then
  reported that a redacted packet scored 0/10 when nothing had been
  judged at all.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.harness import ai

VERDICT = json.dumps({"score": 9, "hard_failures": [], "rationale": "fine"})


class _Proc:
    """The subset of CompletedProcess the judge reads."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _always(proc: _Proc) -> Callable[..., _Proc]:
    def run(*_args: Any, **_kwargs: Any) -> _Proc:
        return proc

    return run


def _in_turn(replies: list[_Proc], calls: list[int] | None = None) -> Callable[..., _Proc]:
    """Return each reply in order; record the call count if asked."""

    def run(*_args: Any, **_kwargs: Any) -> _Proc:
        if calls is not None:
            calls.append(1)
        return replies.pop(0) if len(replies) > 1 else replies[0]

    return run


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    yield


def _artifact(directory: Path, name: str = "artifact.pdf", body: bytes = b"same bytes") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    f = directory / name
    f.write_bytes(body)
    return f


# ---------------------------------------------------------------------------
# Cache key: identical artifacts must key identically from any directory
# ---------------------------------------------------------------------------


def test_cache_key_ignores_the_directory_the_artifact_was_built_in(tmp_path: Path) -> None:
    """The regression that made the cache write-only: pytest tmp dirs change
    every run, so a path-sensitive key never repeats."""
    a = _artifact(tmp_path / "pytest-1" / "m0")
    b = _artifact(tmp_path / "pytest-2" / "m0")
    assert ai._cache_key("basis", [a]) == ai._cache_key("basis", [b])


def test_cache_key_still_tracks_contents_and_name(tmp_path: Path) -> None:
    a = _artifact(tmp_path / "one")
    changed = _artifact(tmp_path / "two", body=b"different bytes")
    renamed = _artifact(tmp_path / "three", name="other.pdf")
    assert ai._cache_key("b", [a]) != ai._cache_key("b", [changed])
    assert ai._cache_key("b", [a]) != ai._cache_key("b", [renamed])
    assert ai._cache_key("b", [a]) != ai._cache_key("different basis", [a])


def test_threshold_participates_in_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`passed` is cached next to `score`, so a cache keyed without the
    threshold would serve a pass/fail decided against a different bar."""
    monkeypatch.setattr(subprocess, "run", _always(_Proc(stdout=VERDICT)))
    f = _artifact(tmp_path / "a")
    lenient = ai.judge(task="t", rubric="r", files=[f], threshold=7)
    strict = ai.judge(task="t", rubric="r", files=[f], threshold=9.5)
    assert lenient.passed
    assert not strict.passed
    assert not strict.cached, "a stricter threshold reused the lenient verdict"


def test_second_judgment_of_the_same_artifact_hits_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the key fix: a rerun must not call the CLI."""
    calls: list[int] = []
    monkeypatch.setattr(subprocess, "run", _in_turn([_Proc(stdout=VERDICT)], calls))

    first = _artifact(tmp_path / "pytest-1" / "m0")
    j1 = ai.judge(task="t", rubric="r", files=[first])
    assert j1.passed
    assert not j1.cached
    assert len(calls) == 1

    # Same artifact, rebuilt into the next run's tmp directory.
    second = _artifact(tmp_path / "pytest-2" / "m0")
    j2 = ai.judge(task="t", rubric="r", files=[second])
    assert j2.cached, "rerun re-judged an unchanged artifact"
    assert len(calls) == 1, "cache hit still shelled out to the CLI"


# ---------------------------------------------------------------------------
# Unreachable is not a verdict
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("proc", "label"),
    [
        (
            _Proc(stdout="", stderr="Not logged in · Please run /login", returncode=1),
            "auth failure",
        ),
        (_Proc(stdout="I'm sorry, I can't do that.", returncode=0), "prose reply"),
    ],
)
def test_unreachable_judge_is_flagged_not_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, proc: _Proc, label: str
) -> None:
    monkeypatch.setattr(subprocess, "run", _always(proc))
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.unavailable, f"{label} was reported as a verdict"
    assert not j.passed


def test_timeout_is_unavailable_not_a_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> _Proc:
        raise subprocess.TimeoutExpired("claude", 1)

    monkeypatch.setattr(subprocess, "run", boom)
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.unavailable
    assert "timed out" in j.rationale


def test_unreachable_verdicts_are_never_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caching a failure would freeze a transient outage into every later run."""
    monkeypatch.setattr(subprocess, "run", _always(_Proc(stdout="", returncode=1)))
    f = _artifact(tmp_path / "a")
    assert ai.judge(task="t", rubric="r", files=[f]).unavailable
    if ai.CACHE_DIR.exists():
        assert not list(ai.CACHE_DIR.glob("*.json"))

    monkeypatch.setattr(subprocess, "run", _always(_Proc(stdout=VERDICT)))
    assert ai.judge(task="t", rubric="r", files=[f]).passed


def test_assert_judgment_skips_when_unavailable_and_fails_on_a_real_zero() -> None:
    # Skipped derives from BaseException, so it escapes pytest.raises(Exception)
    # and would silently skip this test instead of being asserted on.
    with pytest.raises(BaseException) as skipped:
        ai.assert_judgment(ai._unreachable("judge timed out"), "some check")
    assert skipped.typename == "Skipped", "an outage was reported as a failure"

    real = ai.Judgment(0.0, False, "the packet leaked sealed text")
    with pytest.raises(AssertionError, match="leaked sealed text"):
        ai.assert_judgment(real, "redaction")


def test_skip_if_unavailable_passes_a_real_verdict_through() -> None:
    ai.skip_if_unavailable(ai.Judgment(3.0, False, "genuinely bad"))


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------


def test_transient_failure_is_retried_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = [_Proc(stdout="", stderr="Not logged in", returncode=1), _Proc(stdout=VERDICT)]
    monkeypatch.setattr(subprocess, "run", _in_turn(replies))
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.passed
    assert not j.unavailable
    assert len(replies) == 1, "the retry did not consume the transient failure"


def test_retries_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(subprocess, "run", _in_turn([_Proc(stdout="", returncode=1)], calls))
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.unavailable
    assert len(calls) == ai.ATTEMPTS
