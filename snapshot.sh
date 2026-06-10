#!/usr/bin/env bash
# Capture Affine status queries and accumulate dated table history.
#
# Usage:
#   ./snapshot.sh
#   ./snapshot.sh --top 20 --uid 203
#   ./snapshot.sh --no-archive
#   ./snapshot.sh --migrate-only   # rebuild tables from store.json only

set -euo pipefail

HISTORY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Sibling repo: ../affine-cortex (override with AFFINE_CORTEX_ROOT).
if [[ -n "${AFFINE_CORTEX_ROOT:-}" ]]; then
  ROOT="$(cd "$AFFINE_CORTEX_ROOT" && pwd)"
else
  ROOT="$(cd "$HISTORY_DIR/../affine-cortex" && pwd)"
fi

if [[ ! -d "$ROOT" ]]; then
  echo "affine-cortex not found at $ROOT (set AFFINE_CORTEX_ROOT)" >&2
  exit 1
fi

export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

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
