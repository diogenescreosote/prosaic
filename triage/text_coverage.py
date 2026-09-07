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
useless text: image-bodied, garbled), then writes a `.txt` sidecar from
the best available source with `[[[ page k of N ]]]` markers so a hit
carries a page cite. Images get `<stem>.ocr.txt` through tesseract;
DOCX gets `<stem>.txt` through pandoc.

Guarantees:
  * Originals are never modified. Everything written is a sibling.
  * A sidecar not written by this tool (no header) is never overwritten.
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

EXCLUDE_DIRS = frozenset({"out", ".state", ".git", ".flow", "node_modules", ".claude", ".venv"})
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


def ocr_sibling(pdf: Path) -> Path:
    return pdf.with_name(pdf.stem + "_ocr.pdf")


def sidecar_for(doc: Path) -> Path:
    if doc.suffix.lower() in IMAGE_EXT | IMAGE_UNSUPPORTED_EXT:
        return doc.with_name(doc.stem + ".ocr.txt")
    return doc.with_suffix(".txt")


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
    rel = str(pdf.relative_to(matter))
    sib = ocr_sibling(pdf)
    best = sib if sib.exists() else pdf
    side = sidecar_for(pdf)
    d = Doc(path=rel, kind="pdf", state="", sidecar=str(side.relative_to(matter)),
            source=str(best.relative_to(matter)))
    try:
        pages, unc, _ = _survey(best, ocr_output=best is sib)
    except Exception as exc:  # encrypted, corrupt
        d.state = "unreadable"
        d.note = f"{type(exc).__name__}: {exc}"[:160]
        return d
    d.pages, d.uncovered = pages, unc
    if unc:
        d.state = "needs-ocr"
        if best is sib:
            d.note = (f"OCR ran and found no text on {len(unc)} of {pages} page(s): "
                      "likely a photo, graphic or blank scan; describe it in a "
                      "human .txt sidecar if its content matters")
        else:
            d.note = f"{len(unc)} of {pages} page(s) lack a usable text layer"
        return d
    if not side.exists():
        d.state = "needs-sidecar"
        return d
    hp = _header_pages(side)
    if hp is None:
        d.state = "unverified-sidecar"
        d.note = "sidecar not written by this tool; completeness unknown"
        return d
    newest = max(pdf.stat().st_mtime, sib.stat().st_mtime if sib.exists() else 0)
    if side.stat().st_mtime < newest or hp != pages:
        d.state = "stale-sidecar"
        d.note = ("document newer than sidecar" if hp == pages
                  else f"sidecar says {hp} pages, document has {pages}")
        return d
    d.state = "searchable"
    return d


def classify_other(matter: Path, p: Path) -> Doc:
    rel = str(p.relative_to(matter))
    ext = p.suffix.lower()
    side = sidecar_for(p)
    if ext in AUDIO_EXT:
        has = p.with_suffix(".txt").exists()
        return Doc(path=rel, kind="audio", state="searchable" if has else "transcript-needed",
                   sidecar=str(p.with_suffix(".txt").relative_to(matter)),
                   note="" if has else "run the local STT pipeline (docs/stt.md); never a cloud service")
    if ext in IMAGE_UNSUPPORTED_EXT:
        has = side.exists() or p.with_suffix(".txt").exists()
        return Doc(path=rel, kind="image", state="unverified-sidecar" if has else "unsupported",
                   sidecar=str(side.relative_to(matter)), note="" if has else "convert to PNG/JPEG first")
    if ext in IMAGE_EXT:
        human = p.with_suffix(".txt")
        if human.exists():
            return Doc(path=rel, kind="image", state="unverified-sidecar",
                       sidecar=str(human.relative_to(matter)), note="human transcription sidecar")
        d = Doc(path=rel, kind="image", state="", sidecar=str(side.relative_to(matter)), source=rel, pages=1)
        if not side.exists():
            d.state = "needs-ocr"
        elif _header_pages(side) is None:
            d.state = "unverified-sidecar"
        elif side.stat().st_mtime < p.stat().st_mtime:
            d.state = "stale-sidecar"
        else:
            d.state = "searchable"
        return d
    # docx
    d = Doc(path=rel, kind="docx", state="", sidecar=str(side.relative_to(matter)), source=rel, pages=1)
    if not side.exists():
        d.state = "needs-sidecar"
    elif _header_pages(side) is None:
        d.state = "unverified-sidecar"
    elif side.stat().st_mtime < p.stat().st_mtime:
        d.state = "stale-sidecar"
    else:
        d.state = "searchable"
    return d


def _cache_path(matter: Path) -> Path:
    return matter / ".state" / CACHE_NAME


#: Bump when classification or note text changes, so cached rows written
#: by an older version are re-surveyed instead of carrying stale wording.
CACHE_VERSION = "2"


def _stamp(matter: Path, doc: Path) -> str:
    bits = [f"v{CACHE_VERSION}", f"{doc.stat().st_size}:{doc.stat().st_mtime_ns}"]
    for extra in (ocr_sibling(doc), sidecar_for(doc), doc.with_suffix(".txt")):
        if extra.exists() and extra != doc:
            st = extra.stat()
            bits.append(f"{extra.name}:{st.st_size}:{st.st_mtime_ns}")
    return "|".join(bits)


def audit(matter: Path, include_inbox: bool = False, use_cache: bool = True) -> list[Doc]:
    matter = matter.resolve()
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
    tmp = sidecar.with_suffix(sidecar.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, sidecar)
    return classify_pdf(matter, original)


def ocr_pdf(original: Path, pages_to_force: list[int], redo: bool = False) -> tuple[Path, str]:
    """Produce/refresh the `_ocr.pdf` sibling. Returns (sibling, note)."""
    exe = _tool("ocrmypdf")
    if not exe:
        raise RuntimeError("ocrmypdf is not installed")
    sib = ocr_sibling(original)
    if sib.exists() and not redo:
        raise FileExistsError(f"{sib.name} exists; pass --redo-ocr to regenerate it")
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
    matter = matter.resolve()
    p = matter / d.path
    if d.state in ("searchable", "unverified-sidecar", "untriaged", "unreadable",
                   "transcript-needed", "unsupported"):
        return d
    if dry_run:
        return Doc(**{**asdict(d), "note": f"would repair ({d.state})"})
    try:
        if d.kind == "pdf":
            ocr_note = "none"
            sib = ocr_sibling(p)
            if d.state == "needs-ocr":
                pages, unc, kinds = _survey(sib if sib.exists() else p, ocr_output=sib.exists())
                force = [i for i in unc if kinds[i - 1] in FORCE_KINDS]
                sib, ocr_note = ocr_pdf(p, force if (force or sib.exists()) else [],
                                        redo=redo_ocr or not sib.exists())
            source = sib if sib.exists() else p
            return write_pdf_sidecar(matter, p, source, sidecar_for(p), ocr_note)
        if d.kind == "image":
            exe = _tool("tesseract")
            if not exe:
                return Doc(**{**asdict(d), "note": "tesseract is not installed"})
            side = sidecar_for(p)
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
            side = sidecar_for(p)
            if side.exists() and _header_pages(side) is None:
                return Doc(**{**asdict(d), "state": "unverified-sidecar"})
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
    fpath = matter.resolve() / ".state" / FAILURES_NAME
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(json.dumps(failures, indent=1, sort_keys=True))
    final = audit(matter, include_inbox=include_inbox)
    for d in final:
        if not d.searched and d.path in failures:
            d.note = (d.note + " | " if d.note else "") + failures[d.path]
    return final


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
