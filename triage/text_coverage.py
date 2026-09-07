#!/usr/bin/env python3
"""Text coverage: is every document in the matter searchable, and prove it.

The failure this exists to prevent: a search over the record reports
"not found" while the passage sits in a PDF that ripgrep could never
read, because the PDF had no text sidecar --- or had an `_ocr.pdf`
sibling whose text never reached a `.txt` file. A document that was not
searched is not a document that says nothing, so coverage is audited
and repaired mechanically, never assumed.

Two operations:

    text_coverage.py audit  <matter> [--json] [--include-inbox]
    text_coverage.py ensure <matter> [--dry-run] [--include-inbox] [--redo-ocr] [--jobs N]

`audit` classifies every document under the matter (PDF, image, DOCX,
audio) as one of:

    searchable         a current sidecar covers every page
    unverified-sidecar a sidecar exists but was not written by this tool
                       (no header), so completeness cannot be checked;
                       it is searched, and reported
    needs-sidecar      the text layer is fine but no .txt sidecar exists
    stale-sidecar      the tool's own sidecar predates the document
    needs-ocr          pages lack a usable text layer and no _ocr sibling
                       covers them
    transcript-needed  audio without a transcript (the STT pipeline is
                       separate and local; this only reports)
    unsupported        a type nothing here can extract
    unreadable         the file could not be opened
    untriaged          under inbox/ (reported; not repaired unless asked)

`ensure` repairs what it can: OCR-supplements PDFs whose pages lack text
(`ocrmypdf --skip-text`, or `--force-ocr --pages` for pages that carry
useless text: image-bodied, garbled), then writes a text file from the
best available source with `[[[ page k of N ]]]` markers so a hit
carries a page cite. Images go through tesseract; DOCX through pandoc.

Layout (ADR-0041): derived artifacts live in a parallel tree that
mirrors the matter, never beside the original:

    derived/text/<relative path>.txt     page-marked text (tracked)
    derived/ocr/<relative path>          the OCR'd copy (regenerable; ignored)

so `assets/gmail/2026-01-02_letter.pdf` is searched through
`derived/text/assets/gmail/2026-01-02_letter.pdf.txt`, and its OCR'd copy,
if one was needed, is `derived/ocr/assets/gmail/2026-01-02_letter.pdf`.
Legacy siblings (`<stem>_ocr.pdf`, `<stem>.txt`, `<stem>.ocr.txt` beside
the original) are still recognized and searched; `migrate` moves the
ones this tool wrote into the tree. A `.txt` beside an original that
carries no header is a human transcription: read, reported as
unverified, never moved or overwritten.

Guarantees:
  * Originals are never modified. Everything written goes under derived/.
  * A text file not written by this tool (no header) is never overwritten.
  * The tool's own sidecar is rewritten only when the document or its
    `_ocr` sibling is newer than the sidecar.
  * Every classification is cached in .state/text_coverage.json keyed by
    path, size and mtime, so an audit over a thousand documents is fast
    and a changed file is always re-surveyed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import read_coverage as rc  # noqa: E402

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

# A corrupt or encrypted PDF is a classified row (`unreadable`), not a
# stack trace on stdout: silence MuPDF's error chatter and pymupdf's
# verbose exception printing, both of which write where the report goes.
try:
    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)
except Exception:  # pragma: no cover
    pass
for _flag in ("g_exceptions_verbose",):
    if hasattr(fitz, _flag):
        setattr(fitz, _flag, 0)

HEADER_MARK = "[[[ prosaic text sidecar ]]]"
BANNER = "MACHINE TEXT --- VERIFY AGAINST THE DOCUMENT BEFORE CITING IN ANY FILING"
CACHE_NAME = "text_coverage.json"

EXCLUDE_DIRS = frozenset({"out", ".state", ".git", ".flow", "node_modules", ".claude", ".venv",
                          "derived"})
DERIVED = "derived"
PDF_EXT = {".pdf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
IMAGE_UNSUPPORTED_EXT = {".heic", ".heif"}
DOCX_EXT = {".docx"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac"}

#: Pages whose extractable text cannot be trusted to speak for the page.
OCR_KINDS = frozenset(rc.UNCOVERED)          # image-bodied, sparse, image-only, garbled
#: Of those, the pages that already carry text (so --skip-text would leave them).
FORCE_KINDS = frozenset({"image-bodied", "garbled", "sparse"})


@dataclass
class Doc:
    path: str                      # relative to matter
    kind: str                      # pdf | image | docx | audio
    state: str
    pages: int = 0
    uncovered: list[int] = field(default_factory=list)
    sidecar: str = ""              # relative path of the .txt that is/would be searched
    source: str = ""               # relative path of the file the sidecar is/would be dumped from
    note: str = ""

    @property
    def searched(self) -> bool:
        return self.state in ("searchable", "unverified-sidecar")


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------

def _excluded(rel: Path, include_inbox: bool) -> bool:
    parts = set(rel.parts[:-1])
    if parts & EXCLUDE_DIRS:
        return True
    if not include_inbox and rel.parts[:1] == ("inbox",):
        return False  # kept, but reported as untriaged
    return False


def iter_documents(matter: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(matter.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        rel = p.relative_to(matter)
        if set(rel.parts[:-1]) & EXCLUDE_DIRS:
            continue
        ext = p.suffix.lower()
        if ext in PDF_EXT:
            if p.stem.endswith("_ocr"):
                continue  # a sibling, audited through its original
            out.append(p)
        elif ext in IMAGE_EXT | IMAGE_UNSUPPORTED_EXT | DOCX_EXT | AUDIO_EXT:
            out.append(p)
    return out


def _rel(matter: Path, doc: Path) -> Path:
    """Lexical path of `doc` under `matter`. Never resolves symlinks: an
    `assets/x.pdf` that links to `processed_files/x.pdf` is its own
    document with its own derived files, and the matter itself may sit
    behind a symlinked mount."""
    m = Path(os.path.abspath(matter))
    d = Path(os.path.abspath(doc))
    return d.relative_to(m)


def derived_text_path(matter: Path, doc: Path) -> Path:
    return matter / DERIVED / "text" / (str(_rel(matter, doc)) + ".txt")


def derived_ocr_path(matter: Path, doc: Path) -> Path:
    return matter / DERIVED / "ocr" / _rel(matter, doc)


def legacy_ocr_sibling(pdf: Path) -> Path:
    return pdf.with_name(pdf.stem + "_ocr.pdf")


def legacy_text_sibling(doc: Path) -> Path:
    if doc.suffix.lower() in IMAGE_EXT | IMAGE_UNSUPPORTED_EXT:
        return doc.with_name(doc.stem + ".ocr.txt")
    return doc.with_suffix(".txt")


def ocr_copy_for(matter: Path, pdf: Path) -> Path | None:
    """The OCR'd copy to read from, derived/ first, then the legacy sibling."""
    for cand in (derived_ocr_path(matter, pdf), legacy_ocr_sibling(pdf)):
        if cand.exists():
            return cand
    return None


