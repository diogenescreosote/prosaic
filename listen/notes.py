"""The notes file a listening session writes.

One Markdown file, rewritten after every event so it is always
organized rather than appended: a header, then one section per record
in Bates order holding the questions raised on that record (with any
warning the reviewer attached) and the observations made there, then
the cross-cutting realizations, then the closing synthesis if one was
made. The raw transcript and the event stream are sidecars beside it,
so nothing said is lost even when the notes are reorganized.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Question:
    text: str
    warning: str = ""
    at: str = ""


@dataclass
class Record:
    bates: str
    title: str
    order: int
    questions: list[Question] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Notes:
    out: Path
    heading: str
    docset_name: str
    role: str
    records: dict[str, Record] = field(default_factory=dict)
    realizations: list[str] = field(default_factory=list)
    exchanges: list[dict[str, str]] = field(default_factory=list)
    synthesis: str = ""
    question_order: list[str] = field(default_factory=list)
    started: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M"))

    # ------------------------------------------------------------ sidecars
    @property
    def transcript_path(self) -> Path:
        return self.out.with_suffix(".transcript.txt")

    @property
    def events_path(self) -> Path:
        return self.out.with_suffix(".events.jsonl")

    def log_transcript(self, text: str, page: str) -> None:
        with self.transcript_path.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] [{page}] {text}\n")

    def log_event(self, event: dict[str, Any]) -> None:
        event = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ content
    def record(self, bates: str, title: str, order: int) -> Record:
        r = self.records.get(bates)
        if r is None:
            r = Record(bates=bates, title=title, order=order)
            self.records[bates] = r
        elif title and not r.title:
            r.title = title
        return r

    def add_question(
        self, bates: str, title: str, order: int, text: str, warning: str = ""
    ) -> None:
        self.record(bates, title, order).questions.append(
            Question(text=text.strip(), warning=(warning or "").strip(), at=time.strftime("%H:%M"))
        )
        self.question_order.append(bates)

    def undo_last_question(self) -> Question | None:
        """Remove the most recently logged question, whatever page it is on."""
        while self.question_order:
            bates = self.question_order.pop()
            r = self.records.get(bates)
            if r and r.questions:
                return r.questions.pop()
        return None

    def add_note(self, bates: str, title: str, order: int, text: str) -> None:
        self.record(bates, title, order).notes.append(text.strip())

    def add_realization(self, text: str) -> None:
        if text and text.strip() not in self.realizations:
            self.realizations.append(text.strip())

    def add_exchange(self, asked: str, answered: str, page: str) -> None:
        self.exchanges.append({"asked": asked.strip(), "answered": answered.strip(), "page": page})

    # ------------------------------------------------------------ render
    def render(self) -> str:
        lines = [
            f"<!-- NOTREAL: working notes from a listening session ({self.role}); "
            f"machine-transcribed, not verified. Not a filed or served document. -->",
            "",
            f"# {self.heading}",
            "",
            f"Session started {self.started}. Docset: `{self.docset_name}`. "
            f"Transcript: `{self.transcript_path.name}`; events: `{self.events_path.name}`.",
            "",
        ]
        n_q = sum(len(r.questions) for r in self.records.values())
        lines += [
            f"{n_q} question(s) across {len(self.records)} record(s); "
            f"{len(self.realizations)} realization(s).",
            "",
        ]
        for r in sorted(self.records.values(), key=lambda r: r.order):
            lines.append(f"## {r.bates}" + (f" --- {r.title}" if r.title else ""))
            lines.append("")
            if r.questions:
                lines.append("**Questions**")
                lines.append("")
                for i, q in enumerate(r.questions, start=1):
                    lines.append(f"{i}. {q.text}")
                    if q.warning:
                        lines.append(f"   - ⚠ {q.warning}")
                lines.append("")
            if r.notes:
                lines.append("**Notes**")
                lines.append("")
                for n in r.notes:
                    lines.append(f"- {n}")
                lines.append("")
        if self.realizations:
            lines += ["## Realizations", ""]
            lines += [f"- {x}" for x in self.realizations]
            lines.append("")
        if self.exchanges:
            lines += ["## Advice given during the session", ""]
            for e in self.exchanges:
                lines.append(f"- **[{e['page']}] {e['asked']}** --- {e['answered']}")
            lines.append("")
        if self.synthesis:
            lines += ["## Closing synthesis", "", self.synthesis.strip(), ""]
        return "\n".join(lines)

    def save(self) -> None:
        tmp = self.out.with_suffix(self.out.suffix + ".tmp")
        tmp.write_text(self.render(), encoding="utf-8")
        tmp.replace(self.out)
