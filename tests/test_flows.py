"""The flow runner's promises, with a scripted fake agent.

PROSAIC_AGENT_CMD (the ADR-0020 custom-provider seam) stands in for a
real agent, so what is pinned is the runner itself: step order,
outputs as files, the judge loop with its round limit, the human
gate's stop-and-resume, and template rendering. No agent CLI, no
network, no model.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_PY = REPO_ROOT / "flows" / "run.py"

# A fake agent that answers by prompt content: judge prompts get the
# verdict scripted in verdicts.txt (one JSON per line, consumed in
# order); anything else echoes a marker plus the prompt it received.
FAKE_AGENT = r"""
prompt=$(cat)
case "$prompt" in
  *"score"*)
    verdicts="$FAKE_VERDICTS"
    head -1 "$verdicts"
    tail -n +2 "$verdicts" > "$verdicts.tmp" && mv "$verdicts.tmp" "$verdicts"
    ;;
  *) printf 'AGENT-OUTPUT\n---\n%s\n' "$prompt" ;;
esac
"""

FLOW = """
name: testflow
description: exercise every step kind
inputs:
  - source
steps:
  - id: draft
    kind: agent
    prompt: "Work on {source}."
  - id: shout
    kind: command
    command: "tr a-z A-Z < {draft}"
    output: shout.txt
  - id: check
    kind: judge
    threshold: 8
    on_fail: draft
    max_rounds: 3
    prompt: "Score the work at {shout}. score"
  - id: approve
    kind: gate
    message: "Look before it ships."
  - id: after
    kind: command
    command: "echo done-after-gate"
"""


def run_flow(
    tmp_path: Path, *args: str, verdicts: list[dict[str, object]] | None = None
) -> subprocess.CompletedProcess[str]:
    (tmp_path / "flow.yaml").write_text(FLOW)
    (tmp_path / "src.md").write_text("the source document\n")
    vfile = tmp_path / "verdicts.txt"
    if verdicts is not None:
        vfile.write_text("".join(json.dumps(v) + "\n" for v in verdicts))
    return subprocess.run(
        [sys.executable, str(RUN_PY), "flow.yaml", *args],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PROSAIC_AGENT_CMD": FAKE_AGENT, "FAKE_VERDICTS": str(vfile), "PATH": "/usr/bin:/bin"},
    )


def rundir(tmp_path: Path) -> Path:
    runs = list((tmp_path / ".flow").iterdir())
    assert len(runs) == 1, runs
    return runs[0]


def test_happy_path_stops_at_the_gate_with_files_on_disk(tmp_path: Path) -> None:
    proc = run_flow(
        tmp_path, "--input", "source=src.md", verdicts=[{"score": 9, "rationale": "fine"}]
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr  # gate stop
    rd = rundir(tmp_path)
    draft = (rd / "draft.md").read_text()
    assert "Work on src.md." in draft, "prompt must receive the input value"
    assert (rd / "shout.txt").read_text().startswith("AGENT-OUTPUT")
    verdict = json.loads((rd / "check.md").read_text())
    assert verdict["score"] == 9
    assert (rd / "APPROVAL-approve.pending").exists()
    assert not (rd / "after.md").exists(), "nothing past a gate may run"


def test_approved_gate_resumes_and_finishes(tmp_path: Path) -> None:
    run_flow(tmp_path, "--input", "source=src.md", verdicts=[{"score": 9, "rationale": "fine"}])
    rd = rundir(tmp_path)
    (rd / "APPROVAL-approve.pending").rename(rd / "APPROVAL-approve.approved")
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "flow.yaml", "--resume", str(rd)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            "PROSAIC_AGENT_CMD": FAKE_AGENT,
            "FAKE_VERDICTS": str(tmp_path / "verdicts.txt"),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (rd / "after.md").read_text().strip() == "done-after-gate"


def test_failing_judge_loops_back_then_gives_up(tmp_path: Path) -> None:
    proc = run_flow(
        tmp_path,
        "--input",
        "source=src.md",
        verdicts=[
            {"score": 2, "rationale": "weak"},
            {"score": 3, "rationale": "still weak"},
            {"score": 4, "rationale": "no"},
        ],
    )
    assert proc.returncode not in (0, 3)
    assert "failed after 3 round(s)" in proc.stderr
    # The loop re-ran the draft step each round.
    assert proc.stdout.count("[draft] agent...") == 3


def test_failing_judge_recovers_when_a_later_round_passes(tmp_path: Path) -> None:
    proc = run_flow(
        tmp_path,
        "--input",
        "source=src.md",
        verdicts=[{"score": 2, "rationale": "weak"}, {"score": 9, "rationale": "fixed"}],
    )
    assert proc.returncode == 3  # reached the gate
    verdict = json.loads((rundir(tmp_path) / "check.md").read_text())
    assert verdict["score"] == 9


def test_missing_input_is_a_clear_error(tmp_path: Path) -> None:
    proc = run_flow(tmp_path)
    assert proc.returncode not in (0, 3)
    assert "--input source=" in proc.stderr


def test_unknown_placeholder_is_a_clear_error(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "name: bad\nsteps:\n  - id: a\n    kind: agent\n    prompt: 'use {nonexistent}'\n"
    )
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "bad.yaml"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PROSAIC_AGENT_CMD": FAKE_AGENT, "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode not in (0, 3)
    assert "nonexistent" in proc.stderr


def test_malformed_flow_is_rejected_before_anything_runs(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("name: bad\nsteps:\n  - id: a\n    kind: frobnicate\n")
    proc = subprocess.run(
        [sys.executable, str(RUN_PY), "bad.yaml"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode not in (0, 3)
    assert "unknown kind" in proc.stderr
    assert not (tmp_path / ".flow").exists()


def test_shipped_flows_parse(tmp_path: Path) -> None:
    """Every flow the repo ships must at least load."""
    flows = sorted((REPO_ROOT / "flows").glob("*.yaml"))
    assert flows, "no shipped flows found"
    for flow in flows:
        proc = subprocess.run(
            [sys.executable, str(RUN_PY), str(flow)],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
        )
        # Missing inputs is fine (they parse first); unknown kind etc. is not.
        assert "unknown kind" not in proc.stderr, f"{flow.name}: {proc.stderr}"
        assert "must exist and be unique" not in proc.stderr, flow.name