def text_file_for(matter: Path, doc: Path) -> Path | None:
    """The text file that speaks for `doc`, derived/ first, then legacy
    siblings (the tool's old location, then a human `.txt`)."""
    cands = [derived_text_path(matter, doc), legacy_text_sibling(doc)]
    if doc.suffix.lower() in IMAGE_EXT | IMAGE_UNSUPPORTED_EXT:
        cands.append(doc.with_suffix(".txt"))
    for cand in cands:
        if cand.exists():
            return cand
    return None


# Back-compat names used by older callers and tests.
ocr_sibling = legacy_ocr_sibling
sidecar_for = legacy_text_sibling


def _header_pages(sidecar: Path) -> int | None:
    """Pages declared by this tool's header, or None if not our sidecar."""
    try:
        with sidecar.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
            if first != HEADER_MARK:
                return None
            for _ in range(8):
                ln = fh.readline()
                if ln.startswith("pages:"):
                    return int(ln.split(":", 1)[1].strip() or 0)
    except OSError:
        return None
    return 0


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

#: In an _ocr sibling, OCR has already run: a text layer over a full-page
#: raster is exactly what a successfully OCR'd scan looks like
#: (image-bodied), and a short note on a mostly blank page is sparse for
#: real. Only a page OCR left empty, or one whose text is nonsense, is
#: still uncovered there.
OCR_OUTPUT_UNCOVERED = frozenset({"image-only", "garbled"})


