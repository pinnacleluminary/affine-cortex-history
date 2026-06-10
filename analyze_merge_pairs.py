#!/usr/bin/env python3
"""Analyze get-all-miners-env.txt for merge pair recommendations."""
import re
import sys
from pathlib import Path

ENVS = ["LIVEWEB", "MEMORY", "NAVWORLD", "SWE", "TERMINAL"]
ENV_SCORE_RE = re.compile(r"([\d.]+) \((\d+)\)")


def parse_env_cell(cell: str):
    cell = cell.strip()
    if cell == "-" or not cell:
        return None, 0
    m = ENV_SCORE_RE.match(cell)
    if m:
        return float(m.group(1)), int(m.group(2))
    return None, 0


def parse_line(line: str):
    # Fixed tail: 5 env cells, challenge_status, is_valid, optional reasons
    tail_m = re.search(
        r"([\d.-]+(?: \(\d+\))?|-)\s+([\d.-]+(?: \(\d+\))?|-)\s+([\d.-]+(?: \(\d+\))?|-)\s+"
        r"([\d.-]+(?: \(\d+\))?|-)\s+([\d.-]+(?: \(\d+\))?|-)\s+"
        r"(champion|terminated|sampling|in_progress)\s+(True|False)\s*(.*)$",
        line,
    )
    if not tail_m:
        return None
    env_cells = [tail_m.group(i) for i in range(1, 6)]
    challenge = tail_m.group(6)
    is_valid = tail_m.group(7) == "True"
    rest = (tail_m.group(8) or "").strip()
    invalid_reason = rest[:120] if rest and not is_valid else ""

    head = line[: tail_m.start()].rstrip()
    m = re.match(
        r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(.+?)\s{2,}(\S{40})\s{2,}"
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s{2,}(\d+)\s{2,}"
        r"(\S+(?:\s+#\d+)?)\s{2,}([\d.]+)\s{2,}([\d.]+)\s{2,}(\d+)\s*$",
        head,
    )
    if not m:
        m = re.match(
            r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(.+?)\s{2,}(\S{40})?\s*"
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})?\s*(\d*)\s{2,}"
            r"(\S+(?:\s+#\d+)?)\s{2,}([\d.]+)\s{2,}([\d.]+)\s{2,}(\d+)\s*$",
            head,
        )
        if not m:
            return None
    rank, uid, hotkey = int(m.group(1)), int(m.group(2)), m.group(3)
    model = m.group(4).strip()
    rev = (m.group(5) or "").strip() or None
    status = m.group(8).strip()
    overall, avg = float(m.group(9)), float(m.group(10))

    envs = {}
    for name, cell in zip(ENVS, env_cells):
        s, n = parse_env_cell(cell)
        envs[name] = {"score": s, "n": n}

    has_model = bool(model) and model != "-"
    scored = [e["score"] for e in envs.values() if e["score"] is not None and e["n"] >= 50]
    env_mean = sum(scored) / len(scored) if scored else None

    return {
        "rank": rank,
        "uid": uid,
        "hotkey": hotkey,
        "model": model,
        "revision": rev,
        "status": status,
        "overall": overall,
        "avg": avg,
        "challenge": challenge,
        "is_valid": is_valid,
        "invalid_reason": invalid_reason,
        "envs": envs,
        "has_model": has_model,
        "env_mean": env_mean,
    }


def coverage(m, min_n=80):
    return sum(1 for e in m["envs"].values() if e["score"] is not None and e["n"] >= min_n)


def pair_score(cand, champ, min_n=80):
    weights = {"LIVEWEB": 1.2, "MEMORY": 1.0, "NAVWORLD": 1.0, "SWE": 1.1, "TERMINAL": 1.0}
    gain = loss = 0.0
    specs = []
    for env in ENVS:
        cs, cn = champ["envs"][env]["score"], champ["envs"][env]["n"]
        es, en = cand["envs"][env]["score"], cand["envs"][env]["n"]
        if es is None or en < min_n or cs is None or cn < min_n:
            continue
        d = es - cs
        w = weights[env]
        if d > 0.02:
            gain += d * w
            specs.append((env, d, "up"))
        elif d < -0.03:
            loss += abs(d) * w * 1.5
            specs.append((env, d, "down"))
    return gain - loss, specs


