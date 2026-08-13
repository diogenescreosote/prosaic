#!/usr/bin/env python3
"""Build driver for court filing envelopes.

Reads envelopes.yaml from the current working directory and orchestrates
md_pleading.py (and optionally md_to_docx.py) builds for each source in
the requested envelope.  Output PDFs (and .docx files) land in
out/<envelope_name>/.

An "envelope" is a group of pleading source files that constitute a single
court filing — e.g., a complaint, supporting declaration, memorandum of
points and authorities, and proposed order.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

# Resolve paths to sibling scripts relative to this file's location.
PLEADING_GEN = Path(__file__).resolve().parent / "md_pleading.py"
FINAL_BUILD = False  # set from --final in main()
MD_TO_DOCX = Path(__file__).resolve().parent / "md_to_docx.py"
MD_TO_TXT = Path(__file__).resolve().parent / "md_to_txt.py"
REDACT_PDF = Path(__file__).resolve().parent / "redact_pdf.py"


@dataclass
class SourceEntry:
    """A single source file within an envelope.

    Parsed from envelopes.yaml — either a plain string (PDF only) or a
    mapping with ``file`` and optional ``docx: true`` / ``format: txt``.

    ``format`` selects the output renderer:
      * ``pdf`` (default) — California-style pleading/letter PDF via
        md_pleading.py, plus an optional editable ``.docx`` when ``docx: true``.
      * ``txt`` — plain text with no hard line breaks via md_to_txt.py. A txt
        source produces only a ``.txt`` (no PDF/DOCX) and is written to
        ``out/<envelope>/`` without a variant subdirectory.
    """

    file: str
    docx: bool = False
    fmt: str = "pdf"
    copy_attachments: bool = False

    @classmethod
    def from_yaml(cls, raw) -> "SourceEntry":
        if isinstance(raw, str):
            return cls(file=raw)
        fmt = str(raw.get("format", "pdf")).strip().lower()
        if fmt not in ("pdf", "txt"):
            raise ValueError(
                f"Unknown source format {fmt!r} (expected 'pdf' or 'txt')"
            )
        return cls(
            file=raw["file"],
            docx=raw.get("docx", False),
            fmt=fmt,
            copy_attachments=bool(raw.get("copy_attachments", False)),
        )

    @property
    def is_txt(self) -> bool:
        return self.fmt == "txt"


@dataclass
class RedactedPdfEntry:
    """A source that is produced by running redact_pdf.py on a JSON config.

    In envelopes.yaml, specify as:
        - type: redacted_pdf
          config: "redactions/motion_redactions.json"  # relative to src/
          dest: "smith_rfo_public_redacted.pdf"      # filename in output dir
    The JSON config's ``output_pdf`` field names the cached build artifact;
    the ``dest`` field (here) names the copy placed in the envelope output dir.
    """

    config: str       # path relative to src/
    dest: str         # output filename in the envelope's out/ directory

    @classmethod
    def from_yaml(cls, raw) -> "RedactedPdfEntry":
        return cls(config=raw["config"], dest=raw["dest"])

    @property
    def output_name(self) -> str:
        return self.dest


@dataclass
class CopyEntry:
    """A static file copied into an envelope output directory."""

    src: str
    dest: Optional[str] = None

    @classmethod
    def from_yaml(cls, raw) -> "CopyEntry":
        if isinstance(raw, str):
            return cls(src=raw)
        return cls(src=raw["src"], dest=raw.get("dest"))

    @property
    def output_name(self) -> str:
        return self.dest or Path(self.src).name


@dataclass
class EnvelopeEntry:
    """One envelope definition from envelopes.yaml."""

    sources: List[SourceEntry]
    copies: List[CopyEntry]
    redacted_pdfs: List["RedactedPdfEntry"]
    sent_on: Optional[str] = None

    @property
    def is_sent(self) -> bool:
        return bool(self.sent_on)

    @classmethod
    def from_yaml(cls, raw) -> "EnvelopeEntry":
        sent_on = raw.get("sent_on")
        if sent_on is not None:
            sent_on = str(sent_on)

        # Sources can be plain strings, {file:, docx:} dicts, or
        # {type: redacted_pdf, config:, dest:} dicts.  Split them here.
        plain_sources: List[SourceEntry] = []
        redacted: List[RedactedPdfEntry] = []
        for s in raw.get("sources", []):
            if isinstance(s, dict) and s.get("type") == "redacted_pdf":
                redacted.append(RedactedPdfEntry.from_yaml(s))
            else:
                plain_sources.append(SourceEntry.from_yaml(s))

        return cls(
            sources=plain_sources,
            copies=[CopyEntry.from_yaml(c) for c in raw.get("copies", [])],
            redacted_pdfs=redacted,
            sent_on=sent_on,
        )


def load_envelopes(yaml_path: Path) -> dict:
    """Load envelope definitions from envelopes.yaml."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("envelopes", {})


