#!/usr/bin/env python3
"""Capture Affine dashboard API data and render table history."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

_LEGACY: Any = None

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _load_legacy() -> Any:
    global _LEGACY
    if _LEGACY is not None:
        return _LEGACY
    tag = f"{sys.version_info.major}{sys.version_info.minor}"
    here = Path(__file__).resolve().parent
    pyc = here / "__pycache__" / f"snapshot.cpython-{tag}.pyc"
    if not pyc.is_file():
        raise SystemExit(
            f"No cached snapshot bytecode at {pyc}. "
            "Restore history/snapshot.py from backup or re-copy the history/ directory."
        )
    spec = importlib.util.spec_from_file_location("_snapshot_impl", pyc)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load cached snapshot from {pyc}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _LEGACY = mod
    return mod


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _rank_data_usable(data: dict[str, Any]) -> bool:
    scores = data.get("scores")
    return isinstance(scores, dict) and bool(scores.get("scores"))


def _best_rank_period(periods: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not periods:
        return None
    latest = periods[-1]
    if _rank_data_usable(latest.get("data") or {}):
        return latest
    for period in reversed(periods[:-1]):
        if _rank_data_usable(period.get("data") or {}):
            return period
    return latest


def enrich_rank_payload(
    rank_current: dict[str, Any], rank_stub: dict[str, Any]
) -> dict[str, Any]:
    legacy = _load_legacy()
    window = deepcopy(rank_current.get("window") or {})
    queue = deepcopy(rank_current.get("queue") or [])
    scores_resp = deepcopy(rank_current.get("scores") or {})
    all_scores = list(scores_resp.get("scores") or [])
    battle = ((window.get("battle") or {}).get("challenger") or {})
    champion = (window.get("champion") or {})
    summary = rank_stub.get("summary") or {
        "block_number": scores_resp.get("block_number"),
        "calculated_at": scores_resp.get("calculated_at"),
        "champion_uid": champion.get("uid"),
        "battle_uid": battle.get("uid"),
        "queue_size": len(queue),
    }
    rows = legacy.rank_table_rows(
        rank_current, table_limit=len(all_scores)
    )
    return {
        "summary": summary,
        "rows": rows,
        "window": window,
        "queue": queue,
        "scores": scores_resp,
    }


def capture(
    rank_top: int, queue_limit: int, miner_uid: int | None = None
) -> dict[str, Any]:
    legacy = _load_legacy()
    cache: dict[str, Any] = {}
    orig_api_get = legacy.api_get

    def cached_api_get(path: str) -> Any:
        if path not in cache:
            cache[path] = orig_api_get(path)
        return cache[path]

    legacy.api_get = cached_api_get
    try:
        captured = legacy.capture(rank_top, queue_limit, miner_uid)
        rank_path = f"/rank/current?top={rank_top}&queue_limit={queue_limit}"
        rank_current = cache[rank_path]
        captured["rank"] = enrich_rank_payload(rank_current, captured["rank"])
        return captured
    finally:
        legacy.api_get = orig_api_get


def save_rank_snapshot(
    store: dict[str, Any], rank_data: dict[str, Any], captured_at: str
) -> None:
    legacy = _load_legacy()
    ts = captured_at
    store["rank"] = [
        {
            "from": ts,
            "to": ts,
            "fingerprint": legacy.canonical(rank_data),
            "data": deepcopy(rank_data),
        }
    ]


def prune_rank_store(store: dict[str, Any]) -> None:
    periods = list(store.get("rank") or [])
    if len(periods) <= 1:
        return
    best = _best_rank_period(periods)
    if best is not None:
        store["rank"] = [deepcopy(best)]


def render_rank(periods: list[dict[str, Any]]) -> str:
    legacy = _load_legacy()
    from affine.src.miner.rank import _print_rank_table

    lines = [
        "# Rank — af get-rank format (GET /api/v1/rank/current → window + scores)",
        "",
    ]
    if not periods:
        lines.append("(no data yet — run ./history/snapshot.sh)")
        return "\n".join(lines) + "\n"

    latest = periods[-1]
    period = _best_rank_period(periods)
    assert period is not None
    data = period.get("data") or {}
    label = legacy.period_label(period)

    if period is not latest:
        latest_label = legacy.period_label(latest)
        lines.append(
            f"(Using rank payload from {label} — latest capture "
            f"({latest_label}) lacks window/scores; run ./history/snapshot.sh)"
        )
        lines.append("")

    lines.append(f"## {label}")
    lines.append("")

    if not _rank_data_usable(data):
        lines.append(
            "(Legacy snapshot — missing window/scores. Run ./history/snapshot.sh to refresh.)"
        )
        lines.append("")
        return "\n".join(lines) + "\n"

    window = data.get("window") or {}
    queue = data.get("queue") or []
    scores = data.get("scores") or {}

    buf = StringIO()
    with redirect_stdout(buf):
        _print_rank_table(window, queue, scores, show_reason=False)
    lines.append(strip_ansi(buf.getvalue()).rstrip())
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    legacy = _load_legacy()
    legacy.render_rank = render_rank

    parser = argparse.ArgumentParser(
        description="Accumulate Affine API history as tables."
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Top N rows in get-scores.txt",
    )
    parser.add_argument(
        "--rank-top",
        type=int,
        default=legacy.RANK_TOP,
        help="Scores fetched from /rank/current",
    )
    parser.add_argument(
        "--queue-limit",
        type=int,
        default=legacy.QUEUE_LIMIT,
        help="Queue depth from /rank/current",
    )
    parser.add_argument(
        "--uid",
        type=int,
        default=None,
        help="Miner UID for get-miner / get-score",
    )
    parser.add_argument("--no-archive", action="store_true")
    parser.add_argument(
        "--migrate-only",
        action="store_true",
        help="Rebuild tables from store.json only",
    )
    args = parser.parse_args()

    history = args.history_dir.resolve()
    store_path = history / legacy.STORE_NAME
    captured_at = legacy.now_utc()

    store = legacy.load_store(store_path)
    store = legacy.migrate_legacy_store(store, captured_at)
    store["rank"] = legacy.clean_rank_periods(store.get("rank") or [])
    prune_rank_store(store)

    if not args.migrate_only:
        print(f"→ GET {legacy.api_base()}/rank/current")
        captured = capture(args.rank_top, args.queue_limit, args.uid)
        store["meta"] = {
            "top": args.top,
            "rank_top": args.rank_top,
            "queue_limit": args.queue_limit,
            "uid": captured["miner_uid"],
        }
        legacy.merge_period(
            store["queue"], captured["queue"], captured_at
        )
        legacy.merge_period(
            store["challenge"], captured["challenge"], captured_at
        )
        save_rank_snapshot(store, captured["rank"], captured_at)
        legacy.merge_period(
            store["weights"], captured["weights"], captured_at
        )
        legacy.merge_period(store["scores"], captured["scores"], captured_at)
        legacy.merge_period(store["miner"], captured["miner"], captured_at)
        legacy.merge_period(store["score"], captured["score"], captured_at)
        legacy.merge_period(
            store["all_miners_env"], captured["all_miners_env"], captured_at
        )

    legacy.save_store(store_path, store)

    print("→ rendering accumulated tables")
    legacy.write_tables(history, store)

    manifest = legacy.write_manifest(
        history,
        store,
        args.top,
        store.get("meta", {}).get("uid", args.uid),
    )
    print(json.dumps(manifest, indent=2))

    if not args.no_archive and not args.migrate_only:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        arch = history / "archive" / stamp
        arch.mkdir(parents=True, exist_ok=True)
        for name in list(legacy.OUTPUT_FILES) + ["manifest.json", legacy.STORE_NAME]:
            src = history / name
            if src.exists():
                (arch / name).write_text(src.read_text())
        print(f"→ archived to history/archive/{stamp}/")

    print(f"Done. Accumulated history in {history}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
