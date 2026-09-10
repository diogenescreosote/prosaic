"""E-sign geometry comes from the build, and the DocuSeal client checks it.

The failure that motivated this: a <pdf>.fields.json written by hand
from text positions put a date box on top of its underline and a
signature box across the printed name beneath the rule. Three
promises now: a standalone `sc form fill` writes the sidecar for any
form whose descriptor declares esign: fields; a \\signblock{dated}
with a long name and role lays its boxes above their rules with the
name clear of them, in the final build and under the draft banner's
page transform alike; and `docuseal send` refuses a sidecar the build
did not write (without --allow-hand-fields) and any sidecar whose
boxes cover printed text or straddle their rule.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FORM_FILL = REPO_ROOT / "pleading" / "form_fill.py"
MD_PLEADING = REPO_ROOT / "pleading" / "md_pleading.py"
CLIENT = REPO_ROOT / "docuseal-client" / "client.py"

pymupdf = pytest.importorskip("pymupdf")

META = {
    "filer_name": "Jane Roe",
    "filer_address_lines": ["100 Main St, Suite 4", "Springfield, CA 90000"],
    "filer_phone": "(555) 555-0100",
    "filer_email": "jane.roe@example.com",
    "filer_role": "Respondent, In Pro Per",
    "court_county": "EXAMPLE",
    "court_street_address": "100 Court Street",
    "court_mailing_address": "100 Court Street",
    "court_city_zip": "Example City, CA 90000",
    "court_branch": "Civil Division",
    "petitioner": "JOHN SMITH",
    "respondent": "JANE ROE",
    "case_number": "24CV00000",
}
DATA = {
    "consumer": "PAT CONSUMER",
    "requesting_party": "JANE ROE, Respondent",
    "production_date": "October 2, 2026",
    "witness": "Custodian of Records, Example Bank, N.A., 1 Bank Plaza, Example City, CA 90000",
    "signed_by_requesting_party": True,
}
SIDECAR_HEAD = {"page_width": 612, "page_height": 792, "origin": "top-left", "units": "pt"}


def client_module() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("docuseal_client_under_test", str(CLIENT))
    spec = importlib.util.spec_from_loader("docuseal_client_under_test", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def fill(form_id: str, tmp_path: Path) -> Path:
    import yaml
    (tmp_path / "meta.yaml").write_text(yaml.safe_dump(META))
    (tmp_path / "data.yaml").write_text(yaml.safe_dump(DATA))
    out = tmp_path / f"{form_id}.pdf"
    proc = subprocess.run(
        [sys.executable, str(FORM_FILL), "fill", form_id,
         "--meta", str(tmp_path / "meta.yaml"), "--data", str(tmp_path / "data.yaml"),
         "-o", str(out)],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    return out


@pytest.mark.parametrize("form_id, expected", [
    ("subp025", {"notice_date": "date", "notice_signature": "signature"}),
    ("fw001", {"sig_date": "date", "signature": "signature"}),
    ("mc030", {"date": "date", "signature": "signature"}),
])
def test_form_fill_writes_a_build_sidecar_on_the_rules(
        form_id: str, expected: dict[str, str], tmp_path: Path) -> None:
    out = fill(form_id, tmp_path)
    sidecar_path = out.with_name(out.name + ".fields.json")
    assert sidecar_path.exists(), "a fill of a form with esign: fields must write the sidecar"
    sidecar = json.loads(sidecar_path.read_text())
    assert sidecar["source"] == "build"
    assert {f["name"]: f["type"] for f in sidecar["fields"]} == expected
    assert client_module().sidecar_geometry_problems(out, sidecar) == []


def test_form_without_esign_fields_writes_no_sidecar(tmp_path: Path) -> None:
    out = fill("mc025", tmp_path)
    assert not out.with_name(out.name + ".fields.json").exists()


@pytest.mark.parametrize("final", [True, False], ids=["final", "draft-banner"])
def test_dated_signblock_with_a_long_name_clears_its_boxes(tmp_path: Path, final: bool) -> None:
    """Both the final build and the draft build (whose banner scales the
    page content down) must record boxes where the ink actually is."""
    src = tmp_path / "doc.md"
    src.write_text(
        "---\ndoctype: document\nheading_numbers: false\npaper_title: \"Authorization\"\n---\n\n"
        "1. I authorize the disclosure described above, and nothing else.\n\n"
        "\\signblock{dated}{Jane Roe}{for herself and as parent of Pat Roe}\n")
    argv = [sys.executable, str(MD_PLEADING), str(src), str(tmp_path / "doc.pdf")]
    if final:
        argv.append("--final")
    proc = subprocess.run(argv, capture_output=True, text=True, cwd=tmp_path, timeout=300)
    assert proc.returncode == 0, proc.stderr
    sidecar = json.loads((tmp_path / "doc.pdf.fields.json").read_text())
    assert sidecar["source"] == "build"
    assert {f["type"] for f in sidecar["fields"]} == {"date", "signature"}
    assert client_module().sidecar_geometry_problems(tmp_path / "doc.pdf", sidecar) == []
    # The name and role print below the rule, outside the signature box.
    page = pymupdf.open(str(tmp_path / "doc.pdf"))[0]
    sig = next(f for f in sidecar["fields"] if f["type"] == "signature")
    box_bottom = sig["y_top"] + sig["h"]
    for needle in ("Jane Roe", "Pat Roe"):
        hits = [r for r in page.search_for(needle) if r.y0 > 200]
        assert hits, needle
        assert all(r.y0 >= box_bottom - 1 for r in hits), f"{needle} collides with the box"


def _pdf_with_a_signature_line(path: Path) -> tuple[float, float]:
    """A one-page PDF: prose, an underscore rule, a printed name beneath.
    Returns (rule_y_top, name_y_top) in top-left points."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(72, 500, "I agree to the terms above.")
    c.drawString(72, 440, "Signature: ______________________________")
    c.drawString(72, 420, "Jane Roe, for herself and as parent of Pat Roe")
    c.showPage()
    c.save()
    return letter[1] - 440, letter[1] - 420


