"""reports/history.json — the cross-batch metric log.

One JSON object per completed report run, appended by the two CI harness
wrappers (scripts/run_structural_ci.py, scripts/run_reasoning_ci.py) and
rendered as a comparison table by scripts/make_index.py.

The point of this file is *cross-batch comparison*: every row carries the
same metric keys regardless of which tier produced it, so a 20,000-game
heuristic batch and a 2-game Sonnet batch land in the same table and can be
read side by side. That comparison is only ever structural — the two tiers
are not measuring the same thing, and a Sonnet row's rates come from a
sample far too small to mean anything on their own. See the caveat rendered
above the table in reports/index.html.

A metric that a given tier genuinely cannot produce is written as null, not
zero, and renders as "—". Nothing in here is inferred or backfilled.
"""

import datetime
import json
import os
import re

SCHEMA_VERSION = 1

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(REPO_ROOT, "reports")
HISTORY_PATH = os.path.join(REPORTS_DIR, "history.json")

# What the index table shows, in order: (key, label, format).
# format: text | int | pct | num2 | usd | secs
#
# Deliberately narrower than METRIC_KEYS below. Every metric is stored; only
# the ones worth scanning across batches are given a column, led by the two
# the README singles out as the things to watch on a real run — bloc
# non-unanimity and plate detection. The rest are a keystroke away in
# history.json, linked from the page.
COLUMNS = [
    ("date", "Date", "text"),
    ("kind", "Kind", "text"),
    ("games", "Games", "int"),
    ("model", "Model", "text"),
    ("params_summary", "Params", "text"),
    ("traitor_win_pct", "Traitor win", "pct"),
    ("final_2_pct", "Final 2", "pct"),
    ("rope_pct", "Rope raised", "pct"),
    ("bloc_non_unanimous_per_game", "Bloc non-unanimous /game", "num2"),
    ("plate_detect_per_game", "Plate detect /game", "num2"),
    ("invariant_violations", "Invariants", "int"),
    ("cost_usd", "Cost", "usd"),
]

# Everything persisted on a row, whether or not it gets a column.
METRIC_KEYS = [
    "traitor_win_pct", "faithful_win_pct", "final_2_pct", "final_3_pct",
    "final_4plus_pct", "rope_pct", "anchor_break_pct", "zero_vote_council_pct",
    "bloc_non_unanimous_per_game", "plate_detections", "plate_detect_per_game",
    "succession_trigger_pct", "succession_accept_pct", "invariant_violations",
]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def provenance():
    """CI provenance, when running under GitHub Actions; empty values locally."""
    server = os.environ.get("GITHUB_SERVER_URL", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    url = f"{server}/{repo}/actions/runs/{run_id}" if (server and repo and run_id) else None
    return {"commit": (os.environ.get("GITHUB_SHA") or "")[:7] or None, "run_url": url}


def params_fields(snapshot):
    """The two archetype-parameter fields every row carries: a digest that
    identifies the exact numbers a batch ran on, and a one-line summary for
    the table. Rows written before parameters were configurable have neither,
    and render as '—' rather than being backfilled with a guess."""
    if not snapshot:
        return {"params_digest": None, "params_summary": None, "params_overrides": None}
    overrides = list(snapshot.get("overrides") or [])
    n = len(overrides)
    summary = (f"defaults {snapshot['digest']}" if not n else
               f"{n} override{'' if n == 1 else 's'} {snapshot['digest']}")
    return {"params_digest": snapshot["digest"], "params_summary": summary,
            "params_overrides": overrides}


def new_row(kind, report, games, model, metrics, cost_usd, elapsed_s, notes="",
            params=None):
    """Build a history row. `metrics` supplies METRIC_KEYS; anything the tier
    cannot measure must be passed as None and is stored as null. `params` is
    archetypes.params_snapshot()."""
    now = utc_now()
    row = {
        "run_id": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": now.date().isoformat(),
        "kind": kind,
        "report": report,
        "games": games,
        "model": model,
        **params_fields(params),
        "cost_usd": round(cost_usd, 4) if cost_usd is not None else None,
        "elapsed_s": round(elapsed_s, 1) if elapsed_s is not None else None,
        "notes": notes,
    }
    for k in METRIC_KEYS:
        v = metrics.get(k)
        row[k] = round(v, 4) if isinstance(v, float) else v
    row.update(provenance())
    return row


def load(path=HISTORY_PATH):
    if not os.path.exists(path):
        return {"schema": SCHEMA_VERSION, "runs": []}
    with open(path) as f:
        data = json.load(f)
    data.setdefault("schema", SCHEMA_VERSION)
    data.setdefault("runs", [])
    return data


def append_row(row, path=HISTORY_PATH):
    data = load(path)
    data["runs"].append(row)
    data["runs"].sort(key=lambda r: r.get("run_id", ""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return path


def unique_report_path(kind, date=None, reports_dir=REPORTS_DIR):
    """reports/<kind>_<date>.html, suffixed -2, -3, ... if that day already has
    a report of this kind. Same-day re-runs never overwrite an earlier one, so
    the index can list every batch that was ever produced."""
    date = date or utc_now().date().isoformat()
    os.makedirs(reports_dir, exist_ok=True)
    base = f"{kind}_{date}"
    candidate = os.path.join(reports_dir, base + ".html")
    n = 1
    while os.path.exists(candidate):
        n += 1
        candidate = os.path.join(reports_dir, f"{base}-{n}.html")
    return candidate


DATA_DIR = os.path.join(REPORTS_DIR, "data")


def write_report_data(report_filename, data, reports_dir=REPORTS_DIR):
    """reports/data/<report basename>.json — what the dashboard charts fetch.
    Lives under reports/ because that directory is the whole published site;
    anything outside it is not reachable from the page."""
    out_dir = os.path.join(reports_dir, "data")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, os.path.splitext(report_filename)[0] + ".json")
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=False)
        f.write("\n")
    return path


REPORT_RE = re.compile(r"^(structural|reasoning)_(\d{4}-\d{2}-\d{2})(?:-(\d+))?\.html$")


def parse_report_name(filename):
    """-> (kind, date, seq) or None for anything that isn't a report file."""
    m = REPORT_RE.match(filename)
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3) or 1)
