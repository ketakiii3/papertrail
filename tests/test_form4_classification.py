"""F3: only open-market Form 4 trades (codes P/S) count as insider buys/sells."""

from datetime import date
from pathlib import Path

import pytest

from contradiction_detector.agent_tools import summarize_insider_rows
from edgar_ingester.form4_parser import Form4Ingester, classify_transaction, form4_xml_url

FIXTURE = Path(__file__).parent / "fixtures" / "form4_sample.xml"


@pytest.fixture
def rows():
    # Skip __init__ (it opens an HTTP client); parsing needs no instance state.
    parser = Form4Ingester.__new__(Form4Ingester)
    return parser.parse_form4_xml(FIXTURE.read_text())


@pytest.mark.parametrize(
    "code,expected",
    [("S", "sell"), ("P", "buy"), ("s", "sell"), ("F", "other"), ("G", "other"),
     ("M", "other"), ("X", "other"), ("A", "other"), ("", "other"), (None, "other")],
)
def test_classify_transaction(code, expected):
    assert classify_transaction(code) == expected


def test_parse_fixture_classifies_by_code(rows):
    assert [r["transaction_code"] for r in rows] == ["S", "F", "M"]
    assert [r["transaction_type"] for r in rows] == ["sell", "other", "other"]
    assert all(r["acquired_disposed"] == "D" for r in rows)
    sale = rows[0]
    assert sale["insider_name"] == "Doe Jane"
    assert sale["insider_title"] == "Chief Executive Officer"
    assert sale["transaction_date"] == date(2025, 4, 4)
    assert sale["shares"] == pytest.approx(4000.5)  # fractional shares survive parsing
    assert sale["total_value"] == pytest.approx(800_100.0)


def test_summary_ignores_non_open_market_rows(rows):
    summary = summarize_insider_rows(rows)
    assert summary["sell_count"] == 1
    assert summary["other_count"] == 2
    assert summary["buy_count"] == 0
    # Only the S row's notional counts; the F row's $2.1M of withheld stock does not.
    assert summary["total_sell_value"] == pytest.approx(800_100.0)


def test_tax_withholding_alone_is_not_large_insider_selling():
    rows = [
        {"transaction_type": "other", "total_value": 5_000_000},
        {"transaction_type": "other", "total_value": 1_000_000},
        {"transaction_type": "other", "total_value": 1_000_000},
    ]
    summary = summarize_insider_rows(rows)
    assert summary["sell_count"] == 0
    assert summary["large_insider_sales"] is False


def test_three_open_market_sells_is_large():
    rows = [{"transaction_type": "sell", "total_value": 10_000}] * 3
    assert summarize_insider_rows(rows)["large_insider_sales"] is True


@pytest.mark.parametrize(
    "primary_doc,expected_doc",
    [("xslF345X06/form4.xml", "form4.xml"), ("xslF345X05/wf-form4_1.xml", "wf-form4_1.xml"),
     ("form4.xml", "form4.xml")],
)
def test_form4_xml_url_points_at_raw_xml_on_www(primary_doc, expected_doc):
    url = form4_xml_url("0000320193", "0001140361-26-035636", primary_doc)
    assert url == f"https://www.sec.gov/Archives/edgar/data/320193/000114036126035636/{expected_doc}"
