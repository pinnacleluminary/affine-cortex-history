#!/usr/bin/env bash
# Run snapshot.sh on a fixed interval in the background.
#
# Usage:
#   ./history/snapshot_daemon.sh start
#   ./history/snapshot_daemon.sh start --uid 203
#   ./history/snapshot_daemon.sh stop
#   ./history/snapshot_daemon.sh status
#   ./history/snapshot_daemon.sh foreground   # loop in current shell (for debugging)
#
# Env:
#   SNAPSHOT_INTERVAL_SECONDS   seconds between runs (default: 600 = 10 minutes)

set -euo pipefail

HISTORY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOT_SH="$HISTORY_DIR/snapshot.sh"
PID_FILE="$HISTORY_DIR/snapshot_daemon.pid"
LOCK_FILE="$HISTORY_DIR/snapshot_daemon.lock"
LOG_FILE="$HISTORY_DIR/snapshot.log"
INTERVAL="${SNAPSHOT_INTERVAL_SECONDS:-600}"

usage() {
  cat <<EOF
Usage: $(basename "$0") {start|stop|status|foreground} [snapshot.sh args...]

  start       Run snapshot.sh every ${INTERVAL}s in the background
  stop        Stop the background loop
  status      Show whether the daemon is running
  foreground  Run the loop in the foreground (logs to stdout)

Set SNAPSHOT_INTERVAL_SECONDS to change the interval (default: 600).
Extra arguments are passed through to snapshot.sh on each run.
EOF
}

pid_alive() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE")"
  [[ -n "$pid" ]] || return 1
  pid_alive "$pid"
}

run_snapshot() {
  if ! flock -n "$LOCK_FILE" "$SNAPSHOT_SH" "$@"; then
    echo "→ skipped: previous snapshot still running"
  fi
}

loop_foreground() {
  trap 'exit 0' TERM INT
  echo "→ snapshot daemon loop (interval=${INTERVAL}s, log=${LOG_FILE})"
  while true; do
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) snapshot run ==="
    run_snapshot "$@" || echo "→ snapshot.sh failed (exit $?)"
    sleep "$INTERVAL"
  done
}

cmd_start() {
  if is_running; then
    echo "snapshot daemon already running (pid $(cat "$PID_FILE"))"
    return 0
  fi
  if [[ ! -x "$SNAPSHOT_SH" ]]; then
    echo "missing executable: $SNAPSHOT_SH" >&2
    exit 1
  fi
  touch "$LOG_FILE"
  nohup "$0" foreground "$@" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "started snapshot daemon (pid $(cat "$PID_FILE"), interval=${INTERVAL}s)"
  echo "log: $LOG_FILE"
}

cmd_stop() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "snapshot daemon not running"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! pid_alive "$pid"; then
      break
    fi
    sleep 0.5
  done
  if pid_alive "$pid"; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
  echo "stopped snapshot daemon (pid $pid)"
}

cmd_status() {
  if is_running; then
    echo "running (pid $(cat "$PID_FILE"), interval=${INTERVAL}s, log=${LOG_FILE})"
    return 0
  fi
  rm -f "$PID_FILE"
  echo "not running"
  return 1
}

main() {
  local cmd="${1:-}"
  shift || true

  case "$cmd" in
    start)
      cmd_start "$@"
      ;;
    stop)
      cmd_stop
      ;;
    status)
      cmd_status
      ;;
    foreground)
      loop_foreground "$@"
      ;;
    -h | --help | help | "")
      usage
      [[ -z "$cmd" ]] && exit 1
      ;;
    *)
      echo "unknown command: $cmd" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
