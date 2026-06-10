# Affine status history

Local snapshots of the public [Affine API](https://api.affine.io/api/v1) (same data as the [live dashboard](https://www.affine.io/)). Each run appends to accumulated history and renders human-readable tables.

This directory is gitignored (see `.gitignore`).

## Quick start

```bash
cd affine-cortex
source .venv/bin/activate
./history/snapshot.sh
```

Override the API base with `API_URL` (default `https://api.affine.io/api/v1`).

`submitted_at` in `get-all-miners-env.txt` is estimated from each miner's on-chain `first_block` (commit block). Tune with `BITTENSOR_BLOCK_SECONDS` (default `12`).

## API → output files


| File                     | API source                                | Dashboard section                                                                             |
| ------------------------ | ----------------------------------------- | --------------------------------------------------------------------------------------------- |
| `get-queue.txt`          | `GET /rank/current` → `queue`             | Queue                                                                                         |
| `get-challenge.txt`      | `GET /rank/current` → `window`            | Challenge, evolution (champion / battle / reward split)                                       |
| `get-rank.txt`           | `GET /rank/current` → `window` + `scores` | Same layout as `af get-rank` (**latest snapshot only**)                                       |
| `get-weights.txt`        | `GET /scores/weights/latest`              | On-chain weights                                                                              |
| `get-miner.txt`          | `GET /miners/uid/{uid}`                   | Champion miner metadata                                                                       |
| `get-score.txt`          | `GET /scores/uid/{uid}`                   | Per-env scores for champion                                                                   |
| `get-all-miners-env.txt` | `GET /rank/current` → all `scores`        | All UIDs: rank, HF repo, `submitted_at` / `submitted_block`, per-env scores (**latest only**) |


## How accumulation works

1. `**snapshot.sh`** runs `**snapshot.py**`, which fetches the endpoints above.
2. Structured data is stored in `**store.json**`.
3. `***.txt**` files are regenerated as accumulated tables after each run.
4. Captures are keyed by **UTC timestamp** (`YYYY-MM-DD HH:MM:SS`).
5. If a new capture has the **same data** as the previous period, the period end time is updated (e.g. `2026-05-19 12:00:00 → 2026-05-20 08:30:00`) instead of duplicating rows.
6. If data **changes**, a new period starts at that capture time.
7. Tables show **full API fields** (no truncated hotkeys/models); period columns use `Period from` / `Period to`.
8. Accumulated `get-*.txt` files list **most recent periods first** (newest at the top).
9. `get-rank.txt` and `get-all-miners-env.txt` show **only the latest capture** (`store.json` keeps a single `rank` period; other keys still accumulate).

Optional timestamped copies: `**archive/<UTC-stamp>/`**.

## Options

```bash
./history/snapshot.sh --top 20              # (legacy) top N still stored in store.json scores key
./history/snapshot.sh --queue-limit 50      # queue depth from API
./history/snapshot.sh --rank-top 256        # scores rows fetched from /rank/current
./history/snapshot.sh --uid 56              # miner for get-miner / get-score
./history/snapshot.sh --no-archive
./history/snapshot.sh --migrate-only        # rebuild *.txt from store.json only
```

## Scheduled capture (cron)

Edit crontab (`crontab -e`), do not paste cron syntax into bash:

```cron
0 * * * * cd /root/affine-cortex && ./history/snapshot.sh >> /root/affine-cortex/history/snapshot.log 2>&1
```

## Background daemon (every 10 minutes)

Run `snapshot.sh` automatically in the background:

```bash
cd affine-cortex
./history/snapshot_daemon.sh start
./history/snapshot_daemon.sh status
./history/snapshot_daemon.sh stop
```

Optional args are forwarded to `snapshot.sh`:

```bash
./history/snapshot_daemon.sh start --uid 203 --rank-top 256
```

Change the interval (seconds):

```bash
SNAPSHOT_INTERVAL_SECONDS=300 ./history/snapshot_daemon.sh start   # every 5 minutes
```

Logs append to `history/snapshot.log`. A lock file prevents overlapping runs if a capture takes longer than the interval.

## Files


| Path            | Role                                     |
| --------------- | ---------------------------------------- |
| `snapshot.sh`   | Entrypoint                               |
| `snapshot_daemon.sh` | Background loop (default: every 10 min) |
| `snapshot.py`   | HTTP capture, period merge, table render |
| `store.json`    | Canonical structured history             |
| `manifest.json` | Latest run metadata                      |
| `get-*.txt`     | Accumulated table views                  |
| `archive/`      | Per-run snapshots                        |


## Troubleshooting

### HTTP 403 Forbidden

`api.affine.io` sits behind **AWS API Gateway**. A `403` with `{"message":"Forbidden"}` usually means your **outbound IP is blocked** (common on cloud GPU VMs), not a bug in `snapshot.sh`.

**Immediate workaround** (no API needed):

```bash
./history/snapshot.sh --migrate-only
```

Or run `./history/snapshot.sh` without flags: on **403** it automatically falls back to `store.json` (use `--require-api` to force failure instead).

**Other fixes:**


| Action                        | Command                                                          |
| ----------------------------- | ---------------------------------------------------------------- |
| Test API from this machine    | `curl -sS -D- "https://api.affine.io/api/v1/rank/current?top=1"` |
| Run from home / VPN           | Same `./history/snapshot.sh` on a non-datacenter IP              |
| API Gateway key (if provided) | `export AFFINE_API_KEY=your-key` then retry                      |
| Self-hosted validator API     | `export API_URL=https://your-host/api/v1`                        |


Optional env vars: `AFFINE_API_KEY`, `API_GATEWAY_KEY`, `AFFINE_API_USER_AGENT`, `AFFINE_API_HEADERS` (comma `Name: value` pairs).

## See also

- [Miner guide — Status queries](../docs/MINER.md#status-queries)
- [API reference](../skill/references/api-reference.md)