def _resolve_exhibit_source_dependency(input_path: Path, metadata: dict) -> List[Path]:
    exhibit_source = metadata.get("exhibit_source")
    if not exhibit_source:
        return []
    source_path = Path(exhibit_source)
    if not source_path.is_absolute():
        source_path = (input_path.parent / source_path).resolve()
    return [source_path]


def _source_build_info(input_path: Path, variant: Optional[str]) -> tuple[List[Path], List[str]]:
    """(dependency paths, companion output file names) for one source.

    Companion names are the extra files the render emits beside its own
    PDF — currently the SUBP-025 consumer notices a subpoena source
    declares. They are outputs, so a missing one makes the source stale.
    """
    # md_pleading is a sibling module; imported lazily so `--list` and
    # friends stay cheap (importing it registers fonts).
    pleading_dir = str(PLEADING_GEN.parent)
    if pleading_dir not in sys.path:
        sys.path.insert(0, pleading_dir)
    import md_pleading
    metadata = md_pleading.dependency_info(input_path, variant)
    deps = [Path(p) for p in metadata.get("deps", [])]
    deps.extend(_resolve_exhibit_source_dependency(input_path, metadata))
    return deps, list(metadata.get("consumer_notice_names") or [])


def _staleness_reason(outputs: List[Path], deps: List[Path]) -> Optional[str]:
    for output in outputs:
        if not output.exists():
            return f"missing output {output}"

    newest_dep = max(deps, key=lambda dep: os.path.getmtime(dep))
    newest_dep_mtime = os.path.getmtime(newest_dep)
    oldest_output = min(outputs, key=lambda out: os.path.getmtime(out))
    oldest_output_mtime = os.path.getmtime(oldest_output)

    if oldest_output_mtime < newest_dep_mtime:
        return f"{oldest_output} is older than dependency {newest_dep}"

    return None


def _copy_output_paths(
    envelope_name: str,
    copies: List[CopyEntry],
    variant: Optional[str],
) -> List[tuple[Path, Path]]:
    out_dir = Path("out") / envelope_name
    if variant:
        out_dir = out_dir / variant

    pairs: List[tuple[Path, Path]] = []
    for entry in copies:
        src_path = Path(entry.src)
        if not src_path.is_absolute():
            src_path = (Path.cwd() / src_path).resolve()
        pairs.append((src_path, out_dir / entry.output_name))
    return pairs


def _redacted_pdf_paths(entry: "RedactedPdfEntry", src_dir: Path,
                        out_dir: Path) -> tuple[Path, Path, Path, Path]:
    """Resolve a redacted_pdf entry's paths from its JSON config.

    Returns (config_path, source_pdf, cached_output, dest_path). Shared
    by the build and --check-stale paths so their notion of the entry's
    inputs/outputs cannot drift.
    """
    import json as _json

    config_path = (src_dir / entry.config).resolve()
    with open(config_path, encoding="utf-8") as f:
        cfg = _json.load(f)
    base = config_path.parent
    source_pdf = (base / cfg["source_pdf"]).resolve()
    cached_output = (base / cfg["output_pdf"]).resolve()
    return config_path, source_pdf, cached_output, out_dir / entry.dest


