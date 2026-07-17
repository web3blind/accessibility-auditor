import base64
import importlib
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_app(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.delenv("X402ESCROW_ALLOW_DRY_RUN_REQUESTS", raising=False)
    if "bot_final" in sys.modules:
        return importlib.reload(sys.modules["bot_final"])
    return importlib.import_module("bot_final")


def test_x402escrow_site_audit_without_payment_returns_402(monkeypatch):
    bot_final = load_app(monkeypatch)
    client = TestClient(bot_final.app)

    response = client.post(
        "/api/x402escrow/site-audit",
        json={"url": "https://example.com", "max_pages": 2, "max_budget_usdc": "0.50"},
    )

    assert response.status_code == 402
    body = response.json()
    assert body["payment_mode"] == "x402escrow"
    assert body["accepts"][0]["extra"]["maxPages"] == 2
    assert body["accepts"][0]["maxAmountUSDC"] == "0.50"


def test_x402escrow_quote_uses_100_page_cap(monkeypatch):
    bot_final = load_app(monkeypatch)
    client = TestClient(bot_final.app)

    response = client.post(
        "/api/site-audit/quote",
        json={"url": "https://example.com", "max_pages": 999, "include_summary": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["max_pages"] == 100
    assert body["hard_page_cap"] == 100
    assert body["estimated_max_cost_usdc"] == "10.30"


def test_x_payment_header_accepts_json_and_base64():
    from x402escrow import parse_x_payment_header

    payload = {"client": "0xabc", "nonce": "0x01"}
    raw = json.dumps(payload)
    encoded = base64.b64encode(raw.encode()).decode().rstrip("=")

    assert parse_x_payment_header(raw) == payload
    assert parse_x_payment_header(encoded) == payload


def test_payment_authorization_normalization_and_amount_helpers():
    from x402escrow import normalize_payment_authorization, units_to_usdc, usdc_to_units

    auth = normalize_payment_authorization({
        "from": "0x0000000000000000000000000000000000000001",
        "value": "1230000",
        "valid_after": "0",
        "valid_before": "9999999999",
        "nonce": "0x" + "01" * 32,
        "v": "27",
        "r": "0x" + "02" * 32,
        "s": "0x" + "03" * 32,
    })

    assert auth["client"].endswith("0001")
    assert auth["maxAmount"] == 1230000
    assert usdc_to_units("1.230000") == 1230000
    assert units_to_usdc(1230000) == "1.230000"


def test_live_payment_route_settles_then_releases_with_mocks(monkeypatch, tmp_path):
    monkeypatch.setenv("X402ESCROW_LIVE", "true")
    bot_final = load_app(monkeypatch)
    bot_final.storage.storage_dir = tmp_path

    async def fake_audit_site(*args, **kwargs):
        return {
            "site_audit_id": "site_live_mock",
            "audit_type": "site",
            "mode": "multi_page",
            "root_url": "https://example.com/",
            "url": "https://example.com/",
            "timestamp": "2026-07-17T00:00:00",
            "score": 95,
            "grade": "A (Excellent)",
            "critical": 0,
            "warnings": 1,
            "info": 0,
            "summary": {"pages_audited": 2, "pages_failed": 0, "overall_assessment": "ok"},
            "pricing": {"actual_settled": "0.50", "refund": "0.00"},
            "repeated_issues": [],
            "worst_pages": [],
        }

    def fake_settle(auth, url):
        return {
            "mode": "live",
            "status": "settled",
            "escrow_id": "0x" + "11" * 32,
            "settle_tx": "0xsettle",
            "network": "base",
            "contract_address": "0x9562f50f73d8ee22276f13a18d051456d8d137a0",
        }

    def fake_release(escrow_id, amount):
        assert escrow_id == "0x" + "11" * 32
        assert amount == "0.50"
        return {"status": "released", "release_tx": "0xrelease", "escrow_id": escrow_id}

    monkeypatch.setattr(bot_final, "audit_site", fake_audit_site)
    monkeypatch.setattr(bot_final, "settle_x402escrow_authorization", fake_settle)
    monkeypatch.setattr(bot_final, "release_x402escrow", fake_release)

    client = TestClient(bot_final.app)
    payment = {
        "client": "0x0000000000000000000000000000000000000001",
        "maxAmount": "500000",
        "validAfter": "0",
        "validBefore": "9999999999",
        "nonce": "0x" + "01" * 32,
        "v": 27,
        "r": "0x" + "02" * 32,
        "s": "0x" + "03" * 32,
    }

    response = client.post(
        "/api/x402escrow/site-audit",
        headers={"X-PAYMENT": json.dumps(payment)},
        json={"url": "https://example.com", "max_pages": 2, "max_budget_usdc": "0.50"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["paid"] is True
    assert body["payment_mode"] == "x402escrow"
    assert body["escrow"]["release_tx"] == "0xrelease"
    assert bot_final.storage.get_pending_escrow("0x" + "11" * 32)["status"] == "released"