def _survey(path: Path, ocr_output: bool = False) -> tuple[int, list[int], list[str]]:
    """(pages, uncovered page numbers, kinds per page)."""
    s = rc.survey(str(path), rc.DEFAULT_MIN_CHARS)
    kinds = [d["kind"] for d in s["detail"]]
    bad = OCR_OUTPUT_UNCOVERED if ocr_output else OCR_KINDS
    unc = [d["page"] for d in s["detail"] if d["kind"] in bad]
    return s["pages"], unc, kinds


def classify_pdf(matter: Path, pdf: Path) -> Doc:
    rel = str(_rel(matter, pdf))
    ocr = ocr_copy_for(matter, pdf)
    best = ocr or pdf
    side = text_file_for(matter, pdf)
    target = derived_text_path(matter, pdf)
    d = Doc(path=rel, kind="pdf", state="",
            sidecar=str(_rel(matter, side or target)), source=str(_rel(matter, best)))
    try:
        pages, unc, _ = _survey(best, ocr_output=ocr is not None)
    except Exception as exc:  # encrypted, corrupt
        d.state = "unreadable"
        d.note = f"{type(exc).__name__}: {exc}"[:160]
        return d
    d.pages, d.uncovered = pages, unc
    if unc:
        d.state = "needs-ocr"
        if ocr is not None:
            d.note = (f"OCR ran and found no text on {len(unc)} of {pages} page(s): "
                      "likely a photo, graphic or blank scan; describe it in a "
                      "human text file if its content matters")
        else:
            d.note = f"{len(unc)} of {pages} page(s) lack a usable text layer"
        return d
    if side is None:
        d.state = "needs-sidecar"
        return d
    hp = _header_pages(side)
    if hp is None:
        d.state = "unverified-sidecar"
        d.note = "text file not written by this tool; completeness unknown"
        return d
    newest = max(pdf.stat().st_mtime, ocr.stat().st_mtime if ocr else 0)
    if side.stat().st_mtime < newest or hp != pages:
        d.state = "stale-sidecar"
        d.note = ("document newer than its text file" if hp == pages
                  else f"text file says {hp} pages, document has {pages}")
        return d
    d.state = "searchable"
    if side != target:
        d.note = "legacy location; `sc text migrate` moves it under derived/"
    return d


def classify_other(matter: Path, p: Path) -> Doc:
    rel = str(_rel(matter, p))
    ext = p.suffix.lower()
    target = derived_text_path(matter, p)
    side = text_file_for(matter, p)
    if ext in AUDIO_EXT:
        has = side is not None
        return Doc(path=rel, kind="audio", state="searchable" if has else "transcript-needed",
                   sidecar=str(_rel(matter, side or target)),
                   note="" if has else "run the local STT pipeline (docs/stt.md); never a cloud service")
    kind = "image" if ext in IMAGE_EXT | IMAGE_UNSUPPORTED_EXT else "docx"
    d = Doc(path=rel, kind=kind, state="", sidecar=str(_rel(matter, side or target)),
            source=rel, pages=1)
    if side is None:
        if ext in IMAGE_UNSUPPORTED_EXT:
            d.state, d.note = "unsupported", "convert to PNG/JPEG first"
        else:
            d.state = "needs-ocr" if kind == "image" else "needs-sidecar"
        return d
    hp = _header_pages(side)
    if hp is None:
        d.state = "unverified-sidecar"
        d.note = "human transcription" if kind == "image" else "text file not written by this tool"
        return d
    if side.stat().st_mtime < p.stat().st_mtime:
        d.state = "stale-sidecar"
        return d
    d.state = "searchable"
    if side != target:
        d.note = "legacy location; `sc text migrate` moves it under derived/"
    return d


