#!/usr/bin/env bash
# Capture Affine status queries and accumulate dated table history.
#
# Usage:
#   ./history/snapshot.sh
#   ./history/snapshot.sh --top 20 --uid 203
#   ./history/snapshot.sh --no-archive
#   ./history/snapshot.sh --migrate-only   # rebuild tables from store.json only

set -euo pipefail

HISTORY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HISTORY_DIR/.." && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/.env"
  set +a
fi

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
fi

exec python3 "$HISTORY_DIR/snapshot.py" --history-dir "$HISTORY_DIR" "$@"
