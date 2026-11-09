#!/usr/bin/env python3
"""Preflight a folder of PDFs about to be uploaded as one e-filing envelope.

    sc filing-check <folder>

The build checks sources (attachment_gate.py); this checks what is
actually uploaded: the signed, assembled PDFs in a staging folder, which
are put together by hand after signing and are where a form and its
attachment get split.

ERRORS (exit 1):
  * an attachment is its own PDF. Its first page is titled
    "ATTACHMENT N TO ..." (or a declaration "(ATTACHMENT N TO ...)") and
    is not a Judicial Council form page, so it would be uploaded beside
    its form instead of inside it. Join it to the form, form first, as
    one PDF.

WARNINGS (exit 0, read them):
  * a form that has "Attachment N" boxes (any registry descriptor with
    an attachment_* checkbox) with no pages after the form: if one of
    those boxes is checked, the attachment must follow the form in the
    same PDF;
  * a Notice of Remote Appearance (RA-010) with no proposed order
    (RA-020) in the folder; some clerks reject the notice without one.

Only the first page of each PDF is read, plus the page count.
"""

from __future__ import annotations

if __name__ == "__main__":
    import project_python
    project_python.ensure(__file__, "filing-check")

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from attachment_gate import ATTACHMENT_TITLE_RE

#: A Judicial Council form identifies itself in its footer (letters, a
#: hyphen, three digits: "SUBP-010 [Rev. ...]") beside "Form Adopted
#: for Mandatory Use".
FORM_ID_RE = re.compile(r"\b[A-Z]{2,4}-\d{3}[A-Z]?\b")
FORM_MARK_RE = re.compile(
    r"Form (Adopted|Approved) for (Mandatory|Optional) Use|Judicial Council of California",
    re.IGNORECASE)


def attachment_bearing_forms() -> dict:
    """Display id -> blank page count, for every registered form with an
    "Attachment N" checkbox. A PDF no longer than its blank form has
    nothing appended to it.
    """
    import form_fill
    from pypdf import PdfReader
    from attachment_gate import ATTACHMENT_BOX_RE
    found = {}
    for form in form_fill.list_forms():
        try:
            desc = form_fill.load_descriptor(form)
        except Exception:
            continue
        if not any(ATTACHMENT_BOX_RE.match(b) for b in (desc.get("checkboxes") or {})):
            continue
        display = re.sub(r"^([A-Za-z]+)-?(\d+)$", r"\1-\2", form).upper()
        try:
            found[display] = len(PdfReader(str(form_fill.blank_path(desc))).pages)
        except Exception:
            continue
    return found

#: How much of page 1 counts as its title region, in lines of text.
TITLE_LINES = 45


@dataclass
class Report:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def first_page_text(pdf: Path) -> tuple[str, int]:
    import pymupdf
    with pymupdf.open(pdf) as doc:
        if doc.page_count == 0:
            return "", 0
        return doc[0].get_text(), doc.page_count


def form_id(text: str) -> str:
    """The JC form number printed on a form page, or '' for a pleading."""
    if not FORM_MARK_RE.search(text):
        return ""
    m = FORM_ID_RE.search(text)
    return m.group(0) if m else ""


def check_folder(folder: Path) -> Report:
    report = Report()
    pdfs = sorted(p for p in folder.iterdir()
                  if p.suffix.lower() == ".pdf" and p.is_file())
    if not pdfs:
        report.errors.append(f"{folder}: no PDFs to check")
        return report
    forms_present = set()
    bearing = attachment_bearing_forms()
    for pdf in pdfs:
        try:
            text, pages = first_page_text(pdf)
        except Exception as exc:  # unreadable PDF is itself a finding
            report.errors.append(f"{pdf.name}: cannot be read ({exc})")
            continue
        fid = form_id(text)
        if fid:
            forms_present.add(fid)
        head = "\n".join(text.splitlines()[:TITLE_LINES])
        if not fid and ATTACHMENT_TITLE_RE.search(head):
            title = ATTACHMENT_TITLE_RE.search(head).group(0)
            report.errors.append(
                f"{pdf.name}: page 1 reads {title!r} but is not a form page, "
                f"so this attachment would be filed as its own document. "
                f"Append it to its form as ONE PDF, form first "
                f"(qpdf --empty --pages <form>.pdf <attachment>.pdf -- <joined>.pdf), "
                f"and remove the separate copy from this folder."
            )
        if fid in bearing and pages <= bearing[fid]:
            report.warnings.append(
                f"{pdf.name}: {fid}, {pages} page(s). If any Attachment box "
                f"on it is checked, the attachment must follow the form in "
                f"this same PDF. Look at the page before filing."
            )
    if "RA-010" in forms_present and "RA-020" not in forms_present:
        report.warnings.append(
            "RA-010 (Notice of Remote Appearance) with no RA-020 proposed "
            "order in this folder; some clerks reject the notice without one."
        )
    return report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=Path,
                        help="the folder of PDFs to be uploaded as one envelope")
    args = parser.parse_args(argv)
    if not args.folder.is_dir():
        print(f"filing-check: {args.folder} is not a folder", file=sys.stderr)
        return 2
    report = check_folder(args.folder)
    for w in report.warnings:
        print(f"WARNING: {w}")
    for e in report.errors:
        print(f"ERROR: {e}")
    if report.errors:
        print(f"filing-check: {len(report.errors)} error(s); do not file this folder as it is.")
        return 1
    print(f"filing-check: no errors in {args.folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
