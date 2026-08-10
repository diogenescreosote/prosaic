"""Shared helpers for filling Judicial Council form captions.

Every JC form repeats the same caption furniture: the attorney/party
block, the court block, the party names, and the case number. These
helpers derive those values from a pleading's YAML front matter (the
same ``meta`` dict ``md_pleading.py`` uses), so individual form
descriptors can bind caption fields declaratively via ``auto:`` keys
instead of each filler reimplementing the parsing.

Extracted from the original per-form fillers; behavior is unchanged.
"""

from __future__ import annotations

from typing import Optional


def strip_county_prefix(county: str) -> str:
    """Return the bare county name.

    JC forms print "SUPERIOR COURT OF CALIFORNIA, COUNTY OF" as static
    label text, so the field should receive only the county name
    (e.g. ``"ALAMEDA"``), not the full phrase.
    """
    county = (county or "").strip()
    upper = county.upper()
    for prefix in ("COUNTY OF ", "COUNTY,"):
        if upper.startswith(prefix):
            return county[len(prefix):].strip()
    return county


def split_name_and_bar_number(filer_name: str, explicit_bar: str = "") -> tuple[str, str]:
    """Split ``"Sally Sattler, Esq. SBN 123456"`` into (name, bar number).

    An explicit bar number wins; otherwise an ``SBN``/``State Bar No.``
    suffix is parsed off the name.
    """
    name = (filer_name or "").strip()
    bar = (explicit_bar or "").strip()
    import re

    # Always strip an SBN suffix off the name: once the bar number is
    # returned separately, leaving it in the name makes callers print
    # it twice. An explicit bar number still wins as the value.
    m = re.search(r"[,\s]*\(?(?:SBN|State Bar No\.?|Bar No\.?)\s*#?\s*(\d{4,7})\)?\s*$",
                  name, re.IGNORECASE)
    if m:
        return name[: m.start()].rstrip(" ,"), (bar or m.group(1))
    return name, bar


def attorney_block_lines(meta: dict, max_lines: int = 4) -> list[str]:
    """Return the attorney/filer block as exactly ``max_lines`` lines.

    Line 1 is ``filer_name`` (with ``(SBN …)`` appended when
    ``filer_bar_number`` is present); the rest come from
    ``filer_address_lines``. Template placeholders like ``[address]``
    are dropped.
    """
    # Split any SBN already embedded in filer_name before re-appending,
    # so "Sally Sattler, Esq. SBN 123456" + filer_bar_number does not
    # print the bar number twice (real-world caption metadata routinely
    # carries the SBN in the name).
    name, bar = split_name_and_bar_number(
        str(meta.get("filer_name") or ""), str(meta.get("filer_bar_number") or ""))
    line1 = f"{name} (SBN {bar})" if (name and bar) else (name or (f"SBN {bar}" if bar else ""))

    address = [
        str(x).strip()
        for x in (meta.get("filer_address_lines") or [])
        if str(x).strip() and not (str(x).strip().startswith("[") and str(x).strip().endswith("]"))
    ]
    lines = [ln for ln in [line1, *address] if ln]
    return lines[:max_lines] + [""] * (max_lines - len(lines))


def filer_address_parts(meta: dict) -> dict:
    """Split ``filer_address_lines`` into discrete firm/street/city/state/zip.

    Some JC forms (EFS-020's attorney block, for one) have a separate
    field per address component instead of MC-030-style free-text
    lines. Heuristic: the *last* line containing a comma is taken as
    "City, ST ZIP"; the line before it is the street; anything earlier
    is the firm name. This handles both the 3-line represented form
    (firm / street / city-state-zip) and the 2-line pro per form
    (street / city-state-zip). Template placeholders like ``[address]``
    are dropped. State defaults to "CA" when any address is present
    (these are California forms).
    """
    lines = [
        str(x).strip()
        for x in (meta.get("filer_address_lines") or [])
        if str(x).strip()
        and not (str(x).strip().startswith("[") and str(x).strip().endswith("]"))
    ]
    parts = {"firm": "", "street": "", "city": "",
             "state": "CA" if lines else "", "zip": ""}
    if not lines:
        return parts
    rest = list(lines)
    csz = rest.pop() if "," in rest[-1] else ""
    if rest:
        parts["street"] = rest.pop()
    if rest:
        parts["firm"] = ", ".join(rest)
    if csz:
        city_part, tail = csz.split(",", 1)
        parts["city"] = city_part.strip()
        tail_words = tail.strip().split()
        if tail_words:
            parts["state"] = tail_words[0]
        if len(tail_words) > 1:
            parts["zip"] = tail_words[1]
    return parts


def attorney_for(meta: dict) -> str:
    """Resolve the "ATTORNEY FOR (Name):" caption value.

    Preference: explicit ``filer_attorney_for``; then the text after
    "Attorney for " in ``filer_role``; then the raw ``filer_role``
    (self-represented filers conventionally put their own role here,
    e.g. "Respondent, In Pro Per").
    """
    explicit = meta.get("filer_attorney_for")
    if explicit:
        return str(explicit).strip()
    role = str(meta.get("filer_role") or "").strip()
    if role.lower().startswith("attorney for "):
        return role[len("attorney for "):].strip()
    return role