def _cache_path(matter: Path) -> Path:
    return matter / ".state" / CACHE_NAME


#: Bump when classification or note text changes, so cached rows written
#: by an older version are re-surveyed instead of carrying stale wording.
CACHE_VERSION = "4"


def _stamp(matter: Path, doc: Path) -> str:
    bits = [f"v{CACHE_VERSION}", f"{doc.stat().st_size}:{doc.stat().st_mtime_ns}"]
    for extra in (derived_ocr_path(matter, doc), derived_text_path(matter, doc),
                  legacy_ocr_sibling(doc), legacy_text_sibling(doc), doc.with_suffix(".txt")):
        if extra.exists() and extra != doc:
            st = extra.stat()
            bits.append(f"{extra.name}:{st.st_size}:{st.st_mtime_ns}")
    return "|".join(bits)


def audit(matter: Path, include_inbox: bool = False, use_cache: bool = True) -> list[Doc]:
    matter = Path(os.path.abspath(matter))
    cache_file = _cache_path(matter)
    cache: dict = {}
    if use_cache and cache_file.is_file():
        try:
            cache = json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            cache = {}
    results: list[Doc] = []
    fresh: dict = {}
    for p in iter_documents(matter):
        rel = str(p.relative_to(matter))
        stamp = _stamp(matter, p)
        hit = cache.get(rel)
        if hit and hit.get("stamp") == stamp:
            d = Doc(**hit["doc"])
        else:
            d = classify_pdf(matter, p) if p.suffix.lower() in PDF_EXT else classify_other(matter, p)
        if not include_inbox and rel.split(os.sep)[0] == "inbox":
            d = Doc(**{**asdict(d), "state": "untriaged", "note": "under inbox/; triage first (or --include-inbox)"})
        fresh[rel] = {"stamp": stamp, "doc": asdict(d)}
        results.append(d)
    if use_cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(fresh, indent=0, sort_keys=True))
    return results


# ---------------------------------------------------------------------------
# repair
# ---------------------------------------------------------------------------

def _tool(name: str) -> str | None:
    return shutil.which(name)


def write_pdf_sidecar(matter: Path, original: Path, source: Path, sidecar: Path,
                      ocr_note: str = "none") -> Doc:
    """Dump every page of `source` into `sidecar`, page-marked, with a
    provenance header. Never overwrites a sidecar this tool did not write."""
    if sidecar.exists() and _header_pages(sidecar) is None:
        raise FileExistsError(f"{sidecar} was not written by this tool; leaving it")
    doc = fitz.open(str(source))
    try:
        total = doc.page_count
        lines = [HEADER_MARK,
                 f"original: {original.name}",
                 f"source: {source.name}",
                 f"pages: {total}",
                 "tool: pymupdf "
                 f"{getattr(fitz, 'VersionBind', getattr(fitz, '__version__', '?'))}; "
                 f"ocr: {ocr_note}",
                 f"generated: {dt.datetime.now().isoformat(timespec='seconds')}",
                 BANNER, ""]
        unc: list[int] = []
        from_ocr = source != original
        for i, page in enumerate(doc, 1):
            kind, _ = rc.classify(page, rc.DEFAULT_MIN_CHARS)
            if from_ocr and kind in ("image-bodied", "sparse"):
                kind = "text"
            lines.append(f"[[[ page {i} of {total} ]]]")
            body = page.get_text().strip()
            if kind in ("image-only", "blank"):
                lines.append(f"<< NO TEXT LAYER ({kind}) >>")
                if kind == "image-only":
                    unc.append(i)
            else:
                lines.append(body)
                if kind in FORCE_KINDS:
                    lines.append(f"<< {kind.upper()}: text above may not speak for this page >>")
                    unc.append(i)
            lines.append("")
        lines.append(f"[[[ end {source.name} --- {total} page(s) ]]]")
        if unc:
            lines.append(f"[[[ pages NOT covered by this text: {', '.join(map(str, unc))} ]]]")
    finally:
        doc.close()
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    tmp = sidecar.with_suffix(sidecar.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, sidecar)
    return classify_pdf(matter, original)


