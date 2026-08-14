"""Line-wrap glue and em-dash enforcement.

Two live-matter regressions: a bold name at line end shed its comma
onto the next line ("Sibyl Kollmer\n, Henry Kollmer"), and spaced
em dashes rendered spaced because the house rule (text---text,
never spaced) was only a warning.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLEADING_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING_DIR))

import md_pleading as mp  # noqa: E402


def test_wrap_never_orphans_glued_punctuation():
    spans = mp.parse_inline_styles("to **Sibyl Kollmer**, **Henry Kollmer**, and more")
    words = mp.spans_to_styled_words(spans)
    # Wrap at every plausible width; no line may ever START with a
    # glued word (a bare comma, a closing paren...).
    for width in range(40, 400, 7):
        for line in mp.wrap_styled_words(words, float(width)):
            assert not line[0].no_space_before, (
                f"line starts with glued word {line[0].text!r} at width {width}"
            )


def test_em_dash_spacing_is_enforced_not_suggested():
    body = "under the Note --- by Lender or --- worse --- spaced.\n"
    fixed = mp.enforce_em_dash_spacing(body)
    assert " --- " not in fixed
    assert "Note---by" in fixed
    # a dash at a source line break is still a spaced dash
    wrapped = mp.enforce_em_dash_spacing("section 5000) ---\n   as of this")
    assert wrapped == "section 5000)---as of this"
    # a paragraph break is never bridged
    para = "ends here ---\n\nNew paragraph"
    assert mp.enforce_em_dash_spacing(para) == para
    # already-converted literal em dashes are normalized too
    assert " — " not in mp.enforce_em_dash_spacing("a — b")


def test_dash_runs_and_armor_are_untouched():
    armor = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nxyz\n-----END PGP PUBLIC KEY BLOCK-----"
    assert mp.enforce_em_dash_spacing(armor) == armor
    rule = "a --- b ---- c"
    assert "----" in mp.enforce_em_dash_spacing(rule)
