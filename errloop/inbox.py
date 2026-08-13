from __future__ import annotations

import hmac
import hashlib
import json
import os
import re
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

STATUSES = {"active", "investigating", "fixed", "ignored", "fixed_notified"}
SEVERITIES = {"info", "warning", "error", "critical"}
LIFECYCLE_TASKS = {
    "sys.excepthook",
    "thread.FastAPI",
    "fastapi.server_thread",
    "telegram.run_polling",
    "process.main",
}
DEFAULT_DB_PATH = Path(os.getenv("ERRLOOP_DB_PATH", "audits/errloop.sqlite3"))
SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization|cookie|password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*([^\s&;,]+)"),
    re.compile(r"(?i)(bearer)\s+[a-z0-9._\-~+/]+=*"),
    re.compile(r"(?i)(x-payment)\s*[:=]\s*([^\s&;,]+)"),
    re.compile(r"0x[a-fA-F0-9]{64}"),
    re.compile(r"[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"),
]
MAX_TEXT = 1000


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> str:
    text = str(value or "")
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("0x"):
            text = pattern.sub("0x[REDACTED_PRIVATE_KEY_OR_HASH]", text)
        elif "bearer" in pattern.pattern.lower():
            text = pattern.sub("Bearer [REDACTED]", text)
        else:
            text = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    return text[:MAX_TEXT]


def _safe_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    safe = redact(url)
    return safe.split("?", 1)[0][:500]


def _normalize_route(route: Optional[str]) -> str:
    if not route:
        return "unknown"
    route = str(route).split("?", 1)[0]
    parts = []
    for part in route.split("/"):
        if not part:
            continue
        is_dynamic = (
            part.isdigit()
            or bool(re.fullmatch(r"[0-9a-fA-F]{6,}", part))
            or bool(re.fullmatch(r"[0-9a-fA-F-]{12,}", part) and any(ch.isdigit() for ch in part))
        )
        parts.append(":id" if is_dynamic else part)
    return ("/" + "/".join(parts))[:200]


def top_stack_frame(exc: Optional[BaseException]) -> Optional[str]:
    if exc is None or exc.__traceback__ is None:
        return None
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return None
    frame = frames[-1]
    filename = Path(frame.filename).name
    return f"{filename}:{frame.name}:{frame.lineno}"


def build_fingerprint(*, component: str = "app", route: str = "", task: str = "", error: Optional[BaseException] = None, error_type: str = "") -> str:
    name = error_type or (type(error).__name__ if error else "Error")
    frame = top_stack_frame(error) or "no-frame"
    frame_key = re.sub(r":\d+$", "", frame)
    stable = "|".join([component, _normalize_route(route or task), name, frame_key])
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:16]
    label = re.sub(r"[^a-z0-9_-]+", "-", f"{component}-{name}".lower()).strip("-")[:48]
    return f"{label}-{digest}"


