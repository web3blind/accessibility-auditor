#!/bin/bash
source /root/.hermes/agents/accessibility-auditor/venv/bin/activate
cd /root/.hermes/agents/accessibility-auditor
exec python3 -u bot_final.py >> bot.log 2>&1
