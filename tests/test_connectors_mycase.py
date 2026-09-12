"""The mycase connector's testable seams: billing-row parsing and naming.

The connector is browser automation end to end, so the deterministic
tests live at the two pure functions it exports: the /bills listing
parser (cheerio over a saved-page-shaped fixture) and the detail-line
to dated-snake_case name mapping. Everything network-shaped stays in
the *(untested)* column of the spec, where portal automation belongs.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MYCASE = REPO_ROOT / "connectors" / "mycase"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _node(expr: str) -> str:
    """Evaluate a JS expression against connectors/mycase, return stdout."""
    out = subprocess.run(
        ["node", "-e", f"process.stdout.write(String({expr}))"],
        cwd=MYCASE,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


# --- billFileName ------------------------------------------------------


@pytest.mark.parametrize(
    "detail,expected",
    [
        # An invoice: date prefix, invoice number, snake_case.
        ("Jul 28, 2026 - Inv. #10001", "2026-07-28_invoice_10001"),
        # A funds (trust/retainer) request: reference slugged, '#'/'-' dropped.
        ("Sep 15, 2025 - #R-00042", "2025-09-15_funds_request_r00042"),
        # Single-digit day zero-padded so names sort chronologically.
        ("Mar 5, 2025 - #R-00007", "2025-03-05_funds_request_r00007"),
        # A dated line with an unrecognized reference keeps the date.
        ("Jan 2, 2026 - Statement", "2026-01-02_bill_77"),
        # Garbage falls back to the portal's bill id alone.
        ("", "bill_77"),
        ("not a date at all", "bill_77"),
    ],
)
def test_bill_file_name(detail: dict[str, str], expected: str) -> None:
    got = _node(f"require('./pull.js').billFileName({json.dumps(detail)}, '77')")
    assert got == expected


# --- parseBillRows ------------------------------------------------------

# The shape MyCase renders on /bills: <li class="payable"> rows, an
# anchor to /bills/<id>, amount and detail spans, and a status that is
# either an alert ("Overdue") or a payment note ("Paid ...",
# "Forwarded to #...").
FIXTURE = """
<ul class="list">
  <li class="payable list-row">
    <a href="/bills/111222333" class="col-8">
      <span class="list-row__header mt-0">$1,234.56</span>
      <span class="list-row__header-detail">Jul 28, 2026 - Inv. #10001</span>
    </a>
    <div><span class="list-row__alert-text">Overdue</span>
      <a href="/pay/111222333">Pay Now</a></div>
  </li>
  <li class="payable list-row">
    <a href="/bills/111222334" class="col-8">
      <span class="list-row__header mt-0">$500.00</span>
      <span class="list-row__header-detail">Sep 15, 2025 - #R-00042</span>
    </a>
    <div><div class="payable-row__payment">Paid Sep 19, 2025</div></div>
  </li>
  <li class="payable list-row">
    <a href="/bills/111222335" class="col-8">
      <span class="list-row__header mt-0">$99.00</span>
      <span class="list-row__header-detail">Jun 29, 2026 - Inv. #9999</span>
    </a>
    <div><div class="payable-row__payment">Forwarded to #10001</div></div>
  </li>
  <li class="not-a-payable"><a href="/bills/999">ignored</a></li>
</ul>
"""


def test_parse_bill_rows() -> None:
    got = json.loads(
        _node(f"JSON.stringify(require('./pull.js').parseBillRows({json.dumps(FIXTURE)}))")
    )
    assert got == [
        {
            "id": "111222333",
            "amount": "$1,234.56",
            "detail": "Jul 28, 2026 - Inv. #10001",
            "status": "Overdue",
        },
        {
            "id": "111222334",
            "amount": "$500.00",
            "detail": "Sep 15, 2025 - #R-00042",
            "status": "Paid Sep 19, 2025",
        },
        {
            "id": "111222335",
            "amount": "$99.00",
            "detail": "Jun 29, 2026 - Inv. #9999",
            "status": "Forwarded to #10001",
        },
    ]


# --- billExportHref ------------------------------------------------------

# An invoice detail page offers the portal's PDF export; a funds-request
# detail page offers no export control at all (and guessing the export
# URL blind returns an error page rendered as a PDF).
INVOICE_DETAIL = """
<div class="payable-detail">
  <a href="/bills/111222333.pdf" class="payable-detail__export-link">
    View Full Invoice (PDF)</a>
  <a href="/pay/111222333" class="btn">Pay Now</a>
</div>
"""

FUNDS_REQUEST_DETAIL = """
<div class="payable-detail">
  <h1>Funds Request: #R-00042</h1>
  <a href="/bills" class="header__back-button">back</a>
</div>
"""

BARE_PDF_LINK = '<a href="/bills/98765.pdf">export</a>'


@pytest.mark.parametrize(
    "html,expected",
    [
        (INVOICE_DETAIL, "/bills/111222333.pdf"),
        (FUNDS_REQUEST_DETAIL, None),
        # A page shaped differently but still linking the export is
        # honored — the class name is the portal's, not a guarantee.
        (BARE_PDF_LINK, "/bills/98765.pdf"),
    ],
)
def test_bill_export_href(html: str, expected: list[str] | None) -> None:
    got = json.loads(
        _node(f"JSON.stringify(require('./pull.js').billExportHref({json.dumps(html)}))")
    )
    assert got == expected


def test_requiring_the_connector_runs_nothing() -> None:
    """pull.js is importable for its helpers without starting a pull —
    no browser launch, no config read, no output."""
    out = subprocess.run(
        ["node", "-e", "require('./pull.js'); process.stdout.write('ok')"],
        cwd=MYCASE,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout == "ok"
    assert out.stderr == ""
