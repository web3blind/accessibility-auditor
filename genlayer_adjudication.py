#!/usr/bin/env python3
"""GenLayer adjudication bridge for Accessibility Auditor.

The web service can run without GenLayer credentials. In that case this module
returns a deterministic local preview with the same public shape. When
GENLAYER_ENABLED=true and a contract address is configured, it calls the
GenLayer CLI against the selected network and reads the contract decision back.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

DEFAULT_CONTRACT_ADDRESS = "0x188C501e7bc1678C1bB7af2cf19A702194b9FB33"
DEFAULT_NETWORK = "testnet-bradbury"
DEFAULT_CLI_WORKDIR = "/home/assistent/ai-projects/retro-drops-generator/genlayer-accessibility-court"
DEFAULT_EXPLORER_BASE_URL = "https://explorer-bradbury.genlayer.com"
DEFAULT_CLAIM = (
    "The audited web page is accessible for blind users and can be used "
    "with keyboard navigation and screen readers without critical blockers."
)

VALID_VERDICTS = {"supported", "partially_supported", "not_supported", "insufficient_evidence"}


def build_evidence(report: Dict[str, Any], report_url: Optional[str] = None) -> Dict[str, Any]:
    """Build the compact evidence object sent to GenLayer."""
    findings = report.get("findings") or []
    if not findings:
        findings = []
        for category, items in (report.get("issues_by_category") or {}).items():
            for item in items:
                findings.append({"category": category, **item})

    top_findings = report.get("top_findings") or findings[:8]
    manual_checks = report.get("manual_checks") or [
        "Screen reader behavior was not manually verified.",
        "Keyboard focus order needs manual verification.",
        "Dynamic states, modals, menus, and form errors need manual verification.",
    ]

    return {
        "schema_version": "genlayer-accessibility-evidence/1.0",
        "source": "BlindDev Accessibility Auditor",
        "url": report.get("url"),
        "report_url": report_url,
        "timestamp": report.get("timestamp"),
        "score": report.get("score"),
        "grade": report.get("grade"),
        "issue_counts": {
            "total": report.get("total_issues", 0),
            "critical": report.get("critical", 0),
            "warnings": report.get("warnings", 0),
            "info": report.get("info", 0),
        },
        "summary": report.get("summary", {}),
        "top_findings": top_findings[:8],
        "manual_checks": manual_checks,
        "proof": {
            "report_url": report_url,
            "audit_schema": report.get("schema_id"),
        },
    }


def _local_decision(evidence: Dict[str, Any]) -> Dict[str, Any]:
    counts = evidence.get("issue_counts") or {}
    score = evidence.get("score")
    critical = int(counts.get("critical") or 0)
    warnings = int(counts.get("warnings") or 0)
    manual_checks = evidence.get("manual_checks") or []

    if score is None:
        verdict = "insufficient_evidence"
        confidence = 50
        rationale = "The evidence does not include a numeric accessibility score, so the accessibility claim cannot be adjudicated reliably."
    elif critical > 0 or score < 60:
        verdict = "not_supported"
        confidence = 85 if critical else 75
        rationale = "The accessibility claim is not supported: the audit evidence contains critical blockers or a low score."
    elif warnings > 0 or score < 85:
        verdict = "partially_supported"
        confidence = 72
        rationale = "The claim is only partially supported: no critical blocker dominates the evidence, but warnings or a medium score still require fixes and manual verification."
    else:
        verdict = "supported"
        confidence = 70
        rationale = "The automated evidence supports the claim, but final confidence still depends on manual screen-reader and keyboard testing."

    missing = []
    if manual_checks:
        missing.append("Manual assistive-technology verification is still required.")
    if not evidence.get("proof", {}).get("report_url"):
        missing.append("A public report URL or immutable proof should be attached.")

    return {
        "verdict": verdict,
        "confidence": confidence,
        "rationale_en": rationale,
        "key_findings": [
            f"Score: {score}/100" if score is not None else "Score is missing",
            f"Critical issues: {critical}",
            f"Warnings: {warnings}",
        ],
        "missing_evidence": missing,
    }


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    for match in re.finditer(r"\{[\s\S]*\}", text):
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def _validate_decision(data: Dict[str, Any]) -> Dict[str, Any]:
    verdict = data.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise ValueError(f"Invalid GenLayer verdict: {verdict!r}")
    confidence = data.get("confidence")
    if not isinstance(confidence, int) or not 0 <= confidence <= 100:
        raise ValueError(f"Invalid GenLayer confidence: {confidence!r}")
    rationale = data.get("rationale_en") or data.get("rationale_ru") or data.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("GenLayer decision is missing rationale")
    data["rationale_en"] = rationale.strip()
    data.setdefault("key_findings", [])
    data.setdefault("missing_evidence", [])
    return data


def _resolve_npx() -> Optional[str]:
    """Resolve npx in cron/aaPanel environments where PATH may be minimal."""
    npx = shutil.which("npx")
    if npx:
        return npx
    for candidate in (
        "/www/server/nodejs/v22.22.1/bin/npx",
        "/www/server/nodejs/v20.11.1/bin/npx",
        "/usr/local/bin/npx",
        "/usr/bin/npx",
    ):
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _load_genlayer_password(cli_workdir: str) -> Optional[str]:
    """Load the GenLayer keystore password without logging or exposing it."""
    password = os.getenv("GENLAYER_KEYSTORE_PASSWORD") or os.getenv("GENLAYER_DEMO_KEYSTORE_PASSWORD")
    if password:
        return password

    env_path = os.path.join(cli_workdir, ".env")
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "GENLAYER_DEMO_KEYSTORE_PASSWORD":
                    return value.strip().strip('"').strip("'")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return None


def _explorer_url(path: str, value: str) -> str:
    base = os.getenv("GENLAYER_EXPLORER_BASE_URL", DEFAULT_EXPLORER_BASE_URL).rstrip("/")
    return f"{base}/{path}/{value}"


def _fetch_latest_contract_transaction(contract_address: str) -> Optional[Dict[str, Any]]:
    """Best-effort explorer lookup for the newest transaction touching the contract."""
    if not contract_address or contract_address == "n/a":
        return None

    base = os.getenv("GENLAYER_EXPLORER_BASE_URL", DEFAULT_EXPLORER_BASE_URL).rstrip("/")
    query = urllib.parse.urlencode({"address": contract_address, "page": 1, "page_size": 1})
    request = urllib.request.Request(
        f"{base}/api/v1/transactions?{query}",
        headers={"User-Agent": "hexdrive-accessibility-auditor/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    transactions = data.get("transactions") or []
    if not transactions:
        return None
    tx = transactions[0]
    tx_hash = tx.get("hash")
    rollup_hash = tx.get("rollup_transaction_hash")
    return {
        "transaction_hash": tx_hash,
        "transaction_url": _explorer_url("tx", tx_hash) if tx_hash else None,
        "rollup_transaction_hash": rollup_hash,
        "rollup_transaction_url": (
            "https://zksync-os-testnet-genlayer.explorer.zksync.dev/tx/" + rollup_hash
            if rollup_hash else None
        ),
        "contract_url": _explorer_url("address", contract_address),
        "explorer_status": tx.get("status"),
        "submission_timestamp": tx.get("submission_timestamp"),
        "finalization_timestamp": tx.get("finalization_timestamp"),
    }


async def adjudicate_report(
    report: Dict[str, Any],
    *,
    audit_id: Optional[str] = None,
    report_url: Optional[str] = None,
    claim: str = DEFAULT_CLAIM,
) -> Dict[str, Any]:
    """Return a GenLayer adjudication block for an audit report."""
    evidence = build_evidence(report, report_url=report_url)
    case_id = audit_id or f"audit-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    network = os.getenv("GENLAYER_NETWORK", DEFAULT_NETWORK)
    contract_address = os.getenv("GENLAYER_ACCESSIBILITY_CONTRACT", DEFAULT_CONTRACT_ADDRESS)
    cli_workdir = os.getenv("GENLAYER_CLI_WORKDIR", DEFAULT_CLI_WORKDIR)
    enabled = os.getenv("GENLAYER_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    base = {
        "case_id": case_id,
        "claim": claim,
        "network": network,
        "contract_address": contract_address,
        "contract_url": _explorer_url("address", contract_address) if contract_address else None,
        "evidence": evidence,
    }

    if not enabled:
        return {
            **base,
            "status": "local_preview",
            "note": "GENLAYER_ENABLED is false; this is a deterministic local preview with the same output shape.",
            "decision": _local_decision(evidence),
        }

    npx_path = _resolve_npx()
    if not npx_path:
        return {
            **base,
            "status": "error",
            "error": "npx is not available; cannot call GenLayer CLI from this service environment.",
            "decision": _local_decision(evidence),
        }

    evidence_json = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
    subprocess_env = os.environ.copy()
    npx_dir = os.path.dirname(npx_path)
    subprocess_env["PATH"] = npx_dir + os.pathsep + subprocess_env.get("PATH", "")
    try:
        # The service deliberately uses the CLI as an integration boundary so we do
        # not add a fragile Python SDK dependency to the production bot process.
        set_network = await asyncio.create_subprocess_exec(
            npx_path, "genlayer", "network", "set", network,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cli_workdir,
            env=subprocess_env,
        )
        await asyncio.wait_for(set_network.communicate(), timeout=60)

        password = _load_genlayer_password(cli_workdir)
        stdin = asyncio.subprocess.PIPE if password else None
        write_proc = await asyncio.create_subprocess_exec(
            npx_path, "genlayer", "write",
            contract_address,
            "adjudicate_claim",
            "--args", case_id, evidence_json, claim,
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cli_workdir,
            env=subprocess_env,
        )
        write_input = f"{password}\n".encode("utf-8") if password else None
        write_out, write_err = await asyncio.wait_for(write_proc.communicate(write_input), timeout=240)
        write_text = (write_out + write_err).decode("utf-8", errors="replace")
        if write_proc.returncode != 0:
            raise RuntimeError(write_text[-2000:])

        call_proc = await asyncio.create_subprocess_exec(
            npx_path, "genlayer", "call",
            contract_address,
            "get_last_decision_json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cli_workdir,
            env=subprocess_env,
        )
        call_out, call_err = await asyncio.wait_for(call_proc.communicate(), timeout=120)
        call_text = (call_out + call_err).decode("utf-8", errors="replace")
        if call_proc.returncode != 0:
            raise RuntimeError(call_text[-2000:])
        parsed = _extract_json(call_text)
        if parsed is None:
            raise RuntimeError(f"Could not parse GenLayer decision JSON: {call_text[-1000:]}")
        tx_info = await asyncio.to_thread(_fetch_latest_contract_transaction, contract_address)
        return {
            **base,
            "status": "accepted",
            "write_output": write_text[-2000:],
            "decision": _validate_decision(parsed),
            **(tx_info or {}),
        }
    except Exception as exc:
        return {
            **base,
            "status": "error",
            "error": str(exc)[:2000],
            "decision": _local_decision(evidence),
        }
