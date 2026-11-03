"""An escaped underscore renders as an underscore.

Markdown writers escape underscores (``\\_\\_\\_\\_``) so a blank is not read
as emphasis. This renderer never uses ``_`` for emphasis, so it unescapes
them rather than printing the backslashes. Verbatim spans keep theirs.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402


def _body(text: str) -> str:
    return mp.parse_front_matter("---\ntitle: x\n---\n" + text)[1]


def test_escaped_underscore_run_becomes_blank():
    assert _body("GRANTED \\_\\_\\_\\_ DENIED\n").strip() == "GRANTED ____ DENIED"


def test_single_escaped_underscore_unescaped():
    assert _body("snake\\_case\n").strip() == "snake_case"


def test_verbatim_span_keeps_backslash():
    assert "\\fixedwidth{a\\_b}" in _body("see \\fixedwidth{a\\_b}\n")
