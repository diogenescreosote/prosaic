#!/usr/bin/env python3
"""A listening session: talk through a document set, keep the notes.

    sc listen --role depo-prep --docset production.ocr.pdf \\
              --bates-first ACME00001 --index INDEX.md \\
              --brief src/depo/LISTEN_BRIEF.md --out src/depo/questions.md

The speaker pages through the Bates-stamped set and talks: questions to
put to a witness, observations, and questions for the reviewer. Each
utterance is transcribed locally, the page pointer follows along
(explicit cues first, then the words themselves), and the reviewer, one
headless agent call per utterance, logs questions under the record they
concern, warns about the ones that carry a risk, answers what it is
asked, and keeps the cross-cutting realizations. The notes file is
rewritten after every event; the transcript and the event stream sit
beside it. Ctrl-C ends the session with a closing synthesis.

Typed input works alongside the microphone (or instead of it, with
`--stdin-only`): a line is an utterance; `/page 17`, `/undo`, `/save`,
`/quit` are commands.
"""

from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from listen import agent as agent_mod
from listen import track
from listen.docset import Docset, Page, load_docset
from listen.notes import Notes

DIM, BOLD, RESET = "\x1b[2m", "\x1b[1m", "\x1b[0m"
BLUE, YELLOW, GREEN, RED = "\x1b[34m", "\x1b[33m", "\x1b[32m", "\x1b[31m"


def say(text: str, color: str = "") -> None:
    sys.stdout.write(f"{color}{text}{RESET}\n")
    sys.stdout.flush()


