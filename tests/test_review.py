"""Preflight review plumbing (ADR-0045): deterministic cite extraction,
hash-tied report headers, and staleness that follows the source.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SC = REPO_ROOT / "cli" / "sc"


def sc(*argv: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SC), *argv], cwd=cwd, capture_output=True, text=True, timeout=300)


DRAFT = """---
paper_title: MEMORANDUM
---

The court may direct compliance on terms it declares (Code Civ. Proc., § 1987.1).
Relief is sought under Fam. Code §§ 3020, 3040(a) and Evid. Code, section 1014.
Time is shortened under Cal. Rules of Court, rule 5.92(d)(1) and LR 9.12B.
Federal law applies (45 C.F.R. § 164.512(e)(1)(v); 42 U.S.C. § 1320d-6).
See In re Marriage of Smith (2019) 40 Cal.App.5th 100, 105; Zeng v. Wang (2024) 100 Cal.App.5th 123.
"""


@pytest.fixture
def matter(tmp_path: Path) -> Path:
    m = tmp_path / "m"
    proc = sc("init", str(m), "--git", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    (m / "src").mkdir(exist_ok=True)
    (m / "src" / "mpa.md").write_text(DRAFT)
    (m / "envelopes.yaml").write_text("envelopes:\n  motion:\n    sources:\n      - file: mpa.md\n")
    (m / "knowledge" / "authorities.yaml").write_text(
        'authorities:\n  "code civ. proc., § 1987.1":\n    status: verified\n    proposition: compliance on terms\n')
    return m


def test_cites_extracts_every_form_and_reads_the_cache(matter: Path):
    out = sc("review", "cites", "motion", "--matter-dir", str(matter), cwd=matter).stdout
    for cite in ("Code Civ. Proc., § 1987.1", "Fam. Code §§ 3020, 3040(a)", "Evid. Code, section 1014",
                 "Cal. Rules of Court, rule 5.92(d)(1)", "LR 9.12B", "45 C.F.R. § 164.512(e)(1)(v)",
                 "42 U.S.C. § 1320d-6", "In re Marriage of Smith (2019) 40 Cal.App.5th 100, 105",
                 "Zeng v. Wang (2024) 100 Cal.App.5th 123"):
        assert cite in out, f"missed {cite!r}\n{out}"
    assert "| verified" in out and "unverified" in out
    assert "src/mpa.md:5" in out


def test_paths_and_report_header_carry_the_source_hash(matter: Path):
    paths = sc("review", "paths", "motion", "--matter-dir", str(matter), cwd=matter).stdout
    assert "src/mpa.md" in paths and "source_hash:" in paths and "current reports for this target: 0" in paths
    rp = Path(sc("review", "report", "motion", "--check", "judgereview", "--matter-dir", str(matter), cwd=matter).stdout.strip())
    assert rp.parent == matter / "derived" / "review" / "motion"
    text = rp.read_text()
    assert text.startswith("---\ncheck: judgereview\n") and "source_hash:" in text and "sha256:" in text
    assert "status: current" in text
    again = Path(sc("review", "report", "motion", "--check", "judgereview", "--matter-dir", str(matter), cwd=matter).stdout.strip())
    assert again == rp, "same target, same day, same hash: same file"


def test_status_marks_a_report_stale_when_the_source_changes(matter: Path):
    rp = Path(sc("review", "report", "motion", "--check", "oppo", "--matter-dir", str(matter), cwd=matter).stdout.strip())
    rp.write_text(rp.read_text() + "\n1. The draft is weak on notice.\n")
    st = sc("review", "status", "motion", "--matter-dir", str(matter), cwd=matter).stdout
    assert "current" in st and "0 stale" in st
    (matter / "src" / "mpa.md").write_text(DRAFT + "\nA new paragraph.\n")
    st = sc("review", "status", "motion", "--matter-dir", str(matter), cwd=matter).stdout
    assert "stale" in st and "changed since review: src/mpa.md" in st
    assert "status: stale" in rp.read_text(), "the report's own header says it is stale"
    paths = sc("review", "paths", "motion", "--matter-dir", str(matter), cwd=matter).stdout
    assert "STALE reports" in paths and rp.name in paths
    st = sc("review", "status", "motion", "--tidy", "--matter-dir", str(matter), cwd=matter).stdout
    assert "superseded/" in st and not rp.exists()
    assert (rp.parent / "superseded" / rp.name).exists()
    # a fresh report for the new revision gets a new hash in its name
    new = Path(sc("review", "report", "motion", "--check", "oppo", "--matter-dir", str(matter), cwd=matter).stdout.strip())
    assert new.name != rp.name


def test_source_path_target_works_without_an_envelope(matter: Path):
    out = sc("review", "cites", "src/mpa.md", "--matter-dir", str(matter), cwd=matter).stdout
    assert "citations in src/mpa.md" in out and "Zeng v. Wang" in out