def check_staleness(
    name: str,
    sources: List[SourceEntry],
    copies: Optional[List[CopyEntry]] = None,
    redacted_pdfs: Optional[List["RedactedPdfEntry"]] = None,
    variant: Optional[str] = None,
) -> bool:
    """Return True if all outputs are present and newer than dependencies."""
    src_dir = Path("src")
    out_dir = Path("out") / name
    if variant:
        out_dir = out_dir / variant

    ok = True
    for entry in sources:
        input_path = (src_dir / entry.file).resolve()
        stem = Path(entry.file).stem

        if entry.is_txt:
            # Plain-text targets ignore the variant subdirectory and depend
            # only on the markdown source (exhibits are referenced, not
            # attached, so no binary dependencies).
            txt_output = Path("out") / name / f"{stem}.txt"
            reason = _staleness_reason([txt_output], [input_path])
            if reason:
                print(f"  STALE: {reason}", file=sys.stderr, flush=True)
                ok = False
            continue

        try:
            deps, companions = _source_build_info(input_path, variant)
        except Exception as err:
            print(f"  ERROR: could not inspect dependencies for {entry.file}: {err}",
                  file=sys.stderr, flush=True)
            ok = False
            continue

        outputs = [out_dir / f"{stem}.pdf"]
        if entry.docx:
            outputs.append(out_dir / f"{stem}.docx")
        outputs.extend(out_dir / name for name in companions)

        reason = _staleness_reason(outputs, deps)
        if reason:
            print(f"  STALE: {reason}", file=sys.stderr, flush=True)
            ok = False

    for src_path, output_path in _copy_output_paths(name, copies or [], variant):
        reason = _staleness_reason([output_path], [src_path])
        if reason:
            print(f"  STALE: {reason}", file=sys.stderr, flush=True)
            ok = False

    for entry in redacted_pdfs or []:
        try:
            config_path, source_pdf, cached_output, dest_path = \
                _redacted_pdf_paths(entry, src_dir, out_dir)
            reason = (_staleness_reason([cached_output], [config_path, source_pdf])
                      or _staleness_reason([dest_path], [cached_output]))
        except Exception as err:
            print(f"  ERROR: could not inspect redacted_pdf {entry.config}: {err}",
                  file=sys.stderr, flush=True)
            ok = False
            continue
        if reason:
            print(f"  STALE: {reason}", file=sys.stderr, flush=True)
            ok = False

    return ok


def _build_redacted_pdfs(
    name: str,
    entries: List["RedactedPdfEntry"],
    variant: Optional[str],
    force_rebuild: bool,
) -> bool:
    """Build any redacted-PDF sources that are stale and copy to output dir."""
    src_dir = Path("src")
    out_dir = Path("out") / name
    if variant:
        out_dir = out_dir / variant
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    for entry in entries:
        config_path = (src_dir / entry.config).resolve()
        if not config_path.exists():
            print(f"  ERROR: redacted_pdf config not found: {config_path}",
                  file=sys.stderr, flush=True)
            ok = False
            continue

        config_path, source_pdf, cached_output, dest_path = \
            _redacted_pdf_paths(entry, src_dir, out_dir)

        # Check staleness against the cached artifact.
        missing_cache = not cached_output.exists()
        cache_stale = (not missing_cache and (
            _staleness_reason([cached_output], [config_path, source_pdf]) is not None
        ))

        if force_rebuild or missing_cache or cache_stale:
            reason = "forced" if force_rebuild else ("missing" if missing_cache else "stale")
            print(f"  rebuilding {entry.dest} ({reason})", flush=True)
            cmd = [sys.executable, str(REDACT_PDF), str(config_path)]
            if force_rebuild:
                cmd.append("--force")
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print(f"  ERROR: redact_pdf failed for {entry.config}",
                      file=sys.stderr, flush=True)
                ok = False
                continue
        else:
            print(f"  {entry.dest}: cached artifact up to date", flush=True)

        # Copy the cached artifact into the envelope output directory.
        if not cached_output.exists():
            print(f"  ERROR: cached output missing after build: {cached_output}",
                  file=sys.stderr, flush=True)
            ok = False
            continue

        dest_stale = _staleness_reason([dest_path], [cached_output])
        if dest_stale or force_rebuild:
            shutil.copy2(cached_output, dest_path)
            print(f"  Wrote {dest_path}", flush=True)
        else:
            print(f"  {entry.dest} in output dir is up to date", flush=True)

    return ok


