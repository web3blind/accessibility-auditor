#!/bin/bash
cd ~/.hermes/agents/accessibility-auditor
source venv/bin/activate
export TELEGRAM_BOT_TOKEN="8752537543:AAH8UwykeRvTF6AMPaKvdnpppcdg7nUO460"
nohup python bot_final.py > bot.log 2>&1 &
echo "Bot restarted with correct token"
