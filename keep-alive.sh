#!/bin/bash
# Keep-alive monitor for Accessibility Auditor bot
# Checks every minute if bot is running, restarts if needed
# Add to crontab with: */1 * * * * ~/.hermes/agents/accessibility-auditor/keep-alive.sh

BOT_DIR="$HOME/.hermes/agents/accessibility-auditor"
LOG_FILE="$BOT_DIR/keep-alive.log"
VENV="$BOT_DIR/venv/bin/activate"
BOT_SCRIPT="$BOT_DIR/bot_final.py"

# Ensure venv exists
if [ ! -f "$VENV" ]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: venv not found at $VENV" >> "$LOG_FILE"
    exit 1
fi

# Check if process is running
if ! pgrep -f "python3.*bot_final.py" > /dev/null; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Bot not running, restarting..." >> "$LOG_FILE"
    
    # Start bot
    source "$VENV"
    cd "$BOT_DIR"
    nohup python3 -u "$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
    
    # Verify it started
    sleep 2
    if pgrep -f "python3.*bot_final.py" > /dev/null; then
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] Bot restarted successfully (PID: $(pgrep -f 'python3.*bot_final.py'))" >> "$LOG_FILE"
    else
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: Failed to restart bot" >> "$LOG_FILE"
    fi
else
    # Bot is running, just log heartbeat (optional - comment out to reduce logs)
    # echo "[$(date +'%Y-%m-%d %H:%M:%S')] Bot running (PID: $(pgrep -f 'python3.*bot_final.py'))" >> "$LOG_FILE"
    :
fi
