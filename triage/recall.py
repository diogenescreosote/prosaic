#!/usr/bin/env python3
"""Recall: the cheap search of what the humans already said.

The failure this exists to prevent: an agent asks the human a question
he answered yesterday, or repeats a description the vault has already
corrected, because searching the knowledge vault felt expensive. It is
not. The vault, the live lists and the per-message mail index are a few
megabytes of text; ripgrep reads them in well under a second, and the
answer, trimmed and capped, costs a few hundred tokens. So recall is
meant to run before every question to the human and before every
statement about what a document is.

Two operations, both reachable as ``sc`` subcommands:

    recall.py recall <term...> [--matter DIR] [--max N] [--any] [--window N]
                     [-F] [--transcripts [SOURCE]]
    recall.py open-questions <draft.md> [--matter DIR] [--pattern RE]
                     [--top N] [--terms N] [--transcripts [SOURCE]]

``recall`` searches only the knowledge surfaces (SURFACES below), not
the whole record: ``sc find`` is the exhaustive search of the evidence.
Several terms mean AND within a small line window by default, because a
fact recorded in a note usually spans a sentence or two and OR over
several words floods the output; ``--any`` gives OR.

``open-questions`` pulls the placeholders out of a draft (``[XX: ...]``
initials notes, ``[Confirm ...]``, ``[Verify ...]``, ``[TODO ...]``) and
runs recall for each with keywords drawn from the placeholder and the
text just before it, so a draft is filled from recorded answers before
anyone is asked anything. A placeholder is not evidence that the
question is open.

Transcripts of coding-agent sessions are an optional, pluggable source
(TRANSCRIPT_SOURCES), off by default. Only text the human typed is
searched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

#: The human-knowledge surfaces, in display priority: notes first, the
#: generated index after them (it repeats note lines), then the live
#: lists, then the mail index. Directories are searched for `.md` only.
SURFACES: tuple[str, ...] = (
    "knowledge",
    "KNOWLEDGE.md",
    "QUESTIONS.md",
    "TODO.md",
    "derived/mail/messages.tsv",
)

DEFAULT_MAX_HITS = 40
DEFAULT_WINDOW = 3
SNIPPET_CHARS = 160
#: The draft text before a placeholder that keywords are drawn from.
CONTEXT_CHARS = 200
DEFAULT_TOP = 3
DEFAULT_TERMS = 4

#: Placeholders a drafter leaves for the human: initials notes such as
#: `[AB: ...]`, and the usual open markers. Case-insensitive words; the
#: initials stay upper-case so prose in brackets is not caught.
DEFAULT_PLACEHOLDER = r"\[(?:[A-Z]{2,3}:|(?i:confirm|verify|todo|tbd|check|ask)\b)[^\]]*\]"

_STOPWORD_TEXT = """
    a about above after again against all also am an and any are as at be because been
    before being below between both but by can could did do does doing done down during
    each either else ever every few for from further had has have having he her here hers
    herself him himself his how however i if in into is it its itself just let like may
    me might more most much must my myself no nor not now of off on once only or other
    our ours ourselves out over own per same say said says she should since so some such
    than that the their theirs them themselves then there these they this those though
    through to too under until up upon us very via was we were what when where whether
    which while who whom whose why will with within without would yes yet you your yours
    yourself one two three first second third last next new old get got make made see
    seen know known think thought want wanted need needed use used please ok okay
    confirm verify todo tbd check ask question answer fill insert add exact exactly
    date dates day days time times number amount name names whatever something anything
    paragraph para section page line here there below above draft decl declaration
    exhibit attachment court petitioner respondent plaintiff defendant party parties
    counsel attorney honor judge order motion hearing filed filing case matter record
    true correct right wrong really still even actually probably maybe perhaps likely
