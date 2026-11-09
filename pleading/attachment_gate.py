"""An attachment travels with the form it is attached to.

A Judicial Council form whose "Attachment N" box is checked is filed as
ONE document: the form, then the attachment. The attachment is never its
own document in the e-filing envelope. A clerk who receives a request
form with an Attachment box checked and the declaration uploaded beside
it rejects the whole envelope ("... has box or attachment 9 marked, but
there is nothing attached. You must append Attachment #9 to the [form]
as one PDF document").

Drafting the form and its attachment as separate sources is fine and
common: the form as a `cover_sheet_only:` source, the attachment as a
captioned declaration titled "... (ATTACHMENT 9 TO REQUEST FOR ORDER)".
What must not happen is that the pair leaves the building split. So the
envelope says which form each attachment belongs to (`attachment_of:` on
the attachment's entry in envelopes.yaml), and a `--final` build refuses
an envelope that leaves either half unaccounted for:

  * a form-only source whose resolved values check an attachment box,
    with no envelope source declared `attachment_of:` it, and no engine
    overflow attachment drawn into the form's own output;
  * a source titled "ATTACHMENT N TO ..." that carries no `cover_sheet:`
    (which would prepend the form, making one PDF) and declares no
    `attachment_of:`.

Draft builds print the same findings as warnings. The check on the
assembled, signed set is `filing_check.py` (`sc filing-check <dir>`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import yaml

#: "ATTACHMENT 9 TO REQUEST FOR ORDER", "Attachment 3 to Deposition
#: Subpoena", "ATTACHMENT 2a TO ...". The number distinguishes a form
#: attachment from an exhibit or a document merely about attachments.
ATTACHMENT_TITLE_RE = re.compile(r"\bATTACHMENT\s+\d+[A-Z]?\s+TO\b", re.IGNORECASE)

#: Descriptor checkboxes named attachment_<n...> are the form's own
#: "Attachment N" boxes (attachment_2a, attachment_9 and so on); every
#: descriptor with such boxes follows this naming.
ATTACHMENT_BOX_RE = re.compile(r"^attachment_\w+$")


def read_front_matter(path: Path) -> dict:
    """The YAML front matter of a Markdown source, or {} if it has none.

    Read directly rather than through md_pleading.parse_front_matter so
    the gate stays cheap: no font registration, no body processing.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    try:
        data = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def is_attachment_title(meta: dict) -> bool:
    title = str(meta.get("paper_title") or "")
    return bool(ATTACHMENT_TITLE_RE.search(title))


def _engine_managed_boxes(desc: dict, texts: Dict[str, str]) -> set:
    """Attachment boxes the fill engine sets itself.

    A field with `overflow_checkbox:` checks that box only when its text
    spills to an engine-generated attachment drawn into the same output,
    and clears it otherwise; such a box is never an orphan.
    """
    managed = set()
    for name, spec in (desc.get("fields") or {}).items():
        if not str(texts.get(name) or "").strip():
            continue
        for key in ("overflow_checkbox", "inline_checkbox"):
            box = spec.get(key)
            if box:
                managed.add(box)
    return managed


def checked_attachment_boxes(
    meta: dict,
    load_descriptor: Optional[Callable[[str], dict]] = None,
) -> List[str]:
    """Attachment boxes the source's cover form will draw checked.

    Resolved exactly as the fill will resolve them (descriptor defaults,
    then the `forms:` block), so a box that is on by default counts even
    when the source never mentions it.
    """
    form_id = meta.get("cover_sheet")
    if not form_id:
        return []
    import form_fill
    if load_descriptor is None:
        load_descriptor = form_fill.load_descriptor
    try:
        desc = load_descriptor(str(form_id))
    except FileNotFoundError:
        return []
    try:
        texts, checks, _explicit, _problems = form_fill.resolve_values(desc, meta)
    except ValueError:
        # A malformed forms: block fails the render itself, loudly; the
        # gate has nothing to add.
        return []
    managed = _engine_managed_boxes(desc, texts)
    return sorted(
        name for name, on in checks.items()
        if on and ATTACHMENT_BOX_RE.match(name) and name not in managed
    )


def envelope_problems(
    entries: Iterable[Tuple[str, Optional[str]]],
    src_dir: Path,
    load_descriptor: Optional[Callable[[str], dict]] = None,
) -> List[str]:
    """Findings for one envelope.

    `entries` is (source file relative to src/, its `attachment_of:` or
    None) for every PDF source in the envelope.
    """
    entries = list(entries)
    files = {f for f, _ in entries}
    attached_to: Dict[str, List[str]] = {}
    problems: List[str] = []

    for f, parent in entries:
        if not parent:
            continue
        if parent not in files:
            problems.append(
                f"{f}: attachment_of: {parent!r} is not a source in this "
                f"envelope. The attachment is filed with its form, so both "
                f"belong to the same envelope."
            )
            continue
        attached_to.setdefault(parent, []).append(f)

    for f, parent in entries:
        meta = read_front_matter(src_dir / f)
        if parent:
            pmeta = read_front_matter(src_dir / parent)
            if not pmeta.get("cover_sheet"):
                problems.append(
                    f"{f}: attachment_of: {parent!r} names a source with no "
                    f"cover_sheet form. An attachment belongs to a form."
                )
            continue
        if meta.get("cover_sheet_only"):
            boxes = checked_attachment_boxes(meta, load_descriptor)
            if boxes and f not in attached_to:
                problems.append(
                    f"{f}: the {meta.get('cover_sheet')} form checks "
                    f"{', '.join(boxes)}, but nothing in this envelope is "
                    f"attached to it. File the form and its attachment as "
                    f"ONE PDF: give the attachment's entry in envelopes.yaml "
                    f"`attachment_of: {f}` (and join the two signed PDFs, "
                    f"form first, before filing; `sc filing-check` verifies "
                    f"the folder), or put `cover_sheet: "
                    f"{meta.get('cover_sheet')}` on the attachment source so "
                    f"it builds as one PDF. If the form really has no "
                    f"attachment, set the box false in its forms: block."
                )
        elif is_attachment_title(meta) and not meta.get("cover_sheet"):
            problems.append(
                f"{f}: titled {meta.get('paper_title')!r}, so it is an "
                f"attachment to a form, but it carries no cover_sheet and no "
                f"envelope source declares it. An attachment is never filed "
                f"as its own document. Give its entry in envelopes.yaml "
                f"`attachment_of: <the form's source>`, or put the form on "
                f"it as `cover_sheet:` so the two build as one PDF."
            )
    return problems
