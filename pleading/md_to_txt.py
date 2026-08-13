#!/usr/bin/env python3
"""Render a markdown pleading/letter source to plain text with no hard line breaks.

Each content block (heading, paragraph, list item) is emitted as a single
unwrapped line. There is no intra-paragraph wrapping, so the result can be
pasted directly into an online complaint form (e.g. a state licensing
board's complaint portal) that performs its own line wrapping
inside text fields.

Spacing: blocks are separated by a blank line, except that consecutive list
items (markdown ``-`` bullets and numbered items) pack tight against each other
with a single newline. Bullets render as plain lines with no marker, so a
tight, unmarked list is authored as consecutive ``-`` lines with any desired
enumerator (e.g. "(a)") written into the text.

Exhibits are auto-numbered from the YAML ``exhibits:`` list, in list order:

  * ``\\exhibit{shortname}``  -> "Exhibit N" (optionally with a page cite)
  * ``\\exhibitindex``        -> a numbered attachment index built from the list

Section headings (``#`` / ``##`` / ``###``) are auto-numbered ``I.`` / ``A.`` /
``1.`` exactly like md_pleading.py.

Usage:
    python md_to_txt.py input.md output.txt [--variant sealed|public]
"""

from __future__ import annotations

import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Reuse the shared front-matter, macro, and markdown-parsing machinery so the
# plain-text output stays in lockstep with the PDF/DOCX renderers.
import md_pleading as mp


def build_exhibit_map(meta: Dict, label: str) -> Dict[str, str]:
    """Map each exhibit shortname to its auto-numbered citation string."""
    exhibits = meta.get("exhibits") or []
    if not isinstance(exhibits, list):
        raise ValueError("exhibits must be a YAML list if provided")
    mapping: Dict[str, str] = {}
    seen: set = set()
    for idx, ex in enumerate(exhibits, start=1):
        if not isinstance(ex, dict):
            raise ValueError(f"exhibits[{idx}] must be a mapping/object")
        shortname = str(ex.get("shortname", "")).strip()
        if not shortname:
            raise ValueError(f"exhibits[{idx}] is missing a shortname")
        if shortname in seen:
            raise ValueError(f"Duplicate exhibit shortname: {shortname}")
        seen.add(shortname)
        cite = f"{label} {idx}"
        pages = ex.get("pages")
        if isinstance(pages, str) and pages.strip():
            # Shared page-cite formatter (en-dash ranges, p./pp.) so the
            # TXT citation style can never drift from the PDF/DOCX.
            cite += f", {mp._format_page_citation(pages.strip())}"
        mapping[shortname] = cite
    return mapping


def attachment_filename(idx: int, ex: Dict) -> str:
    """Derive the on-disk name for a copied exhibit, keyed to its number.

    e.g. exhibit 5 with shortname ``termination_email`` and a .pdf source ->
    ``Exhibit_05_termination_email.pdf``. Keeping the number in the filename
    means the copied attachments always match the auto-numbered citations.
    """
    src = str(ex.get("path", "")).strip()
    suffix = Path(src).suffix if src else ".pdf"
    shortname = str(ex.get("shortname", f"exhibit_{idx}")).strip()
    return f"Exhibit_{idx:02d}_{shortname}{suffix or '.pdf'}"


def substitute_exhibit_index(body: str, meta: Dict, label: str) -> str:
    r"""Expand ``\exhibitindex`` into a numbered attachment index.

    Each entry becomes its own paragraph (separated by a blank line) so that
    the downstream block parser renders one line per exhibit. When an exhibit
    has a ``path``, the index notes the filename used for the copied
    attachment so the reader can match the index to the attached file.
    """
    if "\\exhibitindex" not in body:
        return body
    exhibits = meta.get("exhibits") or []
    entries: List[str] = []
    for idx, ex in enumerate(exhibits, start=1):
        title = mp.typographic_subs(str(ex.get("title", "")).strip())
        entry = f"{label} {idx}: {title}"
        if str(ex.get("path", "")).strip():
            entry += f" (file: {attachment_filename(idx, ex)})"
        entries.append(entry)
    return body.replace("\\exhibitindex", "\n\n".join(entries))