def ocr_pdf(original: Path, pages_to_force: list[int], redo: bool = False,
            target: Path | None = None) -> tuple[Path, str]:
    """Produce/refresh the OCR'd copy under derived/ocr/. Returns (copy, note)."""
    exe = _tool("ocrmypdf")
    if not exe:
        raise RuntimeError("ocrmypdf is not installed")
    sib = target or legacy_ocr_sibling(original)
    if sib.exists() and not redo:
        raise FileExistsError(f"{sib.name} exists; pass --redo-ocr to regenerate it")
    sib.parent.mkdir(parents=True, exist_ok=True)
    # The sibling is derived output; the signed original is untouched, so
    # invalidating the signature on the copy is correct, not destructive.
    cmd = [exe, "-l", "eng", "-q", "--invalidate-digital-signatures"]
    if pages_to_force:
        cmd += ["--force-ocr", "--pages", ",".join(map(str, pages_to_force))]
        note = f"ocrmypdf --force-ocr --pages {','.join(map(str, pages_to_force))}"
    else:
        cmd += ["--skip-text"]
        note = "ocrmypdf --skip-text"
    tmp = sib.with_suffix(".tmp.pdf")
    subprocess.run([*cmd, str(original), str(tmp)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    os.replace(tmp, sib)
    return sib, note


def repair(matter: Path, d: Doc, dry_run: bool = False, redo_ocr: bool = False) -> Doc:
    """Bring one document to `searchable` if a tool can; return its new state."""
    matter = Path(os.path.abspath(matter))
    p = matter / d.path
    if d.state in ("searchable", "unverified-sidecar", "untriaged", "unreadable",
                   "transcript-needed", "unsupported"):
        return d
    if dry_run:
        return Doc(**{**asdict(d), "note": f"would repair ({d.state})"})
    try:
        if d.kind == "pdf":
            ocr_note = "none"
            existing = ocr_copy_for(matter, p)
            target_ocr = derived_ocr_path(matter, p)
            if d.state == "needs-ocr":
                pages, unc, kinds = _survey(existing or p, ocr_output=existing is not None)
                force = [i for i in unc if kinds[i - 1] in FORCE_KINDS]
                copy, ocr_note = ocr_pdf(p, force if (force or existing) else [],
                                         redo=redo_ocr or existing is None, target=target_ocr)
                existing = copy
            source = existing or p
            return write_pdf_sidecar(matter, p, source, derived_text_path(matter, p), ocr_note)
        if d.kind == "image":
            exe = _tool("tesseract")
            if not exe:
                return Doc(**{**asdict(d), "note": "tesseract is not installed"})
            side = derived_text_path(matter, p)
            side.parent.mkdir(parents=True, exist_ok=True)
            out_base = side.with_suffix("")  # tesseract appends .txt
            subprocess.run([exe, str(p), str(out_base), "-l", "eng"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            text = side.read_text(encoding="utf-8", errors="replace")
            side.write_text("\n".join([HEADER_MARK, f"original: {p.name}", f"source: {p.name}",
                                       "pages: 1", "tool: tesseract; ocr: tesseract",
                                       f"generated: {dt.datetime.now().isoformat(timespec='seconds')}",
                                       BANNER, "", "[[[ page 1 of 1 ]]]", text]), encoding="utf-8")
            return classify_other(matter, p)
        if d.kind == "docx":
            exe = _tool("pandoc")
            if not exe:
                return Doc(**{**asdict(d), "note": "pandoc is not installed"})
            side = derived_text_path(matter, p)
            side.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run([exe, str(p), "-t", "plain", "--wrap=none"],
                                  check=True, capture_output=True, text=True)
            side.write_text("\n".join([HEADER_MARK, f"original: {p.name}", f"source: {p.name}",
                                       "pages: 1", "tool: pandoc; ocr: none",
                                       f"generated: {dt.datetime.now().isoformat(timespec='seconds')}",
                                       BANNER, "", "[[[ page 1 of 1 ]]]", proc.stdout]), encoding="utf-8")
            return classify_other(matter, p)
    except FileExistsError as exc:
        return Doc(**{**asdict(d), "note": str(exc)[:200]})
    except Exception as exc:  # a failed repair is a reported row, never an abort
        return Doc(**{**asdict(d), "state": "unreadable" if d.kind == "pdf" else d.state,
                      "note": f"repair failed: {type(exc).__name__}: {exc}"[:200]})
    return d


FAILURES_NAME = "text_ensure_failures.json"


def ensure(matter: Path, include_inbox: bool = False, dry_run: bool = False,
           redo_ocr: bool = False, jobs: int = 2) -> list[Doc]:
    docs = audit(matter, include_inbox=include_inbox)
    todo = [d for d in docs if d.state in ("needs-ocr", "needs-sidecar", "stale-sidecar")]
    if not todo:
        return docs
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        results = list(ex.map(lambda d: repair(matter, d, dry_run=dry_run, redo_ocr=redo_ocr), todo))
    if dry_run:
        return docs
    # Why a repair did not take is otherwise lost when the tree is
    # re-audited; keep it beside the cache and surface it on the row.
    failures = {r.path: r.note for r in results if r.note.startswith("repair failed")
                or "not installed" in r.note or "leaving it" in r.note}
    fpath = Path(os.path.abspath(matter)) / ".state" / FAILURES_NAME
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(json.dumps(failures, indent=1, sort_keys=True))
    final = audit(matter, include_inbox=include_inbox)
    for d in final:
        if not d.searched and d.path in failures:
            d.note = (d.note + " | " if d.note else "") + failures[d.path]
    return final


# ---------------------------------------------------------------------------
# migrate: move what this tool wrote beside originals into derived/
# ---------------------------------------------------------------------------

def _tracked(matter: Path, path: Path) -> bool:
    if not (matter / ".git").exists():
        return False
    proc = subprocess.run(["git", "ls-files", "--error-unmatch", str(_rel(matter, path))],
                          cwd=matter, capture_output=True, text=True)
    return proc.returncode == 0


def _move(matter: Path, src: Path, dst: Path, dry_run: bool) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    how = "git mv" if _tracked(matter, src) else "mv"
    if not dry_run:
        if how == "git mv":
            subprocess.run(["git", "mv", "-k", str(_rel(matter, src)), str(_rel(matter, dst))],
                           cwd=matter, check=True, capture_output=True)
            if src.exists():  # -k skipped it (e.g. dst tracked); fall back
                os.replace(src, dst)
        else:
            os.replace(src, dst)
    return f"{how} {_rel(matter, src)} -> {_rel(matter, dst)}"


def migrate(matter: Path, dry_run: bool = False, include_legacy_ocr: bool = False) -> list[str]:
    """Move tool-written text files (header present) and the OCR copies the
    tool made into derived/. Human text files stay where they are. Legacy
    `_ocr.pdf` siblings the tool did not make move only on request."""
    matter = Path(os.path.abspath(matter))
    moves: list[str] = []
    for doc in iter_documents(matter):
        legacy_txt = legacy_text_sibling(doc)
        target_txt = derived_text_path(matter, doc)
        tool_made_ocr = False
        if legacy_txt.exists() and _header_pages(legacy_txt) is not None:
            try:
                head = legacy_txt.read_text(encoding="utf-8", errors="replace")[:600]
                tool_made_ocr = "ocr: ocrmypdf" in head
            except OSError:
                pass
            if target_txt.exists():
                moves.append(f"skip {_rel(matter, legacy_txt)}: {_rel(matter, target_txt)} exists")
            else:
                moves.append(_move(matter, legacy_txt, target_txt, dry_run))
        if doc.suffix.lower() in PDF_EXT:
            sib = legacy_ocr_sibling(doc)
            if sib.exists() and (tool_made_ocr or include_legacy_ocr):
                target = derived_ocr_path(matter, doc)
                if target.exists():
                    moves.append(f"skip {_rel(matter, sib)}: {_rel(matter, target)} exists")
                else:
                    moves.append(_move(matter, sib, target, dry_run))
    if not dry_run:
        gi = matter / ".gitignore"
        line = "derived/ocr/"
        text = gi.read_text() if gi.exists() else ""
        if line not in text.splitlines():
            gi.write_text(text.rstrip("\n") + ("\n" if text else "")
                          + "\n# OCR'd copies: regenerable by `sc text ensure`, large\n"
                          + line + "\n")
            moves.append(f"append {line} to .gitignore")
        cache = _cache_path(matter)
        if cache.exists():
            cache.unlink()
    return moves


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def summarize(docs: list[Doc]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in docs:
        out[d.state] = out.get(d.state, 0) + 1
    return out


def coverage_line(docs: list[Doc]) -> str:
    triaged = [d for d in docs if d.state != "untriaged"]
    n = len(triaged)
    ok = sum(1 for d in triaged if d.searched)
    unv = sum(1 for d in triaged if d.state == "unverified-sidecar")
    gaps = n - ok
    s = f"text coverage: {ok}/{n} document(s) searchable"
    if unv:
        s += f" ({unv} with unverified sidecars)"
    if gaps:
        s += f"; {gaps} NOT searchable --- run `sc text ensure`"
    untri = len(docs) - n
    if untri:
        s += f"; {untri} untriaged in inbox/"
    return s


def format_audit(docs: list[Doc], show: int = 60) -> str:
    lines = [coverage_line(docs), ""]
    summ = summarize(docs)
    for state in ("needs-ocr", "needs-sidecar", "stale-sidecar", "unreadable", "transcript-needed",
                  "unsupported", "untriaged", "unverified-sidecar", "searchable"):
        if state in summ:
            lines.append(f"{state:<20} {summ[state]}")
    gaps = [d for d in docs if not d.searched]
    if gaps:
        lines.append("")
        lines.append("Not searchable:")
        for d in gaps[:show]:
            extra = f" pages {d.uncovered[:12]}" if d.uncovered else ""
            lines.append(f"  - [{d.state}] {d.path}{extra}" + (f" --- {d.note}" if d.note else ""))
        if len(gaps) > show:
            lines.append(f"  ... and {len(gaps) - show} more (use --json for all)")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("migrate", help="move tool-written text and OCR copies under derived/")
    sp.add_argument("matter", nargs="?", default=".")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--include-legacy-ocr", action="store_true",
                    help="also move _ocr.pdf siblings this tool did not make")
    for name in ("audit", "ensure"):
        sp = sub.add_parser(name)
        sp.add_argument("matter", nargs="?", default=".")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("--include-inbox", action="store_true")
        sp.add_argument("--no-cache", action="store_true")
        if name == "ensure":
            sp.add_argument("--dry-run", action="store_true")
            sp.add_argument("--redo-ocr", action="store_true",
                            help="regenerate an existing _ocr sibling that still has uncovered pages")
            sp.add_argument("--jobs", type=int, default=2)
    a = ap.parse_args()
    matter = Path(a.matter).resolve()
    if a.cmd == "migrate":
        for m in migrate(matter, dry_run=a.dry_run, include_legacy_ocr=a.include_legacy_ocr):
            print(m)
        return 0
    if a.cmd == "audit":
        docs = audit(matter, include_inbox=a.include_inbox, use_cache=not a.no_cache)
    else:
        docs = ensure(matter, include_inbox=a.include_inbox, dry_run=a.dry_run,
                      redo_ocr=a.redo_ocr, jobs=a.jobs)
    if a.json:
        print(json.dumps([asdict(d) for d in docs], indent=1))
    else:
        sys.stdout.write(format_audit(docs))
    return 0 if all(d.searched or d.state == "untriaged" for d in docs) else 1


if __name__ == "__main__":
    sys.exit(main())
