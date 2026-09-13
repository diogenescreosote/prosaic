"""The reviewer: one headless agent call per utterance.

Every utterance that is not a bare navigation cue goes to the agent
through `cli/agent-run` (the one seam to whatever headless agent CLI is
installed, ADR-0020) under the `listen` role, so a deployment routes it
to the model it wants (ADR-0044). The prompt carries the role's
instructions, the matter's session brief, the docset index, the current
page's text, the running notes for that page, and the last few
exchanges; the reply is one JSON object the session applies. The agent
never touches the matter directory: everything it needs is in the
prompt, and its only output is the JSON.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AGENT_RUN = ROOT / "cli" / "agent-run"
ROLES_DIR = Path(__file__).resolve().parent / "roles"

REPLY_SHAPE = """Reply with ONE JSON object and nothing else, of this shape:
{
  "kind": "question" | "ask" | "note" | "nav" | "noise",
  "page": "<Bates token the speaker is now on, or null if unchanged>",
  "question": "<the deposition question, cleaned up and made precise,
               when kind is question; else null>",
  "warning": "<one sentence if this question carries a risk the speaker
              should know before asking it; else null>",
  "reply": "<what to say back on the terminal: the answer to an ask, or a
            short reaction; one to four sentences; may be empty>",
  "note": "<an observation worth keeping under this record, when the
           utterance is an observation rather than a question; else null>",
  "realization": "<a cross-cutting insight this utterance surfaces, if any; else null>"
}
Kinds: "question" = a question the speaker intends to put to the witness (log it);
"ask" = the speaker is asking YOU something (answer it in reply);
"note" = an observation about the record; "nav" = only moving between pages;
"noise" = nothing usable (a fragment, a false start, background)."""


def load_role(name: str) -> str:
    p = ROLES_DIR / f"{name}.md"
    if not p.exists():
        raise SystemExit(
            f"listen: no role {name!r}; available: "
            + ", ".join(sorted(x.stem for x in ROLES_DIR.glob("*.md")))
        )
    return p.read_text(encoding="utf-8")


def build_prompt(
    role_text: str,
    brief: str,
    index_lines: list[str],
    page_bates: str,
    page_title: str,
    page_text: str,
    page_questions: list[str],
    recent: list[dict[str, str]],
    utterance: str,
) -> str:
    parts = [role_text.strip(), ""]
    if brief.strip():
        parts += ["# Session brief (matter-specific; authoritative)", "", brief.strip(), ""]
    parts += ["# The document set", "", "\n".join(index_lines[:400]), ""]
    parts += [
        f"# Current page: {page_bates}" + (f" ({page_title})" if page_title else ""),
        "",
        page_text.strip()[:6000] or "(no text on this page)",
        "",
    ]
    if page_questions:
        parts += ["# Questions already logged on this page", ""]
        parts += [f"- {q}" for q in page_questions[-12:]]
        parts.append("")
    if recent:
        parts += ["# Recent exchanges (oldest first)", ""]
        for r in recent[-6:]:
            parts.append(f"- [{r.get('page', '')}] speaker: {r.get('said', '')}")
            if r.get("reply"):
                parts.append(f"  you: {r['reply']}")
        parts.append("")
    parts += [
        "# The utterance (machine transcription; may contain errors)",
        "",
        utterance.strip(),
        "",
    ]
    parts += [REPLY_SHAPE]
    return "\n".join(parts)


_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_reply(raw: str) -> dict[str, Any]:
    """The first JSON object in the agent's output; a bare reply when none."""
    m = _JSON_RE.search(raw or "")
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                obj.setdefault("kind", "note")
                return obj
        except json.JSONDecodeError:
            pass
    text = (raw or "").strip()
    return {
        "kind": "ask" if text else "noise",
        "reply": text,
        "page": None,
        "question": None,
        "warning": None,
        "note": None,
        "realization": None,
    }


def call_agent(
    prompt: str, role: str = "listen", timeout: int = 120, model: str | None = None
) -> dict[str, Any]:
    cmd = [str(AGENT_RUN), "--role", role, "--max-turns", "1"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return {
            "kind": "noise",
            "reply": "(the reviewer timed out; say it again)",
            "page": None,
            "question": None,
            "warning": None,
            "note": None,
            "realization": None,
            "_error": "timeout",
        }
    if proc.returncode != 0 and not proc.stdout.strip():
        return {
            "kind": "noise",
            "reply": f"(reviewer failed: {proc.stderr.strip()[-200:]})",
            "page": None,
            "question": None,
            "warning": None,
            "note": None,
            "realization": None,
            "_error": proc.stderr.strip()[-500:],
        }
    return parse_reply(proc.stdout)


def synthesis_prompt(role_text: str, brief: str, notes_md: str) -> str:
    return "\n".join(
        [
            role_text.strip(),
            "",
            "# Session brief",
            "",
            brief.strip(),
            "",
            "# The session's notes so far",
            "",
            notes_md,
            "",
            "# Task",
            "",
            "The session is ending. Write the closing synthesis as Markdown (no JSON): "
            "(1) the themes the questions fall into and a sensible order to take them in; "
            "(2) questions the notes suggest but nobody asked for yet; "
            "(3) the risks flagged during the session, consolidated; "
            "(4) what the record still cannot answer and who could. "
            "Be concrete and brief; cite records by Bates number.",
        ]
    )


def call_agent_text(
    prompt: str, role: str = "listen", timeout: int = 240, model: str | None = None
) -> str:
    cmd = [str(AGENT_RUN), "--role", role, "--max-turns", "1"]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "(synthesis timed out)"
    return proc.stdout.strip() or f"(synthesis failed: {proc.stderr.strip()[-200:]})"
