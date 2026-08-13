import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def reload_inbox(monkeypatch, tmp_path):
    monkeypatch.setenv("ERRLOOP_DB_PATH", str(tmp_path / "errloop.sqlite3"))
    import errloop.inbox as inbox
    return importlib.reload(inbox)


def test_errloop_redacts_dedupes_and_ignores_synthetic(tmp_path, monkeypatch):
    inbox = reload_inbox(monkeypatch, tmp_path)

    try:
        raise RuntimeError("failed token=supersecret EVM_PRIVATE_KEY=0x" + "a" * 64)
    except RuntimeError as exc:
        first = inbox.record_error(error=exc, route="/api/audit/abc123", sample_url="https://example.com/?token=leak")
        second = inbox.record_error(error=exc, route="/api/audit/def456", sample_url="https://example.com/?token=leak")

    assert first["fingerprint"] == second["fingerprint"]
    assert second["occurrences"] == 2
    assert second["status"] == "active"
    assert "[REDACTED]" in second["last_error_message"]
    assert "supersecret" not in second["last_error_message"]
    assert "a" * 64 not in second["last_error_message"]
    assert second["sample_url"] == "https://example.com/"

    synthetic = inbox.record_error(error=ValueError("dedupe check token=secret"), route="/api/audit/abc123")
    assert synthetic["status"] == "ignored"
    assert synthetic["ignored_reason"] == "synthetic smoke test"


def test_lifecycle_system_exit_is_ignored(tmp_path, monkeypatch):
    inbox = reload_inbox(monkeypatch, tmp_path)
    item = inbox.record_error(error=SystemExit(1), task_name="thread.FastAPI", severity="critical")
    assert item["status"] == "ignored"
    assert item["ignored_reason"] == "normal process lifecycle"


def load_app(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("ERRLOOP_DB_PATH", str(tmp_path / "errloop.sqlite3"))
    monkeypatch.setenv("ERRLOOP_API_TOKEN", "agent-secret")
    if "errloop.inbox" in sys.modules:
        importlib.reload(sys.modules["errloop.inbox"])
    if "bot_final" in sys.modules:
        return importlib.reload(sys.modules["bot_final"])
    return importlib.import_module("bot_final")


def test_agent_error_api_is_protected_and_safe(monkeypatch, tmp_path):
    bot_final = load_app(monkeypatch, tmp_path)
    client = TestClient(bot_final.app)

    try:
        raise ValueError("boom password=hunter2")
    except ValueError as exc:
        item = bot_final.errloop_record_error(error=exc, route="/api/test", service="accessibility-auditor")

    assert client.get("/api/agent/errors/summary").status_code == 403

    headers = {"Authorization": "Bearer agent-secret"}
    summary = client.get("/api/agent/errors/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["status_counts"]["active"] == 1

    details = client.get(f"/api/agent/errors/{item['fingerprint']}", headers=headers)
    assert details.status_code == 200
    body = details.json()
    assert body["fingerprint"] == item["fingerprint"]
    assert "hunter2" not in body["last_error_message"]

    marked = client.post(
        f"/api/agent/errors/{item['fingerprint']}/status",
        headers=headers,
        json={"status": "ignored", "reason": "test cleanup"},
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "ignored"
    assert marked.json()["ignored_reason"] == "test cleanup"


def test_agent_error_api_returns_404_when_token_not_configured(monkeypatch, tmp_path):
    bot_final = load_app(monkeypatch, tmp_path)
    monkeypatch.delenv("ERRLOOP_API_TOKEN", raising=False)
    client = TestClient(bot_final.app)
    assert client.get("/api/agent/errors/summary").status_code == 404
