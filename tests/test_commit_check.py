"""The commit-message contract's docket grammar, via `sc commit-check`.

Docket commits assert something happened in the world and must say
what, in a dated footer. Litigation's verbs (Filed/Served/Lodged/
Received) and estate practice's (Executed/Recorded) share one
grammar — the estate matter type made the gap visible when a signed
manifest had no lawful verb to carry.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"


def check(message: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SC), "commit-check"],
        input=message,
        capture_output=True,
        text=True,
    )


def test_docket_accepts_estate_verbs() -> None:
    proc = check(
        "docket: manifest signed and timestamped\n\n"
        "Body.\n\n"
        "Executed: 2026-08-13 (signed at the keyboard)\n"
        "Source: generated in place from the originals\n"
    )
    assert "docket" not in proc.stderr.lower() or "Executed" not in proc.stderr
    assert "add one of" not in proc.stderr


def test_docket_without_event_footer_is_flagged() -> None:
    proc = check("docket: something happened\n\nBody.\n\nSource: somewhere\n")
    assert "add one of" in proc.stderr
    # the guidance names the estate verbs alongside litigation's
    assert "Executed" in proc.stderr
