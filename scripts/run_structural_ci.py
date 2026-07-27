"""CI wrapper around the stage-1.5 structural harness.

Adds exactly three things to `python3 run_structural.py`, and changes nothing
about how the games are played: a collision-free output filename, a summary
row appended to reports/history.json, and a clamp on --games so a bad
workflow input can't pin a runner for an hour.

The harness itself is imported, not reimplemented — run() and render_report()
are run_structural's own, so this wrapper cannot drift from the report it
generates.

    python3 scripts/run_structural_ci.py --games 5000
"""

import argparse
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from run_structural import run, render_report, report_data
from archetypes import PARAM_OVERRIDES, params_summary
from report_history import (append_row, new_row, unique_report_path, write_report_data,
                            REPO_ROOT)

# 5,000 games is ~8s; 200,000 is a few minutes. Past that a workflow_dispatch
# typo is just burning runner time — the report doesn't get more informative.
MAX_GAMES = 200_000


def metrics_from(r):
    n = r["n_games"]
    pct = lambda x: 100.0 * x / n
    detections = sum(r["detects"].values())
    return {
        "traitor_win_pct": pct(r["wins"].get("TRAITORS", 0)),
        "faithful_win_pct": pct(r["wins"].get("FAITHFUL", 0)),
        "final_2_pct": pct(r["endings"].get("Final 2", 0)),
        "final_3_pct": pct(r["endings"].get("Final 3", 0)),
        "final_4plus_pct": pct(r["endings"].get("Final 4+", 0)),
        "rope_pct": pct(r["rope_fired"]),
        "anchor_break_pct": pct(r["floats"].get("ANCHOR_BREAK", 0)),
        "zero_vote_council_pct": pct(r["floats"].get("ZERO_VOTE_COUNCIL", 0)),
        "bloc_non_unanimous_per_game": r["illegal"].get("BLOC_VOTE_NON_UNANIMOUS", 0) / n,
        "plate_detections": detections,
        "plate_detect_per_game": detections / n,
        "succession_trigger_pct": pct(r["succession_trigger"]),
        "succession_accept_pct": pct(r["succession_accept"]),
        "invariant_violations": sum(r["violations"].values()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=5000)
    ap.add_argument("--out", default=None, help="explicit output path (skips date naming)")
    args = ap.parse_args()

    games = args.games
    if games < 1:
        print(f"!! --games {games} is not a positive count; using 1")
        games = 1
    if games > MAX_GAMES:
        print(f"!! --games {games} exceeds the {MAX_GAMES:,} cap; clamping")
        games = MAX_GAMES

    out_path = args.out or unique_report_path("structural")

    print(f"structural batch: {games:,} games -> {os.path.relpath(out_path, REPO_ROOT)}")
    print(f"parameters: {params_summary()}")
    for change in PARAM_OVERRIDES:
        print(f"  override {change}")
    t0 = time.time()
    r = run(games)
    render_report(r, out_path)
    data_path = write_report_data(os.path.basename(out_path), report_data(r))
    elapsed = time.time() - t0

    m = metrics_from(r)
    row = new_row(
        kind="structural",
        report=os.path.basename(out_path),
        games=games,
        model="heuristic-bots",
        metrics=m,
        cost_usd=0.0,
        elapsed_s=r["elapsed"],
        notes="",
        params=r["params"],
    )
    append_row(row)

    print(f"\n{'='*66}")
    print(f"STRUCTURAL — {games:,} games | heuristic bots | {r['elapsed']:.1f}s | $0")
    print(f"{'='*66}")
    print(f"  traitor win        {m['traitor_win_pct']:.1f}%")
    print(f"  final 2            {m['final_2_pct']:.1f}%")
    print(f"  rope raised        {m['rope_pct']:.1f}%")
    print(f"  bloc non-unanimous {m['bloc_non_unanimous_per_game']:.2f}/game")
    print(f"  plate detections   {m['plate_detections']:,}")
    print(f"  invariants         {m['invariant_violations']} violation(s)")
    print(f"  parameters         {params_summary()}")
    print(f"\nreport   {os.path.relpath(out_path, REPO_ROOT)}")
    print(f"data     {os.path.relpath(data_path, REPO_ROOT)}")
    print(f"history  reports/history.json (+1 row, total {elapsed:.1f}s)")

    # Non-zero exit on an invariant violation: the report still gets written and
    # committed, but the workflow run goes red so it isn't missed.
    return 1 if m["invariant_violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
