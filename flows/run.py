#!/usr/bin/env python3
"""run.py — execute a files-first flow (ADR-0024).

A flow is a YAML file describing judgment work as a graph the way a
Makefile describes build work as a DAG: ordered steps, four kinds,
one loop construct. Everything a step produces is a file in the run
directory, so a human can read, edit, or replace any intermediate,
and a stopped run resumes from its files rather than from memory.

Step kinds
    agent    render `prompt`, run it through cli/agent-run, write
             stdout to the step's output file
    command  run a shell command, write stdout to the output file
    judge    an agent step that must answer with JSON
             {"score": 0-10, "rationale": "..."}; score < threshold
             jumps back to `on_fail` (at most `max_rounds` times),
             score >= threshold continues
    gate     stop and wait for a human: writes APPROVAL-<id>.pending
             and exits 3; a rerun proceeds once the human renames it
             to APPROVAL-<id>.approved

Prompts are templates: {name} substitutes an input value or, for a
prior step, the PATH of that step's output file — agent steps are
granted read access to the run directory, and telling an agent where
a file is beats inlining it. State (completed steps, loop counts)
lives in state.json beside the outputs; --resume <rundir> continues
an interrupted or gated run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

PROSAIC_ROOT = Path(__file__).resolve().parent.parent
AGENT_RUN = PROSAIC_ROOT / "cli" / "agent-run"

GATE_EXIT = 3

JUDGE_INSTRUCTIONS = """

Respond with ONLY a JSON object, no other text:
{{"score": <0-10 number>, "rationale": "<2-4 sentences>"}}"""


class FlowError(SystemExit):
    pass


def load_flow(path: Path) -> dict:
    flow = yaml.safe_load(path.read_text())
    for field in ("name", "steps"):
        if field not in flow:
            raise FlowError(f"{path}: flow has no `{field}`")
    ids = [s.get("id") for s in flow["steps"]]
    if len(ids) != len(set(ids)) or not all(ids):
        raise FlowError(f"{path}: step ids must exist and be unique")
    for step in flow["steps"]:
        if step.get("kind") not in ("agent", "command", "judge", "gate"):
            raise FlowError(
                f"{path}: step {step.get('id')}: unknown kind "
                f"{step.get('kind')!r} (agent|command|judge|gate)"
            )
        if step["kind"] == "judge" and step.get("on_fail") not in (None, *ids):
            raise FlowError(f"{path}: step {step['id']}: on_fail names no step")
    return flow


def render(template: str, values: dict[str, str], where: str) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise FlowError(
                f"{where}: no value for {{{key}}} (inputs and prior step ids are available)"
            )
        return values[key]

    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", sub, template)


def run_agent(prompt: str, rundir: Path, yolo: bool) -> str:
    cmd = [str(AGENT_RUN), "--dir", str(rundir)]
    if yolo:
        cmd.append("--yolo")
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FlowError(f"agent step failed: {proc.stderr.strip()[:400]}")
    return proc.stdout


def parse_verdict(raw: str, step_id: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise FlowError(f"judge {step_id}: no JSON verdict in reply: {raw[:200]}")
    try:
        verdict = json.loads(m.group(0))
        return {"score": float(verdict["score"]), "rationale": str(verdict.get("rationale", ""))}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise FlowError(f"judge {step_id}: unusable verdict ({e}): {raw[:200]}") from None


def execute(flow: dict, inputs: dict[str, str], rundir: Path) -> int:
    state_path = rundir / "state.json"
    state = (
        json.loads(state_path.read_text())
        if state_path.exists()
        else {"completed": [], "rounds": {}}
    )

    def save() -> None:
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    for name in flow.get("inputs", []):
        if name not in inputs:
            raise FlowError(f"flow needs --input {name}=...")

    values = dict(inputs)
    steps = flow["steps"]
    index = {s["id"]: i for i, s in enumerate(steps)}
    # Rebuild prior outputs' paths so resume sees the same values.
    for s in steps:
        if s["id"] in state["completed"] and s["kind"] != "gate":
            values[s["id"]] = str(rundir / s.get("output", f"{s['id']}.md"))

    i = 0
    while i < len(steps):
        step = steps[i]
        sid = step["id"]
        out_path = rundir / step.get("output", f"{sid}.md")

        if sid in state["completed"]:
            i += 1
            continue

        if step["kind"] == "gate":
            approved = rundir / f"APPROVAL-{sid}.approved"
            pending = rundir / f"APPROVAL-{sid}.pending"
            if approved.exists():
                print(f"[{sid}] approved")
                state["completed"].append(sid)
                save()
                i += 1
                continue
            pending.write_text(
                (step.get("message", "Approve to continue."))
                + "\n\nTo approve: rename this file to "
                + approved.name
                + " and rerun with --resume.\n"
            )
            print(f"[{sid}] waiting for human approval: {pending}")
            save()
            return GATE_EXIT

        if step["kind"] == "command":
            cmd = render(step["command"], values, f"step {sid}")
            print(f"[{sid}] $ {cmd}")
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode != 0:
                raise FlowError(f"step {sid} failed: {proc.stderr.strip()[:400]}")
            out_path.write_text(proc.stdout)

        elif step["kind"] == "agent":
            prompt = render(step["prompt"], values, f"step {sid}")
            print(f"[{sid}] agent...")
            out_path.write_text(run_agent(prompt, rundir, bool(step.get("yolo"))))

        elif step["kind"] == "judge":
            prompt = render(step["prompt"], values, f"step {sid}") + JUDGE_INSTRUCTIONS.format()
            print(f"[{sid}] judge...")
            verdict = parse_verdict(run_agent(prompt, rundir, False), sid)
            out_path.write_text(json.dumps(verdict, indent=2) + "\n")
            threshold = float(step.get("threshold", 7))
            if verdict["score"] < threshold:
                rounds = state["rounds"].get(sid, 0) + 1
                state["rounds"][sid] = rounds
                target = step.get("on_fail")
                limit = int(step.get("max_rounds", 3))
                print(
                    f"[{sid}] score {verdict['score']} < {threshold} "
                    f"(round {rounds}/{limit}): {verdict['rationale']}"
                )
                if target is None or rounds >= limit:
                    save()
                    raise FlowError(f"judge {sid} failed after {rounds} round(s)")
                # Loop: everything from the target forward runs again.
                for s in steps[index[target] : i]:
                    if s["id"] in state["completed"]:
                        state["completed"].remove(s["id"])
                save()
                i = index[target]
                continue
            print(f"[{sid}] score {verdict['score']} >= {threshold}")

        values[sid] = str(out_path)
        state["completed"].append(sid)
        save()
        i += 1

    print(f"flow complete: {rundir}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a files-first flow")
    parser.add_argument("flow", help="path to a flow YAML")
    parser.add_argument("--input", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--resume", metavar="RUNDIR", help="continue an existing run directory")
    args = parser.parse_args()

    flow = load_flow(Path(args.flow))
    inputs = {}
    for pair in args.input:
        key, sep, value = pair.partition("=")
        if not sep:
            raise FlowError(f"--input wants KEY=VALUE, got {pair!r}")
        inputs[key] = value

    if args.resume:
        rundir = Path(args.resume)
        if not (rundir / "state.json").exists():
            raise FlowError(f"{rundir} is not a flow run directory")
        saved = json.loads((rundir / "inputs.json").read_text())
        saved.update(inputs)
        inputs = saved
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        rundir = Path(".flow") / f"{flow['name']}-{stamp}"
        rundir.mkdir(parents=True)
        (rundir / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")

    sys.exit(execute(flow, inputs, rundir))


if __name__ == "__main__":
    main()