def _build_txt_source(
    name: str,
    input_path: Path,
    stem: str,
    variant: Optional[str],
    force_rebuild: bool,
    copy_attachments: bool = False,
) -> bool:
    """Render one plain-text source to out/<name>/<stem>.txt.

    Text targets ignore the variant subdirectory (a single plain-text file
    serves any audience) and depend only on the markdown source. When
    ``copy_attachments`` is set, the exhibit source files are also copied into
    the same output directory under their numbered names; in that case the
    render always runs so the attachments stay in sync.
    """
    out_dir = Path("out") / name
    out_dir.mkdir(parents=True, exist_ok=True)
    output_txt = out_dir / f"{stem}.txt"

    if not force_rebuild and not copy_attachments:
        reason = _staleness_reason([output_txt], [input_path.resolve()])
        if reason is None:
            print(f"  {input_path.name} is up to date", flush=True)
            return True
        print(f"  rebuilding {input_path.name}: {reason}", flush=True)
    else:
        print(f"  building {input_path.name}", flush=True)

    cmd = [sys.executable, str(MD_TO_TXT), str(input_path), str(output_txt)]
    if FINAL_BUILD:
        cmd.append("--final")
    if variant:
        cmd += ["--variant", variant]
    if copy_attachments:
        cmd += ["--attachments-dir", str(out_dir)]

    print(f"  {input_path.name} -> {output_txt}", flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"  ERROR: {input_path.name} (txt) failed (exit {result.returncode})",
              file=sys.stderr, flush=True)
        return False
    return True


@dataclass
class RenderJob:
    """One renderer invocation, planned but not yet run.

    Planning is separated from running so the renders can overlap.
    Deciding *what* to build is cheap and order-dependent (staleness
    checks, readable log lines); actually building is expensive and
    embarrassingly parallel — each job reads shared inputs read-only
    and writes one output nobody else touches.
    """

    label: str      #: progress line, e.g. "Declaration.md -> out/x.pdf"
    cmd: List[str]
    error: str      #: what to say if it fails


def _render_worker_count(job_count: int, requested: Optional[int]) -> int:
    if requested is not None:
        return max(1, requested)
    env = os.environ.get("PROSAIC_BUILD_JOBS")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            print(f"  WARNING: ignoring non-numeric PROSAIC_BUILD_JOBS={env!r}",
                  file=sys.stderr, flush=True)
    return max(1, min(job_count, os.cpu_count() or 4))


def _run_render_jobs(jobs: List[RenderJob], workers: Optional[int] = None) -> bool:
    """Run planned renders concurrently. Returns True if all succeeded.

    Threads, not processes: each job is already its own OS process, so
    the parent is only waiting on them and the GIL is irrelevant.

    Child output is captured and printed as one block per job when that
    job finishes. Letting ten renderers write to the same terminal
    would interleave them into noise — this is both parallel *and* more
    readable than the sequential version was.
    """
    if not jobs:
        return True

    n = _render_worker_count(len(jobs), workers)
    if n > 1 and len(jobs) > 1:
        print(f"  building {len(jobs)} document(s) on {n} workers", flush=True)

    def run(job: RenderJob) -> Tuple[RenderJob, subprocess.CompletedProcess]:
        return job, subprocess.run(job.cmd, capture_output=True, text=True)

    ok = True
    with ThreadPoolExecutor(max_workers=n) as pool:
        for job, result in pool.map(run, jobs):
            print(f"  {job.label}", flush=True)
            for stream, sink in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
                for line in (stream or "").splitlines():
                    print(f"    {line}", file=sink, flush=True)
            if result.returncode != 0:
                print(f"  ERROR: {job.error} (exit {result.returncode})",
                      file=sys.stderr, flush=True)
                ok = False
    return ok