def _connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS errloop_errors (
            fingerprint TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'active',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            occurrences INTEGER NOT NULL DEFAULT 0,
            service TEXT NOT NULL,
            environment TEXT NOT NULL,
            release TEXT,
            severity TEXT NOT NULL,
            route TEXT,
            task_name TEXT,
            job_name TEXT,
            sample_task_id TEXT,
            sample_url TEXT,
            error_type TEXT NOT NULL,
            last_error_message TEXT,
            top_stack_frame TEXT,
            metadata_json TEXT,
            ignored_reason TEXT,
            ignored_at TEXT
        )
    """)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(errloop_errors)").fetchall()}
    for name, ddl in {
        "ignored_reason": "ALTER TABLE errloop_errors ADD COLUMN ignored_reason TEXT",
        "ignored_at": "ALTER TABLE errloop_errors ADD COLUMN ignored_at TEXT",
    }.items():
        if name not in columns:
            conn.execute(ddl)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_errloop_status_last_seen ON errloop_errors(status, last_seen_at)")
    return conn


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    try:
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
    except json.JSONDecodeError:
        item["metadata"] = {}
    return item


def _classify_initial_status(error: Optional[BaseException], task_name: Optional[str], metadata: Optional[Dict[str, Any]]) -> tuple[str, Optional[str]]:
    message = str(error or "")
    if metadata and str(metadata.get("synthetic", "")).lower() in {"1", "true", "yes"}:
        return "ignored", "synthetic smoke test"
    if re.search(r"(?i)(synthetic|dedupe check|deploy smoke|errloop smoke)", message):
        return "ignored", "synthetic smoke test"
    if isinstance(error, (SystemExit, KeyboardInterrupt)) and (task_name in LIFECYCLE_TASKS or not task_name):
        return "ignored", "normal process lifecycle"
    return "active", None


def secure_compare(value: str, expected: str) -> bool:
    if not value or not expected:
        return False
    return hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


def record_error(
    *,
    fingerprint: Optional[str] = None,
    error: Optional[BaseException] = None,
    service: str = "accessibility-auditor",
    environment: Optional[str] = None,
    release: Optional[str] = None,
    severity: str = "error",
    route: Optional[str] = None,
    task_name: Optional[str] = None,
    job_name: Optional[str] = None,
    sample_task_id: Optional[str] = None,
    sample_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    severity = severity if severity in SEVERITIES else "error"
    environment = environment or os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "production"))
    release = release or os.getenv("APP_RELEASE", os.getenv("GIT_SHA", "local"))
    error_type = type(error).__name__ if error else "Error"
    ts = now_iso()
    initial_status, ignored_reason = _classify_initial_status(error, task_name or job_name, metadata)
    ignored_at = ts if initial_status == "ignored" else None
    fingerprint = fingerprint or build_fingerprint(component=service, route=route or "", task=task_name or job_name or "", error=error, error_type=error_type)
    safe_metadata = {str(k)[:80]: redact(v) for k, v in (metadata or {}).items()}
    params = {
        "fingerprint": fingerprint,
        "first_seen_at": ts,
        "last_seen_at": ts,
        "service": service[:120],
        "environment": environment[:80],
        "release": (release or "")[:120],
        "severity": severity,
        "route": _normalize_route(route),
        "task_name": (task_name or "")[:200] or None,
        "job_name": (job_name or "")[:200] or None,
        "sample_task_id": redact(sample_task_id)[:200] if sample_task_id else None,
        "sample_url": _safe_url(sample_url),
        "error_type": error_type[:120],
        "last_error_message": redact(error if error is not None else error_type),
        "top_stack_frame": top_stack_frame(error),
        "metadata_json": json.dumps(safe_metadata, ensure_ascii=False, sort_keys=True),
        "initial_status": initial_status,
        "ignored_reason": ignored_reason,
        "ignored_at": ignored_at,
    }
    with _connect() as conn:
        conn.execute("""
            INSERT INTO errloop_errors (
                fingerprint, status, first_seen_at, last_seen_at, occurrences, service, environment, release,
                severity, route, task_name, job_name, sample_task_id, sample_url, error_type,
                last_error_message, top_stack_frame, metadata_json, ignored_reason, ignored_at
            ) VALUES (
                :fingerprint, :initial_status, :first_seen_at, :last_seen_at, 1, :service, :environment, :release,
                :severity, :route, :task_name, :job_name, :sample_task_id, :sample_url, :error_type,
                :last_error_message, :top_stack_frame, :metadata_json, :ignored_reason, :ignored_at
            )
            ON CONFLICT(fingerprint) DO UPDATE SET
                status=CASE
                    WHEN errloop_errors.status IN ('fixed', 'fixed_notified') THEN excluded.status
                    WHEN errloop_errors.status='ignored' THEN 'ignored'
                    WHEN excluded.status='ignored' THEN 'ignored'
                    ELSE errloop_errors.status
                END,
                ignored_reason=COALESCE(errloop_errors.ignored_reason, excluded.ignored_reason),
                ignored_at=COALESCE(errloop_errors.ignored_at, excluded.ignored_at),
                last_seen_at=excluded.last_seen_at,
                occurrences=occurrences + 1,
                service=excluded.service,
                environment=excluded.environment,
                release=excluded.release,
                severity=excluded.severity,
                route=excluded.route,
                task_name=excluded.task_name,
                job_name=excluded.job_name,
                sample_task_id=excluded.sample_task_id,
                sample_url=excluded.sample_url,
                error_type=excluded.error_type,
                last_error_message=excluded.last_error_message,
                top_stack_frame=excluded.top_stack_frame,
                metadata_json=excluded.metadata_json
        """, params)
        row = conn.execute("SELECT * FROM errloop_errors WHERE fingerprint=?", (fingerprint,)).fetchone()
    return _row_to_dict(row)


def list_errors(*, status: str = "active", limit: int = 20, since: Optional[str] = None) -> list[Dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    clauses = []
    args: list[Any] = []
    if status != "all":
        clauses.append("status = ?")
        args.append(status)
    if since:
        clauses.append("last_seen_at >= ?")
        args.append(since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect() as conn:
        rows = conn.execute(f"SELECT * FROM errloop_errors {where} ORDER BY last_seen_at DESC LIMIT ?", (*args, limit)).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_error(fingerprint: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM errloop_errors WHERE fingerprint=?", (fingerprint,)).fetchone()
    return _row_to_dict(row) if row else None


def mark_error_status(fingerprint: str, status: str, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    ignored_reason = redact(reason)[:500] if reason else None
    ignored_at = now_iso() if status == "ignored" else None
    with _connect() as conn:
        conn.execute(
            """
            UPDATE errloop_errors
            SET status=?,
                ignored_reason=CASE WHEN ?='ignored' THEN COALESCE(?, ignored_reason) ELSE ignored_reason END,
                ignored_at=CASE WHEN ?='ignored' THEN COALESCE(?, ignored_at) ELSE ignored_at END
            WHERE fingerprint=?
            """,
            (status, status, ignored_reason, status, ignored_at, fingerprint),
        )
        row = conn.execute("SELECT * FROM errloop_errors WHERE fingerprint=?", (fingerprint,)).fetchone()
    return _row_to_dict(row) if row else None


def error_summary(*, limit: int = 10) -> Dict[str, Any]:
    with _connect() as conn:
        status_counts = {r["status"]: r["count"] for r in conn.execute("SELECT status, COUNT(*) AS count FROM errloop_errors GROUP BY status")}
        severity_counts = {r["severity"]: r["count"] for r in conn.execute("SELECT severity, COUNT(*) AS count FROM errloop_errors WHERE status='active' GROUP BY severity")}
        recent = conn.execute("SELECT * FROM errloop_errors ORDER BY last_seen_at DESC LIMIT ?", (max(1, min(int(limit), 50)),)).fetchall()
    return {"status_counts": status_counts, "active_severity_counts": severity_counts, "recent": [_row_to_dict(r) for r in recent]}