def _signature_sidecar(y_top: float, h: float = 26) -> dict[str, object]:
    return {**SIDECAR_HEAD, "fields": [
        {"name": "Signature", "role": "Signer", "type": "signature", "page": 1,
         "x": 140, "y_top": y_top, "w": 200, "h": h}]}


def test_geometry_check_rejects_a_straddling_or_covering_box(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    rule_y, name_y = _pdf_with_a_signature_line(pdf)
    mod = client_module()
    assert mod.sidecar_geometry_problems(pdf, _signature_sidecar(rule_y - 26)) == []
    problems = mod.sidecar_geometry_problems(pdf, _signature_sidecar(rule_y - 8))
    assert any("straddles" in p for p in problems), problems
    problems = mod.sidecar_geometry_problems(pdf, _signature_sidecar(name_y - 6, h=20))
    assert any("covers printed text" in p for p in problems), problems


def test_send_refuses_a_hand_written_sidecar_without_the_flag(tmp_path: Path) -> None:
    pdf = tmp_path / "a.pdf"
    rule_y, _ = _pdf_with_a_signature_line(pdf)
    (tmp_path / "a.pdf.fields.json").write_text(json.dumps(_signature_sidecar(rule_y - 26)))
    env = {"PATH": "/usr/bin:/bin", "DOCUSEAL_URL": "http://127.0.0.1:1",
           "DOCUSEAL_API_KEY": "test-key"}
    proc = subprocess.run(
        [sys.executable, str(CLIENT), "send", "a.pdf", "--to", "Jane Roe <jane@example.com>"],
        capture_output=True, text=True, cwd=tmp_path, env=env, timeout=60)
    assert proc.returncode != 0
    assert "not written by the build" in proc.stderr
    assert "--allow-hand-fields" in proc.stderr