"""
STOPWORDS = frozenset(_STOPWORD_TEXT.split())

_MONTH_TEXT = (
    "january february march april may june july august september october november december"
)
MONTHS = _MONTH_TEXT.split()
MONTH_ABBR = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
_WEEKDAY_TEXT = "monday tuesday wednesday thursday friday saturday sunday"
WEEKDAYS = frozenset(_WEEKDAY_TEXT.split())

_QUOTED_RE = re.compile(r"\"([^\"\n]{3,60})\"|“([^”\n]{3,60})”")
_MONTH_RE = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
)
_DATE_WRITTEN_RE = re.compile(
    rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b"
)
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_SLASH_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_PROPER_RE = re.compile(r"\b[A-Z][A-Za-z'\u2019.-]*[A-Za-z](?:\s+[A-Z][A-Za-z'\u2019.-]*[A-Za-z])*")
_NUMBER_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?|\b\d{3,}(?:[.,]\d+)*\b")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\u2019-]{3,}")
_LABEL_RE = re.compile(r"^\[\s*(?:[A-Z]{2,3}:|(?i:confirm|verify|todo|tbd|check|ask)\b:?)\s*")
_HARNESS_TAG_RE = re.compile(r"<(system-reminder|command-[a-z]+)>.*?</\1>", re.S)
_WS_RE = re.compile(r"\s+")
#: A list marker and `[[stem]]:` label, as the generated index writes
#: them before a note's own line, or a heading or `title:` mark (a
#: note's title appears twice); stripped when comparing snippets.
_INDEX_PREFIX_RE = re.compile(r"^(?:[-*+]|\d+\.|#+|title:)?\s*(?:\[\[[^\]]+\]\]:?\s*)?")
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.S)


# --- terms and matching ------------------------------------------------


def compile_terms(terms: list[str], fixed: bool = False) -> list[re.Pattern[str]]:
    """Case-insensitive patterns; a term that is not a valid regex is
    taken literally rather than failing the search."""
    out: list[re.Pattern[str]] = []
    for t in terms:
        if fixed:
            out.append(re.compile(re.escape(t), re.I))
            continue
        try:
            out.append(re.compile(t, re.I))
        except re.error:
            out.append(re.compile(re.escape(t), re.I))
    return out


def snippet(text: str, pats: list[re.Pattern[str]], width: int = SNIPPET_CHARS) -> str:
    """About `width` characters of `text` around the first match."""
    flat = _WS_RE.sub(" ", text.replace("\t", " | ")).strip()
    starts = [m.start() for p in pats if (m := p.search(flat))]
    at = min(starts) if starts else 0
    if len(flat) <= width:
        return flat
    lo = max(0, min(at - width // 3, len(flat) - width))
    hi = lo + width
    return ("…" if lo else "") + flat[lo:hi].strip() + ("…" if hi < len(flat) else "")


@dataclass
class Hit:
    path: str  # display path: matter-relative, or transcript/<id>
    line: int
    text: str
    terms: set[int] = field(default_factory=set)  # term indexes on this line
    window: set[int] = field(default_factory=set)  # term indexes within the window
    rank: int = 0  # surface priority
    note: str = ""  # e.g. a transcript message's date


def _surface_rank(rel: str) -> int:
    for i, s in enumerate(SURFACES):
        if rel == s or rel.startswith(s + "/"):
            return i
    return len(SURFACES)


def surface_files(matter: Path) -> list[Path]:
    """Every file recall reads, for the no-rg fallback and the count."""
    out: list[Path] = []
    for s in SURFACES:
        p = matter / s
        if p.is_dir():
            out += sorted(q for q in p.rglob("*.md") if q.is_file())
        elif p.is_file():
            out.append(p)
    return out


def _existing_surfaces(matter: Path) -> list[str]:
    return [s for s in SURFACES if (matter / s).exists()]


def rg_command(terms: list[str], paths: list[str], fixed: bool = False) -> list[str]:
    cmd = ["rg", "-n", "-i", "--no-heading", "--with-filename", "--color", "never", "--no-ignore"]
    if fixed:
        cmd.append("-F")
    for t in terms:
        cmd += ["-e", t]
    return [*cmd, "--", *paths]


def _candidate_lines(
    matter: Path, terms: list[str], pats: list[re.Pattern[str]], fixed: bool
) -> Iterator[tuple[str, int, str]]:
    """(matter-relative path, line number, line) for every line carrying
    any term. ripgrep when present; a plain scan otherwise."""
    paths = _existing_surfaces(matter)
    if not paths:
        return
    if shutil.which("rg"):
        proc = subprocess.run(
            rg_command(terms, paths, fixed), cwd=matter, capture_output=True, text=True
        )
        if proc.returncode in (0, 1):
            for ln in proc.stdout.splitlines():
                m = re.match(r"^(.*?):(\d+):(.*)$", ln)
                if not m:
                    continue
                rel = m.group(1)
                if (matter / rel).is_dir() or (
                    rel.startswith("knowledge/") and not rel.endswith(".md")
                ):
                    continue
                yield rel, int(m.group(2)), m.group(3)
            return
    for f in surface_files(matter):
        rel = f.relative_to(matter).as_posix()
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines, 1):
            if any(p.search(ln) for p in pats):
                yield rel, i, ln


def search_surfaces(
    matter: Path,
    terms: list[str],
    *,
    mode: str = "all",
    window: int = DEFAULT_WINDOW,
    fixed: bool = False,
) -> list[Hit]:
    """Hits over SURFACES. mode "all": every term within `window` lines;
    "any": a line with at least one term (scored by how many)."""
    pats = compile_terms(terms, fixed)
    by_file: dict[str, dict[int, Hit]] = {}
    for rel, lno, text in _candidate_lines(matter, terms, pats, fixed):
        on = {i for i, p in enumerate(pats) if p.search(text)}
        if not on:
            continue  # rg and Python disagree on a regex; trust Python
        by_file.setdefault(rel, {})[lno] = Hit(rel, lno, text, on, set(on), _surface_rank(rel))
    want = set(range(len(pats)))
    out: list[Hit] = []
    for _rel, lines in by_file.items():
        for lno, h in lines.items():
            for d in range(-window, window + 1):
                other = lines.get(lno + d)
                if other is not None:
                    h.window |= other.terms
            if mode == "any" or h.window >= want:
                out.append(h)
    return out


# --- transcripts -------------------------------------------------------


#: Opening text of a user-role entry that the human did not type.
_NOT_HUMAN_PREFIXES = (
    "<task-notification",
    "<system-reminder",
    "<command-",
    "<local-command-",
    "<bash-",
    "<user-prompt-submit-hook",
    "Caveat:",
    "[Request interrupted",
)


def claude_code_dir(matter: Path) -> list[Path]:
    """Candidate Claude Code project directories for a matter: the slug
    is the absolute path with each non-alphanumeric character turned into
    `-`, and the matter may be reached through a symlink, so both the
    path as given and its resolution are tried."""
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    seen: list[Path] = []
    for p in (matter.absolute(), matter.resolve()):
        d = base / re.sub(r"[^A-Za-z0-9]", "-", str(p))
        if d.is_dir() and d not in seen:
            seen.append(d)
    return seen


def claude_code_user_texts(path: Path) -> Iterator[tuple[int, str, str]]:
    """(JSONL line, date, text) for each message the human typed."""
    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for i, ln in enumerate(fh, 1):
            if '"user"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if not isinstance(d, dict) or d.get("type") != "user":
                continue
            if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
                continue
            if "toolUseResult" in d:
                continue
            origin = d.get("origin")
            if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
                continue
            content = (d.get("message") or {}).get("content")
            if isinstance(content, str):
                parts = [content]
            elif isinstance(content, list):
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    continue
                parts = [
                    str(b.get("text", ""))
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
            else:
                continue
            text = _HARNESS_TAG_RE.sub("", "\n".join(parts)).strip()
            if not text or text.startswith(_NOT_HUMAN_PREFIXES):
                continue
            yield i, str(d.get("timestamp", ""))[:10], text


def search_claude_code(
    matter: Path, terms: list[str], pats: list[re.Pattern[str]], mode: str, fixed: bool
) -> list[Hit]:
    files: list[Path] = []
    for d in claude_code_dir(matter):
        files += sorted(d.glob("*.jsonl"))
    if not files:
        return []
    if shutil.which("rg"):
        # Prefilter: only sessions whose raw bytes carry some term.
        proc = subprocess.run(
            [
                "rg",
                "-l",
                "-i",
                *(["-F"] if fixed else []),
                *[a for t in terms for a in ("-e", t)],
                "--",
                *map(str, files),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode in (0, 1):
            files = [Path(p) for p in proc.stdout.splitlines() if p]
    want = set(range(len(pats)))
    out: list[Hit] = []
    for f in files:
        for lno, date, text in claude_code_user_texts(f):
            on = {i for i, p in enumerate(pats) if p.search(text)}
            if not on or (mode == "all" and on != want):
                continue
            out.append(Hit(f"transcript/{f.stem[:8]}", lno, text, on, on, len(SURFACES) + 1, date))
    return out


TranscriptSource = Callable[[Path, list[str], list[re.Pattern[str]], str, bool], list[Hit]]

#: Pluggable transcript sources, by name. Each takes (matter, terms,
#: patterns, mode, fixed) and returns hits carrying only human text.
TRANSCRIPT_SOURCES: dict[str, TranscriptSource] = {"claude-code": search_claude_code}


def search(
    matter: Path,
    terms: list[str],
    *,
    mode: str = "all",
    window: int = DEFAULT_WINDOW,
    fixed: bool = False,
    transcripts: str | None = None,
) -> list[Hit]:
    hits = search_surfaces(matter, terms, mode=mode, window=window, fixed=fixed)
    if transcripts:
        src = TRANSCRIPT_SOURCES.get(transcripts)
        if src is None:
            raise SystemExit(
                f"recall: unknown transcript source {transcripts!r} "
                f"(have: {', '.join(sorted(TRANSCRIPT_SOURCES))})"
            )
        hits += src(matter, terms, compile_terms(terms, fixed), mode, fixed)
    return hits


def dedupe(hits: list[Hit], pats: list[re.Pattern[str]]) -> list[tuple[Hit, str]]:
    """Each distinct snippet once (the generated index repeats notes)."""
    seen: set[str] = set()
    out: list[tuple[Hit, str]] = []
    for h in hits:
        s = snippet(h.text, pats)
        key = _INDEX_PREFIX_RE.sub("", _WS_RE.sub(" ", s.lower().strip("… ")))
        if key in seen:
            continue
        seen.add(key)
        out.append((h, s))
    return out


def _fmt(h: Hit, s: str) -> str:
    return f"{h.path}:{h.line}: " + (f"[{h.note}] " if h.note else "") + s


# --- recall ------------------------------------------------------------


def find_matter(start: Path) -> Path:
    here = start.expanduser().absolute()
    for cand in (here, *here.parents):
        if (cand / "matter.yaml").is_file():
            return cand
    raise SystemExit(f"recall: no matter.yaml at or above {start} (pass --matter)")


def format_recall(
    matter: Path,
    terms: list[str],
    hits: list[Hit],
    *,
    mode: str,
    window: int,
    max_hits: int,
    fixed: bool,
    transcripts: str | None,
    argv: list[str],
) -> str:
    pats = compile_terms(terms, fixed)
    joiner = " OR " if mode == "any" else " AND "
    what = joiner.join(repr(t) for t in terms)
    if mode == "all" and len(terms) > 1:
        what += f" (within {window} lines)"
    hits.sort(key=lambda h: (h.rank, -len(h.window), h.path, h.line))
    rows = dedupe(hits, pats)
    where = ", ".join(_existing_surfaces(matter)) or "(no knowledge surfaces)"
    if transcripts:
        where += f", {transcripts} transcripts"
    if not rows:
        tail = "" if transcripts else "; transcripts not searched (--transcripts)"
        return f"recall {what}: no hits in {where}{tail}\n"
    shown = rows if max_hits <= 0 else rows[:max_hits]
    nfiles = len({h.path for h, _ in rows})
    lines = [f"recall {what}: {len(rows)} hit(s) in {nfiles} file(s)"]
    prev = None
    for h, s in shown:
        if prev is not None and h.path != prev:
            lines.append("")
        prev = h.path
        lines.append(_fmt(h, s))
    if len(shown) < len(rows):
        rg = shlex.join(rg_command(terms, _existing_surfaces(matter), fixed))
        cwd = "" if Path.cwd().absolute() == matter else f"cd {shlex.quote(str(matter))} && "
        lines += [
            "",
            f"… {len(rows) - len(shown)} more hit(s) not shown. All of them: "
            f"{shlex.join(['sc', 'recall', *_without_max(argv), '--max', '0'])}",
            f"raw lines (any term, no window): {cwd}{rg}",
        ]
    if not transcripts:
        lines.append("(transcripts not searched; add --transcripts for what the human typed)")
    return "\n".join(lines) + "\n"


def _without_max(argv: list[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for a in argv:
        if skip:
            skip = False
        elif a == "--max":
            skip = True
        elif not a.startswith("--max="):
            out.append(a)
    return out


def cmd_recall(args: argparse.Namespace, argv: list[str]) -> int:
    matter = Path(args.matter).absolute() if args.matter else find_matter(Path.cwd())
    mode = "any" if args.any else "all"
    hits = search(
        matter,
        args.terms,
        mode=mode,
        window=args.window,
        fixed=args.fixed,
        transcripts=args.transcripts,
    )
    sys.stdout.write(
        format_recall(
            matter,
            args.terms,
            hits,
            mode=mode,
            window=args.window,
            max_hits=args.max,
            fixed=args.fixed,
            transcripts=args.transcripts,
            argv=argv,
        )
    )
    return 0 if hits else 1


# --- open questions ----------------------------------------------------


@dataclass
class Placeholder:
    line: int
    text: str  # the placeholder as written, whitespace collapsed
    inner: str  # without brackets and label
    context: str  # the draft text before it


def placeholders(text: str, pattern: str = DEFAULT_PLACEHOLDER) -> list[Placeholder]:
    rx = re.compile(pattern)
    out: list[Placeholder] = []
    fm = _FRONT_MATTER_RE.match(text)
    body_start = fm.end() if fm else 0
    for m in rx.finditer(text, body_start):
        raw = m.group(0)
        inner = _LABEL_RE.sub("", raw).rstrip("]").strip()
        before = text[max(body_start, m.start() - CONTEXT_CHARS) : m.start()]
        before = before.split("\n\n")[-1]  # this paragraph only
        before = rx.sub(" ", before)  # earlier placeholders are not context
        out.append(
            Placeholder(
                text.count("\n", 0, m.start()) + 1,
                _WS_RE.sub(" ", raw),
                inner,
                _WS_RE.sub(" ", before),
            )
        )
    return out


def _date_term(month: str, day: str, year: str | None) -> str:
    """A written date as a regex that also matches its ISO form."""
    mon = MONTH_ABBR[month[:3].lower()]
    d = int(day)
    written = rf"{month.rstrip('.')[:3]}[a-z]*\.?\s+{d}(?:st|nd|rd|th)?\b"
    if not year:
        return rf"(?:{written}|-{mon:02d}-{d:02d}\b)"
    return rf"(?:{written},?\s+{year}|{year}-{mon:02d}-{d:02d})"


def _is_stop(word: str) -> bool:
    w = word.lower().strip("'\u2019.-")
    w = re.sub(r"['\u2019]s$", "", w)
    return w in STOPWORDS or w in MONTHS or w in WEEKDAYS or w in MONTH_ABBR or w == "sept"


def keyword_pairs(inner: str, context: str, cap: int = DEFAULT_TERMS) -> list[tuple[str, str]]:
    """(regex, label) search terms for a placeholder, best first: quoted
    phrases, dates, runs of capitalized words, numbers, then content
    words. The placeholder's own text outranks the context before it."""
    cands: list[str] = []
    labels: dict[str, str] = {}

    def add(term: str, label: str | None = None) -> None:
        t = term.strip()
        if t and t.lower() not in (c.lower() for c in cands):
            cands.append(t)
            labels[t] = label or re.sub(r"\\(.)", r"\1", t)

    def proper(src: str) -> None:
        for m in _PROPER_RE.finditer(src):
            words = [w for w in m.group(0).split() if not _is_stop(w)]
            words = [re.sub(r"['\u2019]s$", "", w).rstrip(".") for w in words]
            if words and (len(words) > 1 or len(words[0]) >= 3):
                add(re.escape(" ".join(words)))

    def numbers(src: str) -> None:
        for m in _NUMBER_RE.finditer(src):
            n = m.group(0)
            if re.fullmatch(r"\d{4}", n) and any(n in c for c in cands):
                continue  # the year of a date already chosen
            add(re.escape(n))

    for src in (inner, context):
        for m in _QUOTED_RE.finditer(src):
            add(re.escape(m.group(1) or m.group(2)))
        for m in _DATE_WRITTEN_RE.finditer(src):
            add(_date_term(m.group(1), m.group(2), m.group(3)), m.group(0))
        for m in _DATE_ISO_RE.finditer(src):
            add(re.escape(m.group(0)))
        for m in _DATE_SLASH_RE.finditer(src):
            add(re.escape(m.group(0)))
        proper(src)
    numbers(inner)
    numbers(context)
    for m in _WORD_RE.finditer(inner):
        w = m.group(0)
        if not _is_stop(w) and not any(w.lower() in c.lower() for c in cands):
            add(re.escape(w.lower()))
    # A shorter term inside a longer one already chosen adds nothing.
    out: list[str] = []
    for c in cands:
        if any(c.lower() in o.lower() for o in out):
            continue
        out.append(c)
        if len(out) >= cap:
            break
    return [(c, labels[c]) for c in out]


