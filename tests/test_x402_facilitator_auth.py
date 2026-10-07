"""Local-only contract tests: ephemeral keys, mock transport, real x402 SDK."""
import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import sys

import httpx
import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from x402.http import HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.schemas import SupportedResponse
from x402.server import x402ResourceServer
from x402_facilitator_auth import CircleFacilitatorAuth, facilitator_config, supported_network_keys

URL = "https://api.circle.com/v1/facilitator/x402"
NETWORK = "eip155:5042002"
ASSET = "0x3600000000000000000000000000000000000000"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("X402_CIRCLE_API_KEY", "X402_CIRCLE_SELLER_PRIVATE_KEY", "X402_FACILITATOR_DEBUG"):
        monkeypatch.delenv(name, raising=False)


def body_for(account):
    requirements = {
        "scheme": "exact", "network": NETWORK, "asset": ASSET,
        "amount": "100000", "payTo": account.address, "maxTimeoutSeconds": 300,
        "extra": {"name": "USDC", "version": "2"},
    }
    # The transport validates seller auth, not the fake buyer authorization.
    payload = {"x402Version": 2, "accepted": requirements, "payload": {"signature": "0x", "authorization": {}}}
    return {"x402Version": 2, "paymentPayload": payload, "paymentRequirements": requirements}


def decode_proof(header):
    return json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))


def recover_proof(request, envelope, *, purpose=None, content=None):
    # Independently reconstruct the documented EIP-712 contract.
    types = {"SellerRequest": [
        {"name": "purpose", "type": "string"}, {"name": "method", "type": "string"},
        {"name": "bodyHash", "type": "bytes32"}, {"name": "network", "type": "string"},
        {"name": "payTo", "type": "address"}, {"name": "nonce", "type": "bytes32"},
        {"name": "issuedAt", "type": "uint64"}, {"name": "expiresAt", "type": "uint64"},
    ]}
    message = {"purpose": purpose or request.url.path.rsplit("/", 1)[-1], "method": request.method,
               "bodyHash": keccak(request.content if content is None else content),
               **{k: envelope[k] for k in ("network", "payTo", "nonce", "issuedAt", "expiresAt")}}
    signable = encode_typed_data(
        domain_data={"name": "Circle Facilitator Seller Request", "version": "1",
                     "chainId": int(envelope["network"].split(":")[1])},
        message_types=types, message_data=message,
    )
    return Account.recover_message(signable, signature=envelope["signature"])


@pytest.mark.parametrize("mode", ["none", "api_key", "proof"])
def test_real_sdk_verify_settle_and_pending(monkeypatch, mode):
    account = Account.create()
    api_key = "unit-test-only-not-a-circle-credential"
    if mode == "api_key":
        monkeypatch.setenv("X402_CIRCLE_API_KEY", api_key)
    if mode == "proof":
        monkeypatch.setenv("X402_CIRCLE_SELLER_PRIVATE_KEY", account.key.hex())
    body = body_for(account)
    seen = []

    def handle(request):
        seen.append(request)
        assert json.loads(request.content) == body
        assert request.headers["user-agent"] == "auditor-test"
        if mode == "api_key":
            assert request.headers.get("authorization") == "Bearer " + api_key
            assert "Facilitator-Seller-Proof" not in request.headers
        elif mode == "proof":
            assert "authorization" not in request.headers
            proof = decode_proof(request.headers["Facilitator-Seller-Proof"])
            assert recover_proof(request, proof) == account.address
            assert recover_proof(request, proof, content=request.content + b" ") != account.address
            assert recover_proof(request, proof, purpose="status") != account.address
            assert proof["version"] == 1 and proof["expiresAt"] - proof["issuedAt"] == 300
            assert len(bytes.fromhex(proof["nonce"][2:])) == 32
        else:
            assert "authorization" not in request.headers and "Facilitator-Seller-Proof" not in request.headers
        result = {"isValid": True, "payer": account.address} if request.url.path.endswith("/verify") else {
            "success": False, "errorReason": "settlement_pending", "payer": account.address,
            "transaction": "", "network": NETWORK,
            "extensions": {"settlement-status": {"status": "pending", "paymentId": "unit-test-payment"}},
        }
        return httpx.Response(200, json=result)

    async def run():
        target = "http://127.0.0.1:4030/facilitator" if mode == "none" else URL
        config = facilitator_config(target, user_agent="auditor-test", timeout=42)
        assert config.http_client.timeout.read == 42 and config.http_client.timeout.connect == 15
        assert not config.http_client.follow_redirects
        # Same real config/auth boundary with an in-memory HTTP transport.
        config.http_client._transport = httpx.MockTransport(handle)
        client = HTTPFacilitatorClient(config)
        try:
            payload = json.dumps(body["paymentPayload"]).encode()
            requirements = json.dumps(body["paymentRequirements"]).encode()
            assert (await client.verify_from_bytes(payload, requirements)).is_valid
            result = await client.settle_from_bytes(payload, requirements)
            assert result.success is False and result.error_reason == "settlement_pending"
        finally:
            await config.http_client.aclose()
    asyncio.run(run())
    assert len(seen) == 2
    if mode == "proof":
        assert decode_proof(seen[0].headers["Facilitator-Seller-Proof"])["nonce"] != decode_proof(seen[1].headers["Facilitator-Seller-Proof"])["nonce"]


