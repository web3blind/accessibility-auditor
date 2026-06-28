from agentkit_action_provider import PaidAuditUrlSchema, _parse_usd_price


def test_parse_usd_price_from_x402_string():
    assert _parse_usd_price("$0.10") == 0.10
    assert _parse_usd_price("0.25 USDC") == 0.25
    assert _parse_usd_price(None) is None


def test_paid_audit_schema_exposes_client_spending_controls():
    schema = PaidAuditUrlSchema(
        url="https://example.com",
        private_key="0xabc",
        max_price_usd=0.10,
        remaining_daily_budget_usd=1.00,
    )

    assert schema.max_price_usd == 0.10
    assert schema.remaining_daily_budget_usd == 1.00
