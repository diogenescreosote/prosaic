"""LLM-judge layer for scenario tests.

Some correctness properties of legal work product are mechanical
(a date field is empty; a page count is right) and some are judgments
(this rendered form is court-ready; this declaration reads like
competent legal writing). The mechanical ones are ordinary asserts;
the judgments are delegated to a headless Claude Code session that
inspects the artifacts and returns a structured verdict:

    {"score": 0-10, "hard_failures": [...], "rationale": "..."}

A check passes when score >= threshold AND no hard failure fired.

Design notes (see design/adr/0008 for the framework decision):
- The judge shells out to the ``claude`` CLI — the same harness
  prosaic's triage layer already requires. No API keys, no extra
  eval-framework dependency.
- Judged tests are marked ``@pytest.mark.ai`` and skip cleanly when
  the CLI is absent or PROSAIC_AI_TESTS=0. CI without AI still runs
  every deterministic check.
- Verdicts are cached per (prompt, file-hashes) under .ai_cache/ so
  reruns are cheap; delete the cache to re-judge.
- Judges are *strict by instruction* and every judgment's rationale is
  printed on failure, so a flaky verdict is diagnosable, not mystical.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".ai_cache"


def ai_available() -> bool:
    if os.environ.get("PROSAIC_AI_TESTS", "1") == "0":
        return False
    return shutil.which("claude") is not None


@dataclass
class Judgment:
    score: float
    passed: bool
    rationale: str
    hard_failures: list[str] = field(default_factory=list)
    raw: str = ""
    cached: bool = False


def _cache_key(prompt: str, files: list[Path]) -> str:
    h = hashlib.sha256(prompt.encode())
    for f in files:
        h.update(str(f).encode())
        h.update(hashlib.sha256(Path(f).read_bytes()).digest())
    return h.hexdigest()[:32]


def judge(task: str, rubric: str, files: list[Path] | tuple = (),
          hard_failures: list[str] | tuple = (), threshold: float = 7.0,
          timeout: int = 300) -> Judgment:
    """Ask the AI judge to score artifacts against a rubric.

    ``task``: one sentence describing what was produced and why.
    ``rubric``: what a 10 looks like, what costs points.
    ``files``: artifact paths the judge must inspect (PDF pages should
        be pre-rendered to PNG — the judge reads images natively).
    ``hard_failures``: conditions that force a fail regardless of score
        (e.g. "a signature or date line is pre-filled").
    """
    files = [Path(f) for f in files]
    for f in files:
        if not f.exists():
            return Judgment(0.0, False, f"artifact missing: {f}")

    prompt = f"""You are a strict quality judge for court-filing work product
produced by an automated system. Inspect the artifacts with your Read
tool, then return a verdict. Be adversarial: your job is to catch
problems a busy human would miss, not to be agreeable.

TASK UNDER TEST: {task}

ARTIFACTS (read every one):
{chr(10).join('- ' + str(f) for f in files)}

RUBRIC (what a 10/10 looks like; deviations cost points):
{rubric}

HARD FAILURES (any one of these = automatic fail, list which fired):
{chr(10).join('- ' + h for h in hard_failures) or '- (none)'}

Respond with ONLY a JSON object, no other text:
{{"score": <0-10 number>, "hard_failures": [<strings, empty if none>],
"rationale": "<2-4 sentences: the score's justification, worst problems first>"}}"""

    key = _cache_key(prompt, files)
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        d = json.loads(cache_file.read_text())
        return Judgment(d["score"], d["passed"], d["rationale"],
                        d.get("hard_failures", []), cached=True)

    # Headless sessions may only read inside their working directory;
    # test artifacts live in pytest tmp dirs, so grant each artifact's
    # parent explicitly.
    add_dirs: list[str] = []
    for d in {str(f.parent.resolve()) for f in files}:
        add_dirs += ["--add-dir", d]
    proc = subprocess.run(
        ["claude", "-p", prompt, *add_dirs],
        capture_output=True, text=True, timeout=timeout,
    )
    raw = proc.stdout.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return Judgment(0.0, False,
                        f"judge returned no JSON (exit {proc.returncode}): {raw[:400]}",
                        raw=raw)
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return Judgment(0.0, False, f"judge JSON unparseable: {e}: {raw[:400]}", raw=raw)

    score = float(d.get("score", 0))
    fails = [str(x) for x in (d.get("hard_failures") or [])]
    passed = score >= threshold and not fails
    j = Judgment(score, passed, str(d.get("rationale", "")), fails, raw=raw)

    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps({
        "score": j.score, "passed": j.passed, "rationale": j.rationale,
        "hard_failures": j.hard_failures}))
    return j


def assert_judgment(j: Judgment, context: str = "") -> None:
    """Assert helper producing a readable failure message."""
    assert j.passed, (
        f"AI judge failed {context}: score={j.score}/10"
        f"{' hard failures: ' + ', '.join(j.hard_failures) if j.hard_failures else ''}"
        f" — {j.rationale}"
    )