def short_title(meta: dict) -> str:
    """Resolve the "SHORT TITLE" caption used by attachment-style forms.

    MC-025 (and similar continuation forms) carry a one-line short
    caption instead of the full party block. Preference: explicit
    ``short_title`` in the front matter; otherwise composed as
    ``"<petitioner> v. <respondent>"`` (or whichever party name is
    present).
    """
    explicit = str(meta.get("short_title") or "").strip()
    if explicit:
        return explicit
    pet = str(meta.get("petitioner") or "").strip()
    resp = str(meta.get("respondent") or "").strip()
    if pet and resp:
        return f"{pet} v. {resp}"
    return pet or resp


def declarant_name(meta: dict) -> Optional[str]:
    """Extract a declarant's name from ``declarant_name`` or the title.

    Falls back to parsing ``paper_title`` of the form
    ``"DECLARATION OF <NAME> [IN SUPPORT OF …]"``.
    """
    name = meta.get("declarant_name")
    if name:
        return str(name).strip()
    title = str(meta.get("paper_title") or "")
    upper = title.upper()
    marker = "DECLARATION OF "
    if marker not in upper:
        return None
    tail = title[upper.index(marker) + len(marker):]
    for cutoff in (" IN SUPPORT OF", " REGARDING", ","):
        idx = tail.upper().find(cutoff)
        if idx != -1:
            tail = tail[:idx]
            break
    return tail.strip() or None


#: The registry of ``auto:`` bindings available to form descriptors.
#: Each maps a caption key to a callable(meta) -> str.
AUTO_BINDINGS = {
    "attorney_line1": lambda m: attorney_block_lines(m)[0],
    "attorney_line2": lambda m: attorney_block_lines(m)[1],
    "attorney_line3": lambda m: attorney_block_lines(m)[2],
    "attorney_line4": lambda m: attorney_block_lines(m)[3],
    "attorney_block": lambda m: "\n".join(l for l in attorney_block_lines(m) if l),
    "phone": lambda m: str(m.get("filer_phone") or "").strip(),
    "fax": lambda m: str(m.get("filer_fax") or "").strip(),
    "email": lambda m: str(m.get("filer_email") or "").strip(),
    "attorney_for": attorney_for,
    # The filer's role verbatim ("Attorney for Respondent JANE ROE",
    # "Respondent, In Pro Per"). Distinct from attorney_for, which peels
    # off a leading "Attorney for " because the form prints that label
    # itself; forms with a bare "(TITLE)" line under a signature (e.g.
    # SUBP-010's issuing-person block) want the whole role.
    "filer_role": lambda m: str(m.get("filer_role") or "").strip(),
    # Discrete attorney-block components, for forms (e.g. EFS-020) that
    # split the block into name/bar/firm/street/city/state/zip fields
    # instead of free-text lines. Name and bar number are separated so
    # an "SBN 123456" suffix folded into filer_name is not printed
    # twice (the form has its own STATE BAR NUMBER box).
    "filer_name_bare": lambda m: split_name_and_bar_number(
        str(m.get("filer_name") or ""), str(m.get("filer_bar_number") or ""))[0],
    "filer_bar_number": lambda m: split_name_and_bar_number(
        str(m.get("filer_name") or ""), str(m.get("filer_bar_number") or ""))[1],
    "filer_firm": lambda m: filer_address_parts(m)["firm"],
    "filer_street": lambda m: filer_address_parts(m)["street"],
    "filer_city": lambda m: filer_address_parts(m)["city"],
    "filer_state": lambda m: filer_address_parts(m)["state"],
    "filer_zip": lambda m: filer_address_parts(m)["zip"],
    "hearing_time": lambda m: str(m.get("hearing_time") or "").strip(),
    "hearing_dept": lambda m: str(m.get("hearing_dept") or "").strip(),
    "court_county": lambda m: strip_county_prefix(str(m.get("court_county") or "")),
    "court_street_address": lambda m: str(m.get("court_street_address") or "").strip(),
    "court_mailing_address": lambda m: str(m.get("court_mailing_address") or "").strip(),
    "court_city_zip": lambda m: str(m.get("court_city_zip") or "").strip(),
    "court_branch": lambda m: str(m.get("court_branch") or "").strip(),
    "petitioner": lambda m: str(m.get("petitioner") or "").strip(),
    "respondent": lambda m: str(m.get("respondent") or "").strip(),
    "other_party": lambda m: str(m.get("other_party") or "").strip(),
    "case_number": lambda m: str(m.get("case_number") or "").strip(),
    "short_title": short_title,
    "paper_title": lambda m: str(m.get("paper_title") or "").strip(),
    "declarant_name": lambda m: declarant_name(m) or "",
    "see_attached_declaration": lambda m: (
        f"See attached Declaration of {declarant_name(m)}."
        if declarant_name(m) else "See attached declaration."
    ),
    "blank": lambda m: "",
}