def keywords(inner: str, context: str, cap: int = DEFAULT_TERMS) -> list[str]:
    """The regexes of keyword_pairs()."""
    return [r for r, _ in keyword_pairs(inner, context, cap)]


#: Live lists: a hit there says the question is already asked, not answered.
OPEN_LISTS = ("QUESTIONS.md", "TODO.md")


def format_open_questions(
    matter: Path,
    draft: Path,
    found: list[Placeholder],
    *,
    top: int,
    cap: int,
    transcripts: str | None,
) -> tuple[str, int]:
    try:
        rel = draft.absolute().relative_to(matter).as_posix()
    except ValueError:
        rel = str(draft)
    lines = [f"open questions in {rel}: {len(found)} placeholder(s)"]
    answered = listed = 0
    for ph in found:
        lines.append("")
        lines.append(f"L{ph.line} {ph.text if len(ph.text) <= 140 else ph.text[:139] + '…'}")
        pairs = keyword_pairs(ph.inner, ph.context, cap)
        terms = [r for r, _ in pairs]
        if not terms:
            lines.append("  (no searchable keywords; recall by hand)")
            continue
        lines.append("  terms: " + " · ".join(label for _, label in pairs))
        # Notes wrap, so a line is scored by the keywords on it and the
        # line either side; ties go to the line carrying more itself.
        hits = search(matter, terms, mode="any", window=1, transcripts=transcripts)
        hits.sort(key=lambda h: (-len(h.window), -len(h.terms), h.rank, h.path, h.line))
        rows: list[tuple[Hit, str]] = []
        # The record and the transcripts each get `top` slots, so a
        # remark the human typed is not crowded out by notes.
        for group in (False, True):
            pool = [h for h in hits if h.path.startswith("transcript/") == group]
            if len(terms) > 1:
                # One keyword on its own is weak evidence; prefer
                # passages that carry two when any do.
                pool = [h for h in pool if len(h.window) >= 2] or pool
            taken = 0
            for h, s in dedupe(pool, compile_terms(terms)):
                if any(o.path == h.path and abs(o.line - h.line) <= 2 for o, _ in rows):
                    continue  # the same passage, one line over
                rows.append((h, s))
                taken += 1
                if taken >= top:
                    break
        if not rows:
            lines.append("  (nothing recorded; ask the human)")
            continue
        if all(h.path in OPEN_LISTS for h, _ in rows):
            listed += 1
        else:
            answered += 1
        for h, s in rows:
            lines.append(
                f"  {h.path}:{h.line} ({len(h.window)}/{len(terms)}): "
                + (f"[{h.note}] " if h.note else "")
                + s
            )
    lines.append("")
    tally = f"{answered} of {len(found)} placeholder(s) have candidate answers on record"
    if listed:
        tally += f"; {listed} only already listed as open ({' / '.join(OPEN_LISTS)})"
    lines.append(
        tally + ". Read those sources before asking; a placeholder is not evidence "
        "the question is open."
    )
    return "\n".join(lines) + "\n", answered


