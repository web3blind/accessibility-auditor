#!/usr/bin/env python3
"""Stable Errloop monitor output for Hermes cron monitor_script."""
from __future__ import annotations

import json
from errloop.inbox import list_errors


def main() -> None:
    rows = list_errors(status="active", limit=100)
    stable = [
        {
            "fingerprint": r["fingerprint"],
            "severity": r["severity"],
            "service": r["service"],
            "route": r.get("route"),
            "task_name": r.get("task_name"),
            "error_type": r["error_type"],
            "occurrences": r["occurrences"],
            "last_error_message": r.get("last_error_message"),
            "top_stack_frame": r.get("top_stack_frame"),
        }
        for r in sorted(rows, key=lambda x: x["fingerprint"])
    ]
    print(json.dumps(stable, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
