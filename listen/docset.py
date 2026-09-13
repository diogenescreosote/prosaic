"""The document set a listening session follows along in.

A docset is one Bates-stamped PDF: page *n* of the file carries the
token `bates_first` advanced by n-1 (the same convention as the
renderer's `bates_first:` exhibit key). Each page has its text (from
the PDF's own text layer, so hand the OCR'd copy in) and a short title,
taken from an optional index file when one is given and from the page's
first line otherwise.

The index file is a Markdown document containing tables with a Bates
column: any row whose cells include a bare page number or range
(`00017`, `00001-02`, `00073-74`, en dash or hyphen) names the pages that row describes,
and the row's first prose cell (not a filename, not the number) is the
title. That is the shape a records-split index naturally takes, and it
is parsed heuristically on purpose: a title is a convenience for the
terminal, never something the session depends on.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

_BATES_RE = re.compile(r"^(?P<prefix>.*?)(?P<num>\d+)$")
_INDEX_REF_RE = re.compile(r"^\s*(\d{2,7})(?:\s*[\u2013\-]\s*(\d{1,7}))?\s*$")
_FILENAME_RE = re.compile(r"`[^`]*\.(?:pdf|md|txt|json)`|\.(?:pdf|md)\b", re.I)


@dataclass
class Page:
    number: int  # 1-based page of the file
    bates: str
    text: str
    title: str = ""
    index_title: str = ""

    @property
    def label(self) -> str:
        return self.index_title or self.title


@dataclass
class Docset:
    path: Path
    prefix: str
    start: int
    width: int
    pages: list[Page] = field(default_factory=list)

    # ------------------------------------------------------------ tokens
    def token(self, number: int) -> str:
        """Bates token for 1-based page `number`."""
        return f"{self.prefix}{str(self.start + number - 1).zfill(self.width)}"

    def number_for(self, ref: str) -> int | None:
        """Page number for a Bates token or a bare number ('17', '00017',
        'CAPINAS00017'); None when it is not in the set."""
        m = _BATES_RE.match(ref.strip())
        if not m:
            return None
        n = int(m.group("num"))
        if m.group("prefix") and m.group("prefix").strip().upper() != self.prefix.upper():
            return None
        page = n - self.start + 1
        return page if 1 <= page <= len(self.pages) else None

    def page(self, ref: str) -> Page | None:
        n = self.number_for(ref)
        return self.pages[n - 1] if n else None

    # ------------------------------------------------------------ titles
    def apply_index(self, index_md: str) -> None:
        for bates_from, bates_to, title in _parse_index(index_md):
            lo = self.number_for(bates_from)
            hi = self.number_for(bates_to) if bates_to else lo
            if lo is None:
                continue
            for n in range(lo, (hi or lo) + 1):
                if 1 <= n <= len(self.pages) and not self.pages[n - 1].index_title:
                    self.pages[n - 1].index_title = title

    def index_lines(self) -> list[str]:
        """One line per distinct titled run, for a prompt or a listing."""
        out: list[str] = []
        run_start: Page | None = None
        prev: Page | None = None
        for p in [*self.pages, None]:
            if p is not None and prev is not None and p.label == prev.label:
                prev = p
                continue
            if run_start is not None and prev is not None:
                span = (
                    run_start.bates
                    if run_start is prev
                    else f"{run_start.bates}--{prev.bates[len(self.prefix) :]}"
                )
                out.append(f"{span}: {run_start.label}")
            run_start, prev = p, p
        return out


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = " ".join(line.split())
        if len(line) >= 4 and not _BATES_RE.fullmatch(line.replace(" ", "")):
            return line[:80]
    return ""


def _parse_index(md: str) -> Iterator[tuple[str, str | None, str]]:
    """Yield (bates_from, bates_to_or_None, title) from Markdown table rows."""
    for line in md.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: "):
            continue
        ref = None
        for c in cells:
            m = _INDEX_REF_RE.match(c)
            if m:
                ref = m
                break
        if not ref:
            continue
        frm = ref.group(1)
        to = ref.group(2)
        if to and len(to) < len(frm):  # 00001-02 -> 00002
            to = frm[: len(frm) - len(to)] + to
        title = ""
        for c in cells:
            if c is ref.group(0) or _INDEX_REF_RE.match(c) or _FILENAME_RE.search(c):
                continue
            if c and c.lower() not in ("had", "new", "unclear"):
                title = c.strip("*").strip()
                break
        if not title:
            fn = next((c for c in cells if _FILENAME_RE.search(c)), "")
            title = fn.strip("`").rsplit(".", 1)[0].replace("_", " ")
        yield frm, to, title


def load_docset(pdf: Path, bates_first: str, index: Path | None = None) -> Docset:
    import fitz  # type: ignore[import-untyped]  # pymupdf

    m = _BATES_RE.match(bates_first.strip())
    if not m or not m.group("num"):
        raise ValueError(f"bates_first {bates_first!r} must end in the page-1 number")
    ds = Docset(
        path=pdf, prefix=m.group("prefix"), start=int(m.group("num")), width=len(m.group("num"))
    )
    doc = fitz.open(str(pdf))
    for i, page in enumerate(doc, start=1):
        text = page.get_text()
        ds.pages.append(Page(number=i, bates=ds.token(i), text=text, title=_first_line(text)))
    if index and index.exists():
        ds.apply_index(index.read_text(encoding="utf-8", errors="replace"))
    return ds
