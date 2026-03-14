# Accessibility Auditor Bot - Keep-Alive Monitor

## Overview
The `keep-alive.sh` script monitors your Accessibility Auditor bot process and automatically restarts it if it crashes or stops running.

### Features
✅ **PID Tracking** – Stores bot PID for reliable detection  
✅ **Log Rotation** – Automatic cleanup when logs exceed 10MB  
✅ **Health Checks** – Verifies process is actually running (not just PID reuse)  
✅ **Clean Environment** – Subshell venv activation prevents pollution  
✅ **Error Logging** – Detailed timestamps and diagnostics  
✅ **Stale Process Cleanup** – Kills orphaned bot processes before restart  

## Files
- **Script:** `~/.hermes/agents/accessibility-auditor/keep-alive.sh`
- **PID File:** `~/.hermes/agents/accessibility-auditor/.bot.pid`
- **Logs:** 
  - `keep-alive.log` – Monitor activity with rotated backups
  - `bot.log` – Bot stdout/stderr with rotated backups

## Cron Setup
```bash
# Runs every 1 minute from cron
* * * * * ~/.hermes/agents/accessibility-auditor/keep-alive.sh
```

The cronjob is already configured. Verify with:
```bash
list_cronjobs  # Shows "Accessibility Auditor Keep-Alive"
```

## Manual Testing
```bash
# Run the script manually
~/.hermes/agents/accessibility-auditor/keep-alive.sh

# Check the logs
tail -20 ~/.hermes/agents/accessibility-auditor/keep-alive.log

# Verify bot is running
ps aux | grep bot_final.py
cat ~/.hermes/agents/accessibility-auditor/.bot.pid
```

## What Happens If Bot Crashes
1. **Monitor detects** – Next cron execution (within 60 seconds)
2. **Logs the event** – Records timestamp and reason to `keep-alive.log`
3. **Cleans up** – Kills any stray bot processes
4. **Restarts cleanly** – Activates venv and starts fresh bot
5. **Verifies startup** – Confirms bot is responsive
6. **Updates PID** – Stores new process ID for next check

## Log Rotation
- Logs auto-rotate when they exceed **10MB**
- Last 3 rotated logs are kept
- Format: `keep-alive.log.YYYYMMDD_HHMMSS`
- Example:
  ```
  keep-alive.log                    (current, <10MB)
  keep-alive.log.20260314_120000    (rotated backup)
  keep-alive.log.20260314_110000    (rotated backup)
  ```

## Troubleshooting

**Bot won't stay running?**
```bash
# Check bot startup errors
tail -50 ~/.hermes/agents/accessibility-auditor/bot.log

# Check keep-alive logs
grep ERROR ~/.hermes/agents/accessibility-auditor/keep-alive.log
```

**Manual restart if needed:**
```bash
pkill -f "python3.*bot_final.py"
sleep 2
~/.hermes/agents/accessibility-auditor/keep-alive.sh
```

**Disable monitoring (if troubleshooting):**
```bash
# Via Hermes (remove the cron job)
remove_cronjob("1de383971302")  # or check list_cronjobs() for current ID
```

## Environment
- **Python:** 3.x (uses venv at `~/.hermes/agents/accessibility-auditor/venv`)
- **OS:** Linux/macOS compatible
- **Dependencies:** bash, python3, standard POSIX tools
- **Bot file:** `bot_final.py` (runs FastAPI + Telegram polling)

## Performance
- **Memory:** Negligible – just checks PID and logs
- **CPU:** Minimal – single process check per minute
- **Disk:** Log rotation prevents unbounded growth
- **Network:** None – local process monitoring only