def build_envelope(
    name: str,
    sources: List[SourceEntry],
    copies: Optional[List[CopyEntry]] = None,
    redacted_pdfs: Optional[List["RedactedPdfEntry"]] = None,
    variant: Optional[str] = None,
    sign: Optional[str] = None,
    date: Optional[str] = None,
    force_rebuild: bool = False,
    jobs: Optional[int] = None,
) -> bool:
    """Build stale or missing sources for one envelope. Returns True if all succeed."""
    src_dir = Path("src")
    out_dir = Path("out") / name
    if variant:
        out_dir = out_dir / variant
    out_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    render_jobs: List[RenderJob] = []
    for entry in sources:
        input_path = src_dir / entry.file
        stem = Path(entry.file).stem

        if entry.is_txt:
            if not _build_txt_source(name, input_path, stem, variant,
                                     force_rebuild, entry.copy_attachments):
                ok = False
            continue

        output_pdf = out_dir / f"{stem}.pdf"
        outputs = [output_pdf]
        if entry.docx:
            outputs.append(out_dir / f"{stem}.docx")

        if not force_rebuild:
            try:
                deps, companions = _source_build_info(input_path.resolve(), variant)
                reason = _staleness_reason(
                    outputs + [out_dir / name for name in companions], deps)
            except Exception as err:
                print(
                    f"  WARNING: could not inspect dependencies for {entry.file}; "
                    f"rebuilding anyway ({err})",
                    file=sys.stderr,
                    flush=True,
                )
                reason = "dependency inspection failed"
            if reason is None:
                print(f"  {entry.file} is up to date", flush=True)
                continue
            print(f"  rebuilding {entry.file}: {reason}", flush=True)
        else:
            print(f"  force rebuilding {entry.file}", flush=True)

        cmd = [sys.executable, str(PLEADING_GEN), str(input_path), str(output_pdf)]
        if FINAL_BUILD:
            cmd.append("--final")
        if variant:
            cmd += ["--variant", variant]
        if sign:
            cmd += ["--sign", sign]
        if date:
            cmd += ["--date", date]

        render_jobs.append(RenderJob(
            label=f"{entry.file} -> {output_pdf}",
            cmd=cmd,
            error=f"{entry.file} failed",
        ))

        # The .docx renderer reads the markdown, not the PDF, so it is
        # independent of the job above and can run alongside it.
        if entry.docx:
            output_docx = out_dir / f"{stem}.docx"
            docx_cmd = [sys.executable, str(MD_TO_DOCX),
                        str(input_path), str(output_docx)]
            if FINAL_BUILD:
                docx_cmd.append("--final")
            if variant:
                docx_cmd += ["--variant", variant]
            render_jobs.append(RenderJob(
                label=f"{entry.file} -> {output_docx}",
                cmd=docx_cmd,
                error=f"{entry.file} .docx failed",
            ))

    if not _run_render_jobs(render_jobs, jobs):
        ok = False

    for src_path, output_path in _copy_output_paths(name, copies or [], variant):
        reason = None if force_rebuild else _staleness_reason([output_path], [src_path])
        if reason is None and not force_rebuild:
            print(f"  {output_path.name} is up to date", flush=True)
            continue
        if force_rebuild:
            print(f"  force copying {src_path} -> {output_path}", flush=True)
        else:
            print(f"  copying {src_path} -> {output_path}: {reason}", flush=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, output_path)

    if redacted_pdfs:
        if not _build_redacted_pdfs(name, redacted_pdfs, variant, force_rebuild):
            ok = False

    return ok