def cmd_open_questions(args: argparse.Namespace) -> int:
    draft = Path(args.draft)
    if not draft.is_file():
        print(f"open-questions: no such file {draft}", file=sys.stderr)
        return 2
    matter = Path(args.matter).absolute() if args.matter else find_matter(draft.absolute().parent)
    found = placeholders(draft.read_text(encoding="utf-8", errors="replace"), args.pattern)
    if not found:
        print(f"open questions in {draft}: none (pattern {args.pattern})")
        return 1
    out, _ = format_open_questions(
        matter, draft, found, top=args.top, cap=args.terms, transcripts=args.transcripts
    )
    sys.stdout.write(out)
    return 0


# --- command line ------------------------------------------------------


def add_recall_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("terms", nargs="+", help="case-insensitive regexes")
    sp.add_argument(
        "--matter", metavar="DIR", help="matter directory (default: walk up from the cwd)"
    )
    sp.add_argument(
        "--max",
        metavar="N",
        type=int,
        default=DEFAULT_MAX_HITS,
        help=f"hits shown (default {DEFAULT_MAX_HITS}; 0 = all)",
    )
    sp.add_argument("--any", action="store_true", help="any term (OR); default every term")
    sp.add_argument(
        "--window",
        metavar="N",
        type=int,
        default=DEFAULT_WINDOW,
        help=f"lines within which every term must appear (default {DEFAULT_WINDOW})",
    )
    sp.add_argument("-F", "--fixed", action="store_true", help="literal terms, not regexes")
    sp.add_argument(
        "--transcripts",
        nargs="?",
        const="claude-code",
        default=None,
        metavar="SOURCE",
        help="also search what the human typed in agent sessions (default source: claude-code)",
    )


def add_open_questions_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("draft", help="the draft .md to scan")
    sp.add_argument(
        "--matter", metavar="DIR", help="matter directory (default: walk up from the draft)"
    )
    sp.add_argument(
        "--pattern", metavar="RE", default=DEFAULT_PLACEHOLDER, help="placeholder regex"
    )
    sp.add_argument(
        "--top", metavar="N", type=int, default=DEFAULT_TOP, help="hits per placeholder"
    )
    sp.add_argument(
        "--terms", metavar="N", type=int, default=DEFAULT_TERMS, help="keywords per placeholder"
    )
    sp.add_argument(
        "--transcripts",
        nargs="?",
        const="claude-code",
        default=None,
        metavar="SOURCE",
        help="also search agent-session transcripts",
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="recall", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="op", required=True)
    add_recall_args(sub.add_parser("recall"))
    add_open_questions_args(sub.add_parser("open-questions"))
    args = p.parse_args(argv)
    if args.op == "recall":
        return cmd_recall(args, argv[1:])
    return cmd_open_questions(args)


if __name__ == "__main__":
    raise SystemExit(main())
