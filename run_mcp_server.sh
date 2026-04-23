#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -d mcp_venv ]]; then
  python3 -m venv mcp_venv
  source mcp_venv/bin/activate
  pip install -r mcp-requirements.txt
  python -m playwright install chromium
else
  source mcp_venv/bin/activate
fi

exec python mcp_server.py
