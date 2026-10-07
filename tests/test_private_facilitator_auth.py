import asyncio
import pytest
from x402_facilitator_auth import facilitator_config

@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for key in ('X402_PRIVATE_FACILITATOR_TOKEN', 'X402_CIRCLE_API_KEY', 'X402_CIRCLE_SELLER_PRIVATE_KEY'):
        monkeypatch.delenv(key, raising=False)

def test_private_token(monkeypatch):
    token = 'unit-test-token-not-secret-123456789'
    monkeypatch.setenv('X402_PRIVATE_FACILITATOR_TOKEN', token)
    cfg = facilitator_config('http://127.0.0.1:3402')
    assert cfg.http_client.headers['authorization'] == 'Bearer ' + token
    assert cfg.http_client.follow_redirects is False
    asyncio.run(cfg.http_client.aclose())

@pytest.mark.parametrize('url', ['https://example.com', 'http://localhost:3402', 'http://127.0.0.1:3402/other'])
def test_private_token_wrong_origin(monkeypatch, url):
    monkeypatch.setenv('X402_PRIVATE_FACILITATOR_TOKEN', 'unit-test-token-not-secret-123456789')
    with pytest.raises(ValueError):
        facilitator_config(url)

def test_private_token_circle_conflict(monkeypatch):
    monkeypatch.setenv('X402_PRIVATE_FACILITATOR_TOKEN', 'unit-test-token-not-secret-123456789')
    monkeypatch.setenv('X402_CIRCLE_API_KEY', 'test-key')
    with pytest.raises(ValueError):
        facilitator_config('http://127.0.0.1:3402')