def recommend_method(specs):
    ups = [e for e, d, t in specs if t == "up"]
    downs = [e for e, d, t in specs if t == "down"]
    max_up = max((abs(d) for e, d, t in specs if t == "up"), default=0)
    if len(ups) >= 3 and not downs:
        return "dare_ties", {"alpha": 1.0, "density": 0.2}
    if len(ups) >= 2 and len(downs) <= 1:
        return "dare_ties", {"alpha": 1.0, "density": 0.15}
    if len(ups) == 1 and not downs:
        if max_up > 0.08:
            return "dare_ties", {"alpha": 1.0, "density": 0.12}
        return "slerp", {"alpha": 0.2}
    if ups and downs:
        return "dare_ties", {"alpha": 1.0, "density": 0.1}
    return "linear", {"alpha": 0.15}


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "get-all-miners-env.txt")
    lines = [l for l in path.read_text().splitlines() if re.match(r"^\s+\d+\s+\d+", l)]
    miners = [r for l in lines if (r := parse_line(l))]
    print(f"Parsed {len(miners)} / {len(lines)} rows\n")

    champ = next((m for m in miners if m["status"] == "CHAMPION"), miners[0])
    print(f"Champion uid={champ['uid']}: {champ['model']}")
    print(f"  revision: {champ['revision']}")
    for env in ENVS:
        e = champ["envs"][env]
        print(f"  {env}: {e['score']} ({e['n']})")

    MIN_N = 80
    print(f"\n=== Per-env leaders (n>={MIN_N}) ===")
    for env in ENVS:
        cand = [
            (m["envs"][env]["score"], m)
            for m in miners
            if m["has_model"]
            and m["envs"][env]["score"] is not None
            and m["envs"][env]["n"] >= MIN_N
        ]
        cand.sort(key=lambda x: -x[0])
        print(f"\n{env}:")
        cs = champ["envs"][env]["score"] or 0
        for sc, m in cand[:5]:
            print(
                f"  {sc:.4f} ({m['envs'][env]['n']:3d}) uid={m['uid']:3d} "
                f"Δ={sc-cs:+.3f} valid={m['is_valid']} {m['model'][:52]}"
            )

    full = sorted(
        [m for m in miners if coverage(m, MIN_N) >= 5 and m["has_model"]],
        key=lambda m: -(m["env_mean"] or 0),
    )
    print(f"\n=== Full 5-env coverage: {len(full)} miners ===")
    for m in full[:12]:
        print(
            f"  uid={m['uid']:3d} mean={m['env_mean']:.4f} valid={m['is_valid']} "
            f"{m['status'][:14]:14s} {m['model'][:55]}"
        )

    candidates = [
        m
        for m in miners
        if m["uid"] != champ["uid"] and m["has_model"] and coverage(m, MIN_N) >= 3
    ]
    scored = []
    for m in candidates:
        sc, specs = pair_score(m, champ, MIN_N)
        if sc > 0.02:
            scored.append((sc, m, specs))
    scored.sort(key=lambda x: -x[0])

    print("\n=== RECOMMENDED MERGE PAIRS ===")
    for i, (sc, m, specs) in enumerate(scored[:15], 1):
        method, params = recommend_method(specs)
        deploy = m["is_valid"] and "hf_repo_not_found" not in m["invalid_reason"]
        ups = ", ".join(f"{e}+{d:.3f}" for e, d, t in specs if t == "up")
        downs = ", ".join(f"{e}{d:.3f}" for e, d, t in specs if t == "down")
        tag = "DEPLOY_OK" if deploy else "RESEARCH"
        print(f"\n{i}. [{tag}] {method} {params}  pair_score={sc:+.3f}")
        print(f"   champion: {champ['model']}")
        print(f"   revision: {champ['revision']}")
        print(f"   candidate: {m['model']}")
        print(f"   revision: {m['revision']}")
        print(f"   uid={m['uid']} status={m['status']} valid={m['is_valid']}")
        if m["invalid_reason"]:
            print(f"   invalid: {m['invalid_reason'][:70]}")
        print(f"   ↑ {ups or '—'}")
        if downs:
            print(f"   ↓ {downs}")


if __name__ == "__main__":
    main()
