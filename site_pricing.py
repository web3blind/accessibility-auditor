"""Deterministic pricing helpers for multi-page site accessibility audits.

The MVP is dry-run friendly: it computes quote/settlement values without
calling x402Escrow contracts. Keep money math in Decimal and serialize as
fixed two-decimal USDC strings for API stability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

PRICE_PER_PAGE_USDC = Decimal("0.10")
SUMMARY_FEE_USDC = Decimal("0.30")
MIN_CHARGE_USDC = Decimal("0.00")
MAX_PAGES = 100
DEFAULT_MAX_PAGES = 10

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class SiteAuditPricing:
    currency: str
    price_per_page: Decimal
    summary_fee: Decimal
    max_locked: Decimal
    actual_settled: Decimal
    refund: Decimal
    successful_pages: int
    include_summary: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "price_per_page": format_usdc(self.price_per_page),
            "summary_fee": format_usdc(self.summary_fee),
            "max_locked": format_usdc(self.max_locked),
            "actual_settled": format_usdc(self.actual_settled),
            "refund": format_usdc(self.refund),
            "successful_pages": self.successful_pages,
            "include_summary": self.include_summary,
        }


def parse_usdc(value: str | int | float | Decimal) -> Decimal:
    """Parse a USDC amount into Decimal without accepting negative values."""
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value).replace("$", "").strip())
    if amount < 0:
        raise ValueError("USDC amount cannot be negative")
    return amount.quantize(_CENT, rounding=ROUND_DOWN)


def format_usdc(value: Decimal) -> str:
    return f"{value.quantize(_CENT):.2f}"


def clamp_max_pages(max_pages: int | None) -> int:
    if max_pages is None:
        return DEFAULT_MAX_PAGES
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")
    return min(int(max_pages), MAX_PAGES)


def estimate_max_cost(max_pages: int, include_summary: bool = True) -> Decimal:
    pages = clamp_max_pages(max_pages)
    total = PRICE_PER_PAGE_USDC * pages
    if include_summary and pages > 1:
        total += SUMMARY_FEE_USDC
    return total.quantize(_CENT)


def calculate_site_audit_price(
    successful_pages: int,
    max_locked: str | int | float | Decimal,
    include_summary: bool = True,
) -> SiteAuditPricing:
    """Calculate the actual settled cost and refund for completed work.

    Failed pages are not charged. If every page fails, the MVP settles zero.
    """
    if successful_pages < 0:
        raise ValueError("successful_pages cannot be negative")
    locked = parse_usdc(max_locked)
    actual = PRICE_PER_PAGE_USDC * int(successful_pages)
    if include_summary and successful_pages > 1:
        actual += SUMMARY_FEE_USDC
    actual = max(MIN_CHARGE_USDC, actual.quantize(_CENT))
    actual = min(actual, locked)
    refund = (locked - actual).quantize(_CENT)
    return SiteAuditPricing(
        currency="USDC",
        price_per_page=PRICE_PER_PAGE_USDC,
        summary_fee=SUMMARY_FEE_USDC if include_summary and successful_pages > 1 else Decimal("0.00"),
        max_locked=locked,
        actual_settled=actual,
        refund=refund,
        successful_pages=successful_pages,
        include_summary=include_summary,
    )


def build_site_audit_quote(url: str, max_pages: int | None = None, include_summary: bool = True) -> dict[str, Any]:
    pages = clamp_max_pages(max_pages)
    estimated = estimate_max_cost(pages, include_summary=include_summary)
    return {
        "root_url": url,
        "max_pages": pages,
        "estimated_max_cost_usdc": format_usdc(estimated),
        "price_per_page_usdc": format_usdc(PRICE_PER_PAGE_USDC),
        "summary_fee_usdc": format_usdc(SUMMARY_FEE_USDC if include_summary and pages > 1 else Decimal("0.00")),
        "hard_page_cap": MAX_PAGES,
        "payment_mode": "x402escrow",
        "note": "Final cost depends on pages actually audited. Unused escrow is refunded.",
    }