def copy_attachments(meta: Dict, base_dir: Path, dest_dir: Path) -> Tuple[List[str], List[str]]:
    """Copy each exhibit's source file into ``dest_dir`` under its numbered name.

    Paths are resolved relative to ``base_dir`` (the case directory). Returns
    (copied_names, missing_descriptions).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    missing: List[str] = []
    for idx, ex in enumerate(meta.get("exhibits") or [], start=1):
        src = str(ex.get("path", "")).strip()
        if not src:
            continue
        src_path = Path(src)
        if not src_path.is_absolute():
            src_path = base_dir / src_path
        src_path = src_path.resolve()
        name = attachment_filename(idx, ex)
        if not src_path.exists():
            missing.append(f"{name} <- {src}")
            continue
        shutil.copy2(src_path, dest_dir / name)
        copied.append(name)
    return copied, missing


_EXHIBIT_REF_RE = re.compile(r"\\(?:exhibit|attachment)\{([A-Za-z0-9_\-]+)\}")


def substitute_exhibit_refs(body: str, exhibit_map: Dict[str, str]) -> str:
    r"""Replace ``\exhibit{shortname}`` / ``\attachment{shortname}`` cites."""
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in exhibit_map:
            raise ValueError(f"Unknown exhibit shortname referenced in body: {key}")
        return exhibit_map[key]
    return _EXHIBIT_REF_RE.sub(repl, body)


def block_to_line(block: mp.Block,
                  footnote_numbers: Dict[str, int] | None = None) -> str:
    """Collapse a parsed block into a single plain-text line.

    Bullet items render as plain lines with no marker (the author supplies any
    desired enumerator, e.g. "(a)", inside the text). Numbered items render with
    their literal "N." marker. Footnote references render as inline ``[n]``
    markers (matching the notes section render_text appends); an undefined id
    renders as its literal ``[^id]`` marker so the error is visible, matching
    the PDF/DOCX renderers.
    """
    if block.spans:
        parts: List[str] = []
        for span in block.spans:
            if span.footnote_id is not None:
                num = (footnote_numbers or {}).get(span.footnote_id)
                parts.append(f"[{num}]" if num is not None
                             else f"[^{span.footnote_id}]")
            else:
                parts.append(span.text)
        text = "".join(parts)
    else:
        text = block.text
    text = text.strip()
    if block.kind == "numbered":
        return f"{block.level}. {text}"
    return text


def _signature_block_text(block: mp.Block, meta: Dict) -> str:
    """Render a \\signblock or \\declsignblock as plain text.

    Mirrors the PDF layout (date line, signature rule, name, role) minus the
    grid: block.text is the name; for declsignblock spans[0]=location and
    spans[1]=optional role override; for signblock spans[0]=optional role
    override (falling back to filer_role).
    """
    year = datetime.date.today().year
    name = block.text.strip()
    if block.kind == "declsignblock":
        location = block.spans[0].text.strip() if block.spans else ""
        role = (block.spans[1].text.strip().title()
                if len(block.spans) > 1 and block.spans[1].text.strip() else "")
        date_line = mp.unsigned_decl_execution_line(year, location)
    else:
        role_override = block.spans[0].text.strip() if block.spans else ""
        role = (role_override.title() if role_override
                else str(meta.get("filer_role", "")).title())
        date_line = mp.unsigned_dated_line(year)
    lines = [date_line, "", "____________________________________", "", name]
    if role:
        lines.append(role)
    return "\n".join(lines)


def _is_tight(block: mp.Block) -> bool:
    """List items (bullets / numbered) pack tight against their siblings."""
    return block.kind in ("bullet", "numbered")


def render_text(meta: Dict, body: str, variant: str) -> str:
    label = str(meta.get("exhibit_label", "Exhibit"))

    body = mp.substitute_redaction_macros(body, meta, variant)
    body = substitute_exhibit_index(body, meta, label)
    exhibit_map = build_exhibit_map(meta, label)
    body = substitute_exhibit_refs(body, exhibit_map)
    body = mp.substitute_date_macro(body, meta)

    # Shared front-end transforms, identical to the PDF/DOCX renderers:
    # expand the '#.' flat auto-numbering sentinel, pull footnote definitions
    # out of the body, and number references in reading order (defined ids
    # only \u2014 undefined ids keep their literal marker).
    body = mp.autonumber_list_items(body)
    body, footnote_defs = mp.extract_footnote_defs(body)
    footnote_numbers: Dict[str, int] = {}
    for m in re.finditer(r"\[\^([^\]]+?)\]", body):
        fid = m.group(1).strip()
        if fid in footnote_defs and fid not in footnote_numbers:
            footnote_numbers[fid] = len(footnote_numbers) + 1

    doctype = meta.get("doctype", "pleading")
    blocks = mp.parse_markdown_blocks(body, doctype=doctype)
    if meta.get("heading_numbers", True):
        blocks = mp.number_headings(blocks)

    # Build (line, tight) pairs. Consecutive tight items (list members) are
    # joined by a single newline; everything else is separated by a blank line.
    items: List[tuple] = []
    for block in blocks:
        if block.kind == "table":
            for row in (block.rows or []):
                items.append((" | ".join(row), True))
            continue
        if block.kind in ("signblock", "declsignblock"):
            items.append((_signature_block_text(block, meta), False))
            continue
        if block.kind in ("qrblock", "qrblockfile"):
            # Text output has no pixels; the honest equivalent is the
            # payload itself, labeled, which is what the QR encodes.
            caption = block.spans[0].text if block.spans else ""
            header = f"[QR code{': ' + caption if caption else ''}]"
            items.append((header + "\n" + mp.qr_payload(block), False))
            continue
        items.append((block_to_line(block, footnote_numbers), _is_tight(block)))

    # Footnotes: inline [n] markers point at an end-of-document notes
    # section, one "[n] text" line per note in number order.
    for fid, num in sorted(footnote_numbers.items(), key=lambda kv: kv[1]):
        items.append((f"[{num}] {mp.typographic_subs(footnote_defs[fid])}",
                      False))

    parts: List[str] = []
    # Plain text has no pages and no red, so the banner goes once at the
    # top, delimited so it cannot be mistaken for the document's own
    # first line. A .txt of a draft gets pasted into email more often
    # than a PDF does, which is precisely when the reader needs to know.
    banner = mp.draft_banner_text(meta)
    if banner:
        parts.append(f"*** {banner} ***\n\n")
    for idx, (line, tight) in enumerate(items):
        if idx > 0:
            prev_tight = items[idx - 1][1]
            parts.append("\n" if (tight and prev_tight) else "\n\n")
        parts.append(line)
    return "".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render a markdown source to plain text with no hard line breaks.")
    parser.add_argument("input", help="Markdown source file with YAML front matter")
    parser.add_argument("output", help="Output .txt path")
    parser.add_argument("--variant", choices=sorted(mp.SUPPORTED_VARIANTS),
                        default="sealed",
                        help="Render variant for variant-aware metadata and redactions")
    parser.add_argument("--attachments-dir", metavar="DIR", default=None,
                        help="Also copy each exhibit's source file into DIR under "
                             "its numbered name (Exhibit_NN_shortname.ext)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    raw = input_path.read_text(encoding="utf-8")
    meta, body = mp.parse_front_matter(raw)
    mp.warn_unknown_front_matter_keys(meta, Path(args.input).name)
    meta = mp.apply_variant_to_meta(meta, args.variant)

    text = render_text(meta, body, args.variant)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")

    if args.attachments_dir:
        base_dir = input_path.resolve().parent.parent  # case directory
        copied, missing = copy_attachments(meta, base_dir, Path(args.attachments_dir))
        for name in copied:
            print(f"  copied {name}")
        for desc in missing:
            print(f"  WARNING: exhibit source not found: {desc}", file=sys.stderr)


if __name__ == "__main__":
    main()
