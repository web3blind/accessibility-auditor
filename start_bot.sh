#!/bin/bash
# Start Accessibility Auditor Bot with venv activated

cd /root/.hermes/agents/accessibility-auditor

# Activate virtual environment
source venv/bin/activate

# Start bot process
nohup python3 -u -B bot_final.py >> bot.log 2>&1 &

# Save PID
echo $! > bot.pid

echo "Bot started with PID: $!"