@pytest.mark.parametrize("url", ["https://example.com/facilitator", "http://api.circle.com/v1/facilitator/x402",
    "https://api.circle.com.evil.test/v1/facilitator/x402", URL + "?key=x", URL + "/wrong", "https://user@api.circle.com/v1/facilitator/x402"])
def test_credentials_refused_outside_official_url(monkeypatch, url):
    monkeypatch.setenv("X402_CIRCLE_API_KEY", "unit-test-credential")
    with pytest.raises(ValueError, match="official Circle"):
        facilitator_config(url)


def test_mixed_and_invalid_modes_are_redacted(monkeypatch):
    secret = "unit-test-private-not-a-key"
    monkeypatch.setenv("X402_CIRCLE_SELLER_PRIVATE_KEY", secret)
    with pytest.raises(ValueError) as caught:
        facilitator_config(URL)
    assert secret not in str(caught.value)
    monkeypatch.setenv("X402_CIRCLE_API_KEY", "unit-test-key")
    with pytest.raises(ValueError, match="exactly one"):
        facilitator_config(URL)


def test_proof_rejects_mismatched_pay_to_and_v1():
    account = Account.create()
    auth = CircleFacilitatorAuth(URL, seller_private_key=account.key.hex())
    body = body_for(Account.create())
    for version in (1, 2):
        body["x402Version"] = version
        request = httpx.Request("POST", URL + "/verify", json=body)
        with pytest.raises(ValueError, match="signing account"):
            list(auth.auth_flow(request))


def test_proof_hashes_exact_noncanonical_body():
    account = Account.create()
    auth = CircleFacilitatorAuth(URL, seller_private_key=account.key.hex())
    raw = json.dumps(body_for(account), indent=4).encode() + b"\n"
    request = httpx.Request("POST", URL + "/settle", content=raw)
    list(auth.auth_flow(request))
    proof = decode_proof(request.headers["Facilitator-Seller-Proof"])
    assert recover_proof(request, proof) == account.address
    assert request.content == raw


def test_no_proof_for_public_supported_and_no_cross_origin_leak():
    auth = CircleFacilitatorAuth(URL, seller_private_key=Account.create().key.hex())
    request = httpx.Request("GET", URL + "/supported")
    list(auth.auth_flow(request))
    assert "Facilitator-Seller-Proof" not in request.headers
    with pytest.raises(ValueError, match="cannot call"):
        list(auth.auth_flow(httpx.Request("POST", "https://other.test/verify", json={})))
    with pytest.raises(ValueError, match="Mixed"):
        list(auth.auth_flow(httpx.Request("POST", URL + "/verify", headers={"Authorization": "Bearer unit-test"}, json={})))


def test_supported_filter_is_exact_v2_and_empty_is_authoritative():
    networks = {"arc": {"evm_network": NETWORK}, "base": {"evm_network": "eip155:84532"}}
    supported = {"kinds": [{"scheme": "exact", "x402Version": 2, "network": NETWORK},
                            {"scheme": "exact", "x402Version": 1, "network": "eip155:84532"}]}
    assert supported_network_keys(networks, ["arc", "base"], supported) == ["arc"]
    assert supported_network_keys(networks, ["arc", "base"], SupportedResponse.model_validate(supported)) == ["arc"]
    assert supported_network_keys(networks, ["arc"], {"kinds": []}) == []
    supported["kinds"][0]["scheme"] = "other"
    assert supported_network_keys(networks, ["arc"], supported) == []


