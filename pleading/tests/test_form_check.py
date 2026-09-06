"""`sc form check`: every registered descriptor still fills under this engine.

This is the merge gate for engine changes. A deployment runs it with
PROSAIC_LAYERS_ROOT pointed at its own checkout so its local/ and
module descriptors are exercised by the candidate engine.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLEADING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLEADING))

import form_fill  # noqa: E402


def test_every_builtin_form_checks_clean(tmp_path):
    rows = form_fill.check_forms(keep_dir=tmp_path)
    assert [r.form_id for r in rows] == form_fill.list_forms()
    failures = [(r.form_id, r.error) for r in rows if not r.ok]
    assert not failures, failures
    for r in rows:
        assert r.pages >= 1
        assert (tmp_path / f"{r.form_id}.full.pdf").exists()
        assert (tmp_path / f"{r.form_id}.preview.pdf").exists()


def test_check_reports_a_broken_descriptor_as_a_row(tmp_path, monkeypatch):
    real = form_fill.load_descriptor

    def broken(form_id):
        if form_id == "mc040":
            raise ValueError("synthetic descriptor fault")
        return real(form_id)

    monkeypatch.setattr(form_fill, "load_descriptor", broken)
    rows = form_fill.check_forms(["mc040", "subp010"], keep_dir=tmp_path)
    by = {r.form_id: r for r in rows}
    assert not by["mc040"].ok and "synthetic descriptor fault" in by["mc040"].error
    assert by["subp010"].ok
    text = form_fill.format_check(rows)
    assert "1 failed" in text and "FAIL" in text


def test_cli_check_exit_status(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(PLEADING / "form_fill.py"), "check", "mc040", "--keep", str(tmp_path)],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 forms, 1 ok, 0 failed" in proc.stdout