class Session:
    def __init__(
        self,
        ds: Docset,
        notes: Notes,
        role_text: str,
        brief: str,
        start_page: int = 1,
        agent_model: str | None = None,
        agent_role: str = "listen",
        quiet: bool = False,
    ):
        self.ds = ds
        self.notes = notes
        self.role_text = role_text
        self.brief = brief
        self.page = max(1, min(start_page, len(ds.pages)))
        self.agent_model = agent_model
        self.agent_role = agent_role
        self.recent: list[dict[str, str]] = []
        self.quiet = quiet

    # ------------------------------------------------------------ pages
    @property
    def cur(self) -> Page:
        return self.ds.pages[self.page - 1]

    def goto(self, number: int, why: str = "") -> None:
        number = max(1, min(number, len(self.ds.pages)))
        changed = number != self.page
        self.page = number
        p = self.cur
        rec = self.notes.records.get(p.bates)
        n_q = len(rec.questions) if rec else 0
        tag = f" {DIM}({why}){RESET}" if why and changed else ""
        say(
            f"{BOLD}{BLUE}→ {p.bates}{RESET}{BOLD}{'  ' + p.label if p.label else ''}{RESET}"
            f"{DIM}  [{n_q} q]{RESET}{tag}"
        )
        self.notes.log_event({"kind": "nav", "page": p.bates, "why": why})

    # ------------------------------------------------------------ input
    def handle(self, utterance: str) -> None:
        utt = utterance.strip()
        if not utt:
            return
        self.notes.log_transcript(utt, self.cur.bates)
        if not self.quiet:
            say(f"{DIM}you: {utt}{RESET}")

        cue = track.explicit_cue(utt, self.ds, self.page)
        if cue:
            self.goto(cue, "you said so")
            if len(utt.split()) <= 6:
                return
        else:
            guess = track.content_match(utt, self.ds, self.page)
            if guess:
                self.goto(guess, "sounds like this page")

        page = self.cur
        page_questions = (
            [q.text for q in self.notes.records[page.bates].questions]
            if page.bates in self.notes.records
            else []
        )
        prompt = agent_mod.build_prompt(
            self.role_text,
            self.brief,
            self.ds.index_lines(),
            page.bates,
            page.label,
            page.text,
            page_questions,
            self.recent,
            utt,
        )
        t0 = time.time()
        reply = agent_mod.call_agent(prompt, role=self.agent_role, model=self.agent_model)
        dt = time.time() - t0
        self.apply(utt, reply, dt)

    def apply(self, utt: str, reply: dict[str, Any], dt: float) -> None:
        kind = str(reply.get("kind") or "note")
        # The reviewer may move the pointer from context.
        page_ref = reply.get("page")
        if page_ref:
            n = self.ds.number_for(str(page_ref))
            if n and n != self.page:
                self.goto(n, "the reviewer thinks so")
        p = self.cur
        text_reply = (reply.get("reply") or "").strip()
        warning = (reply.get("warning") or "").strip()
        question = (reply.get("question") or "").strip()
        note = (reply.get("note") or "").strip()
        realization = (reply.get("realization") or "").strip()

        if kind == "question" and question:
            self.notes.add_question(p.bates, p.label, p.number, question, warning)
            say(f"{GREEN}Q {len(self.notes.records[p.bates].questions)} logged:{RESET} {question}")
        elif kind == "ask":
            self.notes.add_exchange(utt, text_reply, p.bates)
        if note:
            self.notes.add_note(p.bates, p.label, p.number, note)
            if kind == "note":
                say(f"{DIM}noted.{RESET}")
        if warning:
            say(f"{YELLOW}⚠ {warning}{RESET}")
        if text_reply and (kind != "question" or not warning or text_reply != warning):
            say(text_reply)
        if realization:
            self.notes.add_realization(realization)
            say(f"{BLUE}★ {realization}{RESET}")
        if kind == "noise" and not text_reply:
            say(f"{DIM}(nothing to log){RESET}")
        say(f"{DIM}{dt:.1f}s{RESET}")
        self.recent.append({"page": p.bates, "said": utt, "reply": text_reply or question})
        self.recent = self.recent[-8:]
        self.notes.log_event(
            {"kind": kind, "page": p.bates, "said": utt, "reply": reply, "seconds": round(dt, 1)}
        )
        self.notes.save()

    # ------------------------------------------------------------ commands
    def command(self, line: str) -> bool:
        """Returns False when the session should end."""
        parts = line[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in ("quit", "q", "exit", "done"):
            return False
        if cmd == "page" and arg:
            n = self.ds.number_for(arg) or (int(arg) if arg.isdigit() else None)
            if n:
                self.goto(n, "command")
            else:
                say(f"{RED}no such page: {arg}{RESET}")
        elif cmd == "undo":
            q = self.notes.undo_last_question()
            say(f"{DIM}removed: {q.text}{RESET}" if q else f"{DIM}nothing to undo{RESET}")
            self.notes.save()
        elif cmd == "save":
            self.notes.save()
            say(f"{DIM}saved {self.notes.out}{RESET}")
        elif cmd == "where":
            self.goto(self.page)
        elif cmd == "index":
            for line in self.ds.index_lines():
                say(f"{DIM}{line}{RESET}")
        else:
            say(f"{DIM}commands: /page N, /undo, /save, /where, /index, /quit{RESET}")
        return True

    def close(self, synthesis: bool) -> None:
        if synthesis and (self.notes.records or self.notes.exchanges):
            say(f"{DIM}closing synthesis…{RESET}")
            self.notes.synthesis = agent_mod.call_agent_text(
                agent_mod.synthesis_prompt(self.role_text, self.brief, self.notes.render()),
                role=self.agent_role,
                model=self.agent_model,
            )
        self.notes.save()
        say(f"{BOLD}notes: {self.notes.out}{RESET}")


def _stdin_thread(q: queue.Queue[str | None]) -> None:
    try:
        for line in sys.stdin:
            q.put(line.rstrip("\n"))
    except Exception:
        pass
    q.put(None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--role", default="depo-prep", help="reviewer role (listen/roles/<name>.md)")
    ap.add_argument("--docset", required=True, type=Path, help="the Bates-stamped PDF (OCR'd copy)")
    ap.add_argument("--bates-first", required=True, help="token stamped on page 1, e.g. ACME00001")
    ap.add_argument("--index", type=Path, help="Markdown index with a Bates column (titles)")
    ap.add_argument("--brief", type=Path, help="matter-specific session brief (Markdown)")
    ap.add_argument("--out", required=True, type=Path, help="the notes file to write")
    ap.add_argument("--heading", help="title for the notes file")
    ap.add_argument("--start", default="1", help="page or Bates token to start on")
    ap.add_argument("--stdin-only", action="store_true", help="no microphone; typed input only")
    ap.add_argument("--device", type=int, help="capture device index for whisper-stream")
    ap.add_argument("--whisper-model", type=Path, help="ggml model file")
    ap.add_argument("--agent-model", help="override the agent model for this session")
    ap.add_argument("--agent-role", default="listen", help="agent-run role name in matter.yaml")
    ap.add_argument("--no-synthesis", action="store_true", help="skip the closing synthesis")
    ap.add_argument("--quiet", action="store_true", help="do not echo transcribed utterances")
    args = ap.parse_args(argv)

    ds = load_docset(args.docset, args.bates_first, args.index)
    role_text = agent_mod.load_role(args.role)
    brief = args.brief.read_text(encoding="utf-8") if args.brief else ""
    args.out.parent.mkdir(parents=True, exist_ok=True)
    notes = Notes(
        out=args.out,
        heading=args.heading or f"Listening session: {args.role}",
        docset_name=args.docset.name,
        role=args.role,
    )
    start = ds.number_for(args.start) or (int(args.start) if args.start.isdigit() else 1)
    session = Session(
        ds,
        notes,
        role_text,
        brief,
        start_page=start,
        agent_model=args.agent_model,
        agent_role=args.agent_role,
        quiet=args.quiet,
    )

    say(
        f"{BOLD}listening session · {args.role} · {len(ds.pages)} pages · notes → {args.out}{RESET}"
    )
    q: queue.Queue[str | None] = queue.Queue()
    stream = None
    if not args.stdin_only:
        from listen.transcribe import DEFAULT_MODEL, WhisperStream

        stream = WhisperStream(model=args.whisper_model or DEFAULT_MODEL, device=args.device)
        stream.start()
        dev = stream.device if stream.device is not None else "default"
        say(f"{DIM}microphone on (device {dev}); pause to send; Ctrl-C to finish{RESET}")
        threading.Thread(target=lambda: _forward(stream.queue, q), daemon=True).start()
    threading.Thread(target=_stdin_thread, args=(q,), daemon=True).start()
    session.goto(start)

    ended = 0
    try:
        while True:
            item = q.get()
            if item is None:
                ended += 1
                if args.stdin_only or ended >= 2:
                    break
                continue
            if item.startswith("/"):
                if not session.command(item):
                    break
                continue
            session.handle(item)
    except KeyboardInterrupt:
        say("")
    finally:
        if stream:
            stream.stop()
        session.close(synthesis=not args.no_synthesis)
    return 0


def _forward(src: queue.Queue[str | None], dst: queue.Queue[str | None]) -> None:
    while True:
        item = src.get()
        dst.put(item)
        if item is None:
            return


if __name__ == "__main__":
    sys.exit(main())