@pytest.mark.parametrize("supported", [True, False])
def test_primary_setup_with_real_sdk_and_payment_offers(monkeypatch, supported):
    """Execute the actual setup block without Telegram, files or real network."""
    monkeypatch.setenv("X402_FACILITATOR_URL", URL)
    monkeypatch.setenv("X402_FACILITATOR_NETWORKS", "arc_testnet,arc_mainnet,base_sepolia")
    monkeypatch.setenv("X402_SERVER_ADDRESS", Account.create().address)
    monkeypatch.delenv("EVM_SERVER_ADDRESS", raising=False)
    monkeypatch.setenv("X402_CIRCLE_API_KEY", "unit-test-only")
    response = {"kinds": [{"scheme": "exact", "x402Version": 2, "network": NETWORK}] if supported else [],
                "extensions": [], "signers": {}}
    monkeypatch.setattr(HTTPFacilitatorClient, "_get_sync_client", lambda self: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))))
    app = FastAPI()
    ns = dict(os=os, logging=logging, __name__="test_payment_setup", X402_ENABLED=True,
              HTTPFacilitatorClient=HTTPFacilitatorClient, x402ResourceServer=x402ResourceServer,
              ExactEvmServerScheme=ExactEvmServerScheme, PaymentOption=PaymentOption,
              RouteConfig=RouteConfig, PaymentMiddlewareASGI=PaymentMiddlewareASGI, app=app)
    source = (Path(__file__).resolve().parents[1] / "bot_final.py").read_text()
    setup = source.split("# x402 setup - payment middleware for /api/audit/paid", 1)[1].split("@app.exception_handler(Exception)", 1)[0]
    exec(compile(setup, "bot_final.py:x402-setup", "exec"), ns)
    try:
        assert ns["X402_ENABLED"] is supported
        if not supported:
            assert not app.user_middleware
            return
        assert ns["_x402_facilitator_networks"] == ["arc_testnet"]
        @app.post("/api/audit/paid")
        async def paid():
            pytest.fail("Unpaid call must not reach paid handler")
        with TestClient(app) as client:
            result = client.post("/api/audit/paid", json={"url": "https://example.com"})
        assert result.status_code == 402
        required = json.loads(base64.b64decode(result.headers["payment-required"]))
        offer = required["accepts"][0]
        assert len(required["accepts"]) == 1
        assert offer["network"] == NETWORK and offer["amount"] == "100000"
        assert offer["asset"] == ASSET and offer["payTo"] == ns["_X402_SERVER_ADDRESS"]
        assert offer["extra"]["name"] == "USDC" and offer["extra"]["version"] == "2"
        assert "unit-test-only" not in result.text
    finally:
        asyncio.run(ns["_x402_facilitator"]._get_async_client().aclose())


@pytest.mark.parametrize("filename,name", [("bot_final.py", "submit_paid_audit"), ("api.py", "create_paid_audit")])
def test_paid_handlers_fail_closed_when_setup_is_disabled(filename, name):
    import ast
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from types import SimpleNamespace

    source = (Path(__file__).resolve().parents[1] / filename).read_text()
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.AsyncFunctionDef) and node.name == name)
    function.decorator_list = []
    ns = {"X402_ENABLED": False, "AuditRequest": object, "JSONResponse": JSONResponse, "HTTPException": HTTPException}
    exec(compile(ast.Module(body=[function], type_ignores=[]), filename, "exec"), ns)
    if filename == "api.py":
        with pytest.raises(HTTPException) as caught:
            asyncio.run(ns[name](SimpleNamespace(url="https://example.com")))
        assert caught.value.status_code == 503
    else:
        response = asyncio.run(ns[name](SimpleNamespace(url="https://example.com")))
        assert response.status_code == 503
        assert json.loads(response.body) == {"error": "Payment service unavailable"}


@pytest.mark.parametrize("base_url", [URL, "https://api-sandbox.circle.com/v1/facilitator/x402"])
def test_api_key_scoped_to_each_circle_environment(base_url):
    auth = CircleFacilitatorAuth(base_url, api_key="unit-test-only")
    request = httpx.Request("POST", base_url + "/settle", json={})
    list(auth.auth_flow(request))
    assert request.headers["Authorization"] == "Bearer unit-test-only"
    assert "Facilitator-Seller-Proof" not in request.headers
