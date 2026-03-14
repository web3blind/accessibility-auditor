#!/bin/bash
# Accessibility Auditor Bot - Keep-Alive Monitor
# Monitors and auto-restarts bot with PID tracking, log rotation, and health checks
# Designed to run from cron: * * * * * ~/.hermes/agents/accessibility-auditor/keep-alive.sh

set -o pipefail

BOT_DIR="$HOME/.hermes/agents/accessibility-auditor"
VENV_PATH="$BOT_DIR/venv"
PID_FILE="$BOT_DIR/.bot.pid"
LOG_FILE="$BOT_DIR/keep-alive.log"
BOT_LOG="$BOT_DIR/bot.log"
MAX_LOG_SIZE=10485760  # 10MB in bytes
BOT_NAME="python3.*bot_final.py"

# Ensure directory exists
mkdir -p "$BOT_DIR"

log_message() {
    local level="$1"
    shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*" >> "$LOG_FILE"
}

rotate_log() {
    local log_file="$1"
    if [[ -f "$log_file" ]]; then
        local size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null || echo 0)
        if [[ $size -gt $MAX_LOG_SIZE ]]; then
            local timestamp=$(date '+%Y%m%d_%H%M%S')
            mv "$log_file" "${log_file}.${timestamp}"
            # Keep only last 3 rotated logs
            ls -t "${log_file}".* 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null
            log_message "INFO" "Log rotated: $log_file (was ${size} bytes)"
        fi
    fi
}

get_pid_from_file() {
    if [[ -f "$PID_FILE" ]]; then
        cat "$PID_FILE" 2>/dev/null
    fi
}

is_process_running() {
    local pid="$1"
    if [[ -z "$pid" ]]; then
        return 1
    fi
    kill -0 "$pid" 2>/dev/null
    return $?
}

# Rotate logs if needed
rotate_log "$LOG_FILE"
rotate_log "$BOT_LOG"

# Check if bot is already running
STORED_PID=$(get_pid_from_file)
if [[ -n "$STORED_PID" ]] && is_process_running "$STORED_PID"; then
    # Verify it's actually the bot process (not PID reuse)
    if ps -p "$STORED_PID" 2>/dev/null | grep -q "$BOT_NAME"; then
        # Bot is healthy
        exit 0
    fi
fi

# Fallback: check by process name
if pgrep -f "$BOT_NAME" > /dev/null 2>&1; then
    RUNNING_PID=$(pgrep -f "$BOT_NAME" | head -1)
    echo "$RUNNING_PID" > "$PID_FILE"
    log_message "INFO" "Bot running (PID: $RUNNING_PID, recovered from pgrep)"
    exit 0
fi

# Bot is not running - attempt restart
log_message "WARN" "Bot not running. Attempting restart..."

# Kill any stray processes
pkill -9 -f "$BOT_NAME" 2>/dev/null || true
sleep 1

# Activate venv in a subshell to avoid environment pollution
(
    if [[ -f "$VENV_PATH/bin/activate" ]]; then
        source "$VENV_PATH/bin/activate"
    else
        log_message "ERROR" "Virtual environment not found at $VENV_PATH"
        exit 1
    fi
    
    cd "$BOT_DIR" || exit 1
    
    # Start bot with nohup and capture its PID
    nohup python3 -u bot_final.py >> "$BOT_LOG" 2>&1 &
    BOT_PID=$!
    echo $BOT_PID
) > "$PID_FILE" 2>&1

RESTART_PID=$(cat "$PID_FILE" 2>/dev/null)

# Wait briefly for startup
sleep 3

# Verify restart was successful
if is_process_running "$RESTART_PID"; then
    log_message "INFO" "Bot restarted successfully (PID: $RESTART_PID)"
else
    log_message "ERROR" "Failed to restart bot. Check $BOT_LOG for details"
    # Attempt to capture startup error from log
    if [[ -f "$BOT_LOG" ]]; then
        log_message "ERROR" "Last 10 lines of bot.log:"
        tail -10 "$BOT_LOG" | while read -r line; do
            log_message "ERROR" "  $line"
        done
    fi
    exit 1
fi

exit 0
