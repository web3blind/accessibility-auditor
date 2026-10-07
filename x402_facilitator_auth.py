"""Optional Circle authentication at the serialized HTTP request boundary.

Protocol: https://developers.circle.com/facilitator-service/sign-seller-proof
API key and seller proof are alternative modes, never combined. No signing key
is needed for production API-key mode. Other facilitators remain unauthenticated.
"""

import base64
import json
import os
import re
import secrets
import time
from urllib.parse import urlsplit

import httpx


_CIRCLE_HOSTS = {"api.circle.com", "api-sandbox.circle.com"}
_CIRCLE_PATH = "/v1/facilitator/x402"
_SELLER_TYPES = {
    "SellerRequest": [
        {"name": "purpose", "type": "string"},
        {"name": "method", "type": "string"},
        {"name": "bodyHash", "type": "bytes32"},
        {"name": "network", "type": "string"},
        {"name": "payTo", "type": "address"},
        {"name": "nonce", "type": "bytes32"},
        {"name": "issuedAt", "type": "uint64"},
        {"name": "expiresAt", "type": "uint64"},
    ]
}


class CircleFacilitatorAuth(httpx.Auth):
    """Sign exactly the bytes httpx will send, not a reserialized SDK object."""

    requires_request_body = True

    def __init__(self, url, *, api_key="", seller_private_key=""):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in _CIRCLE_HOSTS
                or parsed.port not in (None, 443) or parsed.username or parsed.password
                or parsed.path.rstrip("/") != _CIRCLE_PATH or parsed.query or parsed.fragment):
            raise ValueError("Circle authentication requires an official Circle x402 URL")
        if bool(api_key) == bool(seller_private_key):
            raise ValueError("Configure exactly one Circle authentication mode")
        if api_key and (api_key.strip() != api_key or any(ord(c) < 32 or ord(c) > 126 for c in api_key)):
            raise ValueError("Invalid Circle API key format")
        self._host = parsed.hostname
        self._api_key = api_key
        self._account = None
        if seller_private_key:
            from eth_account import Account

            try:
                self._account = Account.from_key(seller_private_key)
            except Exception:
                raise ValueError("Invalid Circle seller signing key") from None

    def auth_flow(self, request):
        # Never leak either credential to another host/path, even with a reused client.
        if (request.url.scheme != "https" or request.url.host != self._host
                or request.url.port not in (None, 443)
                or request.url.path not in {_CIRCLE_PATH + suffix for suffix in ("/verify", "/settle", "/supported")}):
            raise ValueError("Circle authenticated client cannot call this URL")
        if request.url.path.endswith("/supported"):
            # Circle's capability discovery is public and needs no seller proof.
            yield request
            return
        if request.method != "POST":
            raise ValueError("Circle verify and settle require POST")
        if "Authorization" in request.headers or "Facilitator-Seller-Proof" in request.headers:
            raise ValueError("Mixed Circle authentication headers are not allowed")
        if self._api_key:
            request.headers["Authorization"] = "Bearer " + self._api_key
        else:
            request.headers["Facilitator-Seller-Proof"] = self._seller_proof(request)
        yield request

    def _seller_proof(self, request):
        from eth_account.messages import encode_typed_data
        from eth_utils import keccak

        try:
            body = json.loads(request.content)
            requirements = body["paymentRequirements"]
            network, pay_to = requirements["network"], requirements["payTo"]
            if body["x402Version"] != 2 or not re.fullmatch(r"eip155:[1-9][0-9]*", network):
                raise ValueError
            if pay_to.lower() != self._account.address.lower():
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ValueError("Circle seller proof requires x402 v2 and the signing account as payTo") from None
        issued_at = int(time.time())
        envelope = {
            "version": 1,
            "network": network,
            "payTo": pay_to,
            "nonce": "0x" + secrets.token_hex(32),
            "issuedAt": issued_at,
            "expiresAt": issued_at + 300,
        }
        message = {
            "purpose": request.url.path.rsplit("/", 1)[-1],
            "method": request.method,
            "bodyHash": keccak(request.content),
            **{key: value for key, value in envelope.items() if key != "version"},
        }
        signable = encode_typed_data(
            domain_data={
                "name": "Circle Facilitator Seller Request",
                "version": "1",
                "chainId": int(network.split(":")[1]),
            },
            message_types=_SELLER_TYPES,
            message_data=message,
        )
        envelope["signature"] = "0x" + self._account.sign_message(signable).signature.hex()
        return base64.urlsafe_b64encode(json.dumps(envelope, separators=(",", ":")).encode()).decode().rstrip("=")


def facilitator_config(url, *, user_agent=None, timeout=180.0):
    """Create the installed SDK config; optional secrets are read only from env."""
    from x402.http import FacilitatorConfig

    api_key = os.getenv("X402_CIRCLE_API_KEY", "")
    seller_key = os.getenv("X402_CIRCLE_SELLER_PRIVATE_KEY", "")
    auth = CircleFacilitatorAuth(url, api_key=api_key, seller_private_key=seller_key) if api_key or seller_key else None
    private_token = os.getenv("X402_PRIVATE_FACILITATOR_TOKEN", "")
    if private_token:
        parsed = urlsplit(url)
        if api_key or seller_key:
            raise ValueError("Private facilitator and Circle authentication cannot be combined")
        if url.rstrip("/") != "http://127.0.0.1:3402" or len(private_token) < 32 or any(ord(c) < 33 or ord(c) > 126 for c in private_token):
            raise ValueError("Private facilitator token requires the approved loopback endpoint")
    headers = {"user-agent": user_agent} if user_agent else {}
    if private_token:
        headers["Authorization"] = "Bearer " + private_token
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=15.0),
        headers=headers,
        auth=auth,
        follow_redirects=False,
    )
    return FacilitatorConfig(url=url, timeout=timeout, http_client=client)


def supported_network_keys(networks, requested, supported):
    """Filter against exact v2 capabilities, including an authoritative empty set."""
    kinds = supported.get("kinds", []) if isinstance(supported, dict) else supported.kinds
    accepted = set()
    for kind in kinds:
        def field(name, default=None):
            return kind.get(name, default) if isinstance(kind, dict) else getattr(kind, name, default)
        if field("scheme") == "exact" and field("x402_version", field("x402Version")) == 2:
            accepted.add(str(field("network")))
    return [key for key in requested if networks.get(key, {}).get("evm_network") in accepted]
