"""The AI judge harness itself (design/adr/0008).

The judged scenario tests cannot check these properties: they need a
reachable judge to run at all, and the failure modes here are precisely
the ones that fire when it is unreachable. So the harness gets ordinary
deterministic tests, with the CLI stubbed.

Two of these pin bugs that shipped and were caught in an actual run:

- ``_cache_key`` hashed each artifact's absolute path. Scenario
  artifacts live under ``tmp_path_factory`` directories that change
  every run, so the key never repeated, the cache never hit, and every
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

import pytest

from tests.harness import ai


VERDICT = json.dumps({"score": 9, "hard_failures": [], "rationale": "fine"})


class _Proc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(ai.time, "sleep", lambda _s: None)


def _artifact(directory, name="artifact.pdf", body=b"same bytes"):
    directory.mkdir(parents=True, exist_ok=True)
    f = directory / name
    f.write_bytes(body)
    return f


# ---------------------------------------------------------------------------
# Cache key: identical artifacts must key identically from any directory
# ---------------------------------------------------------------------------

def test_cache_key_ignores_the_directory_the_artifact_was_built_in(tmp_path):
    """The regression that made the cache write-only: pytest tmp dirs change
    every run, so a path-sensitive key never repeats."""
    a = _artifact(tmp_path / "pytest-1" / "m0")
    b = _artifact(tmp_path / "pytest-2" / "m0")
    assert ai._cache_key("prompt", [a]) == ai._cache_key("prompt", [b])


def test_cache_key_still_tracks_contents_and_name(tmp_path):
    a = _artifact(tmp_path / "one")
    changed = _artifact(tmp_path / "two", body=b"different bytes")
    renamed = _artifact(tmp_path / "three", name="other.pdf")
    assert ai._cache_key("p", [a]) != ai._cache_key("p", [changed])
    assert ai._cache_key("p", [a]) != ai._cache_key("p", [renamed])
    assert ai._cache_key("p", [a]) != ai._cache_key("different prompt", [a])


def test_threshold_participates_in_the_key(tmp_path, monkeypatch):
    """`passed` is cached next to `score`, so a cache keyed without the
    threshold would serve a pass/fail decided against a different bar."""
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: _Proc(stdout=VERDICT))
    f = _artifact(tmp_path / "a")
    lenient = ai.judge(task="t", rubric="r", files=[f], threshold=7)
    strict = ai.judge(task="t", rubric="r", files=[f], threshold=9.5)
    assert lenient.passed and not strict.passed
    assert not strict.cached, "a stricter threshold reused the lenient verdict"


def test_second_judgment_of_the_same_artifact_hits_the_cache(tmp_path, monkeypatch):
    """The whole point of the key fix: a rerun must not call the CLI."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _Proc(stdout=VERDICT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    first = _artifact(tmp_path / "pytest-1" / "m0")
    j1 = ai.judge(task="t", rubric="r", files=[first])
    assert j1.passed and not j1.cached and len(calls) == 1

    # Same artifact, rebuilt into the next run's tmp directory.
    second = _artifact(tmp_path / "pytest-2" / "m0")
    j2 = ai.judge(task="t", rubric="r", files=[second])
    assert j2.cached, "rerun re-judged an unchanged artifact"
    assert len(calls) == 1, "cache hit still shelled out to the CLI"


# ---------------------------------------------------------------------------
# Unreachable is not a verdict
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("proc,label", [
    (_Proc(stdout="", stderr="Not logged in · Please run /login", returncode=1),
     "auth failure"),
    (_Proc(stdout="I'm sorry, I can't do that.", returncode=0), "prose reply"),
])
def test_unreachable_judge_is_flagged_not_scored(tmp_path, monkeypatch, proc, label):
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: proc)
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.unavailable, f"{label} was reported as a verdict"
    assert not j.passed


def test_timeout_is_unavailable_not_a_zero(tmp_path, monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", boom)
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.unavailable and "timed out" in j.rationale


def test_unreachable_verdicts_are_never_cached(tmp_path, monkeypatch):
    """Caching a failure would freeze a transient outage into every later run."""
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: _Proc(stdout="", returncode=1))
    f = _artifact(tmp_path / "a")
    assert ai.judge(task="t", rubric="r", files=[f]).unavailable
    assert not list(ai.CACHE_DIR.glob("*.json")) if ai.CACHE_DIR.exists() else True

    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: _Proc(stdout=VERDICT))
    assert ai.judge(task="t", rubric="r", files=[f]).passed


def test_assert_judgment_skips_when_unavailable_and_fails_on_a_real_zero():
    # Skipped derives from BaseException, so it escapes pytest.raises(Exception)
    # and would silently skip this test instead of being asserted on.
    with pytest.raises(BaseException) as skipped:
        ai.assert_judgment(ai._unreachable("judge timed out"), "some check")
    assert skipped.typename == "Skipped", "an outage was reported as a failure"

    real = ai.Judgment(0.0, False, "the packet leaked sealed text")
    with pytest.raises(AssertionError, match="leaked sealed text"):
        ai.assert_judgment(real, "redaction")


def test_skip_if_unavailable_passes_a_real_verdict_through():
    ai.skip_if_unavailable(ai.Judgment(3.0, False, "genuinely bad"))


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def test_transient_failure_is_retried_then_succeeds(tmp_path, monkeypatch):
    replies = [_Proc(stdout="", stderr="Not logged in", returncode=1),
               _Proc(stdout=VERDICT)]
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: replies.pop(0))
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.passed and not j.unavailable and not replies


def test_retries_are_bounded(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: (calls.append(1),
                                           _Proc(stdout="", returncode=1))[1])
    j = ai.judge(task="t", rubric="r", files=[_artifact(tmp_path / "a")])
    assert j.unavailable and len(calls) == ai.ATTEMPTS
