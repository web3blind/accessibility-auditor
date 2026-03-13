#!/bin/bash
# Start bot with environment from .env

cd ~/.hermes/agents/accessibility-auditor

# Load .env file
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Start bot
python3 -u -B bot_final.py &
echo $! > bot.pid

echo "✅ Bot started with PID $(cat bot.pid)"