def list_envelopes(envelopes: dict) -> None:
    """Print available envelopes and their sources."""
    for name, raw_cfg in envelopes.items():
        cfg = EnvelopeEntry.from_yaml(raw_cfg)
        status = f"sent {cfg.sent_on}" if cfg.is_sent else "draft"
        print(f"{name}: [{status}]")
        for entry in cfg.sources:
            if entry.is_txt:
                tag = " [txt]"
            else:
                tag = " [+docx]" if entry.docx else ""
            print(f"  {entry.file}{tag}")
        for entry in cfg.copies:
            print(f"  copy {entry.src} -> {entry.output_name}")
        for entry in cfg.redacted_pdfs:
            print(f"  redacted_pdf {entry.config} -> {entry.output_name}")


def expected_outputs(envelopes: dict) -> List[str]:
    """Every path this config can legitimately produce, one per line.

    Deliberately over-inclusive. The consumer is `sc clean`, which
    deletes whatever is *not* here — so a false negative destroys work
    and a false positive merely leaves a stale file behind. Every
    variant directory is listed whether or not it was ever built, and a
    source whose front matter cannot be inspected yields a line that
    covers its whole envelope rather than nothing.

    Lines are either concrete paths or `<dir>/*` wildcards; a wildcard
    means "everything in here is unclassifiable, leave it alone."
    """
    src_dir = Path("src")
    out: List[str] = []
    for name, raw_cfg in envelopes.items():
        cfg = EnvelopeEntry.from_yaml(raw_cfg)
        dirs = [Path("out") / name,
                Path("out") / name / "public",
                Path("out") / name / "sealed"]
        for entry in cfg.sources:
            stem = Path(entry.file).stem
            for d in dirs:
                for ext in (".pdf", ".docx", ".txt"):
                    out.append(str(d / f"{stem}{ext}"))
                # Redaction sidecars ride next to their document. Both
                # renderers write one, named after the file they
                # describe — .pdf.redactions.json and
                # .docx.redactions.json are different files.
                out.append(str(d / f"{stem}.pdf.redactions.json"))
                out.append(str(d / f"{stem}.docx.redactions.json"))
                # RFC 3161 timestamp tokens (timestamp.py). These
                # certify that a specific PDF existed at a past moment:
                # evidentiary, and impossible to regenerate once that
                # moment has passed. Never collectable.
                out.append(str(d / f"{stem}.tsr"))
            # Companions (consumer notices, MC-025 overflow) are named
            # by the renderer from front matter. Inspecting can fail on
            # a source mid-edit; when it does, protect the envelope
            # rather than guess.
            try:
                input_path = (src_dir / entry.file).resolve()
                for variant in (None, "public", "sealed"):
                    _deps, companions = _source_build_info(input_path, variant)
                    base = Path("out") / name
                    for d in ({base} | {base / v for v in ("public", "sealed")}):
                        for companion in companions:
                            out.append(str(d / companion))
            except Exception:
                out.append(str(Path("out") / name / "*"))
        for _src, dest in _copy_output_paths(name, cfg.copies or [], None):
            out.append(str(dest))
        for variant in ("public", "sealed"):
            for _src, dest in _copy_output_paths(name, cfg.copies or [], variant):
                out.append(str(dest))
    return sorted(set(out))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build court filing envelopes from envelopes.yaml")
    parser.add_argument("envelope", nargs="?", help="Envelope name to build")
    parser.add_argument("--all", action="store_true",
                        help="Build all envelopes")
    parser.add_argument("--list", action="store_true",
                        help="List available envelopes")
    parser.add_argument("--list-outputs", action="store_true",
                        help="print every output path the config can produce, "
                             "one per line (used by `sc clean`)")
    parser.add_argument("--check-stale", action="store_true",
                        help="Fail if outputs are missing or older than sources/exhibits")
    parser.add_argument("--final", action="store_true",
                        help="Suppress the default DRAFT banner on every "
                             "rendered artifact: this build goes into the world")
    parser.add_argument("--force", action="store_true",
                        help="Allow rebuilding envelopes marked sent")
    parser.add_argument("--jobs", "-j", type=int, default=None, metavar="N",
                        help="Concurrent renderers (default: one per core; "
                             "also PROSAIC_BUILD_JOBS). -j1 serializes, "
                             "which is what you want when bisecting a failure.")
    parser.add_argument("--variant", choices=["sealed", "public"], default=None,
                        help="Render variant to build; outputs go under out/<envelope>/<variant>/")
    parser.add_argument("--sign", metavar="NAME", default=None,
                        help="Sign with NAME (cursive)")
    parser.add_argument("--date", metavar="YYYY-MM-DD", default=None,
                        help="Date for signature blocks")
    args = parser.parse_args()
    global FINAL_BUILD
    FINAL_BUILD = bool(getattr(args, "final", False))

    yaml_path = Path("envelopes.yaml")
    if not yaml_path.exists():
        print(f"Error: {yaml_path} not found in {Path.cwd()}", file=sys.stderr)
        sys.exit(1)

    envelopes = load_envelopes(yaml_path)

    if args.list:
        list_envelopes(envelopes)
        return

    if args.list_outputs:
        for line in expected_outputs(envelopes):
            print(line)
        return

    if not args.envelope and not args.all:
        parser.print_usage()
        sys.exit(1)

    if args.variant is None:
        print(
            "WARNING: no --variant specified. Outputs will be written to "
            "out/<envelope>/ rather than out/<envelope>/public or "
            "out/<envelope>/sealed, and any redaction-bearing source will "
            "render its PUBLIC (redacted) variant. Pass --variant sealed "
            "explicitly for sealed content; prefer VARIANT=public or "
            "VARIANT=sealed for filing-ready packets.",
            file=sys.stderr,
            flush=True,
        )

    if args.all:
        if args.force:
            targets = list(envelopes.keys())
        else:
            targets = [
                name for name, raw_cfg in envelopes.items()
                if not EnvelopeEntry.from_yaml(raw_cfg).is_sent
            ]
            skipped = [
                f"{name} ({EnvelopeEntry.from_yaml(raw_cfg).sent_on})"
                for name, raw_cfg in envelopes.items()
                if EnvelopeEntry.from_yaml(raw_cfg).is_sent
            ]
            if skipped:
                print("Skipping sent envelopes:", flush=True)
                for item in skipped:
                    print(f"  {item}", flush=True)
            if not targets:
                print("No draft envelopes to build.", flush=True)
                return
    else:
        if args.envelope not in envelopes:
            print(f"Error: unknown envelope '{args.envelope}'",
                  file=sys.stderr)
            print(f"Available: {', '.join(envelopes.keys())}",
                  file=sys.stderr)
            sys.exit(1)
        cfg = EnvelopeEntry.from_yaml(envelopes[args.envelope])
        if cfg.is_sent and not args.force:
            print(
                f"Error: envelope '{args.envelope}' was marked sent on "
                f"{cfg.sent_on}. Re-run with --force to rebuild it.",
                file=sys.stderr,
            )
            sys.exit(1)
        targets = [args.envelope]

    all_ok = True
    for name in targets:
        cfg = EnvelopeEntry.from_yaml(envelopes[name])
        if args.check_stale:
            print(f"Checking staleness: {name}", flush=True)
            if not check_staleness(
                name,
                cfg.sources,
                copies=cfg.copies,
                redacted_pdfs=cfg.redacted_pdfs,
                variant=args.variant,
            ):
                all_ok = False
        else:
            print(f"Building envelope: {name}", flush=True)
            if not build_envelope(
                name,
                cfg.sources,
                copies=cfg.copies,
                redacted_pdfs=cfg.redacted_pdfs,
                variant=args.variant,
                sign=args.sign,
                date=args.date,
                force_rebuild=args.force,
                jobs=args.jobs,
            ):
                all_ok = False

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
