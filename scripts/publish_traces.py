"""Copies per-game traces into reports/ so the trace viewer can reach them.

GitHub Pages serves reports/ and nothing else, so traces sitting in traces/
or traces_ci/ are invisible to the site however well they are committed. This
module writes a published copy under reports/data/traces/<batch>/, one JSON
array per game plus a manifest the viewer reads.

The batch id is the report's own basename — reasoning_2026-07-22 — so a link
from a report to its traces needs no lookup table, and a report that is
regenerated as reasoning_2026-07-22-2.html gets its own directory rather than
overwriting the first one's evidence.

Nothing here rewrites a trace. The published copy is the JSONL parsed into a
JSON array and re-serialised; the fields are the harness's own.

    python3 scripts/publish_traces.py --report reasoning_2026-07-22.html \\
        --traces-dir traces --games 3 4 --winners TRAITORS TRAITORS
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from report_history import DATA_DIR, REPORTS_DIR

TRACES_SUBDIR = "traces"


def batch_id(report_filename):
    return os.path.splitext(os.path.basename(report_filename))[0]


def publish(report_filename, games, label=None, reports_dir=REPORTS_DIR):
    """games: [{"game_id": int, "trace": [entry, ...], "winner": str|None,
    "final_alive": int|None}]. Returns the manifest dict that was written."""
    bid = batch_id(report_filename)
    out_dir = os.path.join(reports_dir, "data", TRACES_SUBDIR, bid)
    os.makedirs(out_dir, exist_ok=True)

    entries = []
    for g in games:
        trace = g["trace"]
        name = f"game_{g['game_id']:04d}.json"
        with open(os.path.join(out_dir, name), "w") as f:
            json.dump(trace, f, separators=(",", ":"))
            f.write("\n")
        entries.append({
            "game_id": g["game_id"],
            "winner": g.get("winner"),
            "final_alive": g.get("final_alive"),
            "decisions": len(trace),
            # Relative to reports/, which is where every dashboard page lives.
            "file": f"data/{TRACES_SUBDIR}/{bid}/{name}",
        })

    manifest = {
        "id": bid,
        "label": label or bid,
        "report": os.path.basename(report_filename),
        "games": entries,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return manifest


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    ap = argparse.ArgumentParser(
        description="Publish an existing traces directory for the trace viewer.")
    ap.add_argument("--report", required=True,
                    help="the report these traces belong to, e.g. reasoning_2026-07-22.html")
    ap.add_argument("--traces-dir", required=True)
    ap.add_argument("--games", type=int, nargs="+", required=True)
    ap.add_argument("--winners", nargs="*", default=None,
                    help="optional, one per game — shown in the game picker")
    ap.add_argument("--final-alive", type=int, nargs="*", default=None)
    ap.add_argument("--label", default=None)
    args = ap.parse_args()

    if args.winners and len(args.winners) != len(args.games):
        ap.error("--winners must have one value per game")
    if args.final_alive and len(args.final_alive) != len(args.games):
        ap.error("--final-alive must have one value per game")

    games = []
    for i, gid in enumerate(args.games):
        path = os.path.join(args.traces_dir, f"game_{gid:04d}.jsonl")
        if not os.path.exists(path):
            ap.error(f"no trace at {path}")
        games.append({
            "game_id": gid,
            "trace": load_jsonl(path),
            "winner": args.winners[i] if args.winners else None,
            "final_alive": args.final_alive[i] if args.final_alive else None,
        })

    manifest = publish(args.report, games, label=args.label)
    total = sum(g["decisions"] for g in manifest["games"])
    print(f"published {len(manifest['games'])} game(s), {total} decisions, "
          f"to {os.path.relpath(os.path.join(DATA_DIR, TRACES_SUBDIR, manifest['id']), _REPO)}/")
    print("run scripts/make_index.py to pick it up in the viewer")


if __name__ == "__main__":
    main()
