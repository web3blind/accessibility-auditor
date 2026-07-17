import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from site_pricing import (
    build_site_audit_quote,
    calculate_site_audit_price,
    clamp_max_pages,
    estimate_max_cost,
    format_usdc,
    parse_usdc,
)


def test_parse_and_format_usdc_are_decimal_based():
    assert parse_usdc("$3.307") == Decimal("3.30")
    assert format_usdc(Decimal("2")) == "2.00"


def test_clamp_max_pages_enforces_bounds():
    assert clamp_max_pages(None) == 10
    assert clamp_max_pages(999) == 100


def test_clamp_max_pages_rejects_zero():
    try:
        clamp_max_pages(0)
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_estimate_max_cost_includes_summary_fee_for_multi_page():
    assert estimate_max_cost(3, include_summary=True) == Decimal("0.60")
    assert estimate_max_cost(1, include_summary=True) == Decimal("0.10")
    assert estimate_max_cost(3, include_summary=False) == Decimal("0.30")


def test_actual_price_charges_successful_pages_and_refunds_remainder():
    price = calculate_site_audit_price(successful_pages=17, max_locked="3.30", include_summary=True)
    assert price.as_dict()["actual_settled"] == "2.00"
    assert price.as_dict()["refund"] == "1.30"


def test_zero_success_pages_settles_zero_by_default():
    price = calculate_site_audit_price(successful_pages=0, max_locked="1.00", include_summary=True)
    assert price.as_dict()["actual_settled"] == "0.00"
    assert price.as_dict()["refund"] == "1.00"


def test_actual_price_never_exceeds_locked_budget():
    price = calculate_site_audit_price(successful_pages=50, max_locked="1.00", include_summary=True)
    assert price.as_dict()["actual_settled"] == "1.00"
    assert price.as_dict()["refund"] == "0.00"


def test_quote_shape_is_agent_friendly():
    quote = build_site_audit_quote("https://example.com", max_pages=30, include_summary=True)
    assert quote["estimated_max_cost_usdc"] == "3.30"
    assert quote["payment_mode"] == "x402escrow"
    assert quote["hard_page_cap"] == 100
