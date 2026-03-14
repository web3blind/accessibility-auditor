# Keep-Alive Script - Changelog

## v2.0 (2026-03-14) - Production Release

### Major Improvements
- ✅ **PID File Tracking** – Reliable detection of running process (avoids PID reuse edge cases)
- ✅ **Health Checks** – Uses `kill -0` to verify process is actually alive, not just checking pgrep
- ✅ **Log Rotation** – Automatic size-based rotation at 10MB with 3-version backups
- ✅ **Clean Venv Isolation** – Subshell activation prevents environment variable pollution
- ✅ **Stale Process Cleanup** – Kills orphaned bot processes before restart attempt
- ✅ **Comprehensive Logging** – Timestamped entries with log level indicators
- ✅ **Cross-Platform** – macOS and Linux compatible (stat flag detection)

### Deployment
- Removed duplicate cronjobs (`d8a1579abc39`, `5493654982b4`)
- Installed new cronjob: `1de383971302` (every 1m, recurring)
- Created KEEP_ALIVE_README.md documentation

### Key Changes from Template
```diff
- TEMPLATE: simple pgrep-only check
+ v2.0: PID file + kill -0 health check + pgrep fallback

- TEMPLATE: sourced venv in main shell
+ v2.0: subshell venv isolation

- TEMPLATE: no log rotation
+ v2.0: automatic 10MB rotation with backups

- TEMPLATE: no error context
+ v2.0: comprehensive error logging with bot.log tail dump
```

### Testing Verified
✅ Script executes successfully
✅ Bot detected (PID: 4033701)
✅ Logs created and rotated correctly
✅ Cron job scheduled and operational

---

## v1.0 (Earlier) - Initial Implementation
- Basic process check with pgrep
- Simple restart with nohup
- Manual logging to keep-alive.log
