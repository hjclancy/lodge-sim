"""CI wrapper for the stage-2 Sonnet batch + stage-3 narrative report.

Runs both stages in one process under a single USD ceiling, then writes
reports/reasoning_<date>.html and appends a row to reports/history.json.

Why one process instead of two workflow steps: run_reasoning_report.py needs
`--winners` and `--final-alive` per game, and README is explicit that the
run_agents.py console line is the only persisted record of those. Scraping
stdout in YAML to feed the next step is a fragile way to move two integers.
Holding the referee's final state in memory and passing it straight to
extract_facts() is not.

The game-driver loop below mirrors run_agents.py's rather than calling it,
because budget enforcement and metric collection both need the live objects.
Everything that decides how a game is *played* is imported from the existing
modules — load_rules() and assignment_for() come from run_agents itself, so
seeds and archetype assignment are identical to a local `python3
run_agents.py` run. The console reporting is not reproduced; that is what the
report and history row are for.

Budget, in three layers:
  1. The workflow clamps its input before this script is invoked.
  2. This script clamps again (MAX_BUDGET_USD) — a caller that bypasses the
     workflow still can't ask for an unbounded run.
  3. BudgetedLLM refuses individual API calls once accrued spend reaches the
     agent share of the ceiling, so a single long game can't blow past it the
     way run_agents.py's between-games check allows.

    python3 scripts/run_reasoning_ci.py --games 2 --budget 10
"""

import argparse
import datetime
import json
import os
import sys
import time
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from referee import Referee, PHASES, TRAITOR, FAITHFUL
from run_skeleton import check
from run_agents import assignment_for, load_rules
from agents_claude import ClaudeAgents
from archetypes import ALL_IDS, ARCHETYPES, PARAM_OVERRIDES, params_snapshot, params_summary
from llm import LLM, MockLLM
import publish_traces
import run_reasoning_report as rr
from report_history import (append_row, new_row, unique_report_path, write_report_data,
                            REPO_ROOT)

# Ceilings. The Sonnet-5 batch of 2026-07-22 cost $2.50–$3.20 per game at
# effort=high, so $25 is roughly 8 games — well past the point where a case
# study stops earning its cost, and far enough below a painful bill that a
# fat-fingered input is survivable.
MAX_BUDGET_USD = 25.0
MIN_BUDGET_USD = 0.50
MAX_GAMES = 10

# Worst-case cost of one stage-3 narration call: ~60K input tokens at $2/M
# plus the full 16K max_tokens at $10/M. Kept as headroom so the last
# narration can never push total spend past the ceiling.
NARRATION_HEADROOM_USD = 0.40

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_EFFORT = "high"

PLATE_WORDS = ("plate", "china", "motif", "cairn")


class BudgetExceeded(RuntimeError):
    pass


class BudgetedLLM(LLM):
    """LLM that refuses to spend past a ceiling.

    run_agents.py checks --budget between games, so one game can overshoot by
    a whole game's worth of calls. Here the check is per call: once accrued
    cost reaches the cap, _one() raises instead of calling the API, and the
    exception propagates out through the referee phase that asked for it.
    Spend already made is spent — no cap can undo a completed call — but the
    ceiling can only be exceeded by the handful of ~400-token calls already in
    flight when it trips.
    """

    def __init__(self, cap_usd, **kw):
        super().__init__(**kw)
        self.cap_usd = cap_usd
        self.tripped = False

    def _one(self, system, user, retries=1):
        if self.cost() >= self.cap_usd:
            self.tripped = True
            raise BudgetExceeded(
                f"agent budget ${self.cap_usd:.2f} reached (spent ${self.cost():.2f})")
        return super()._one(system, user, retries=retries)


MOCK_NARRATIVE = (
    "This is a --mock run. No API call was made, so there is no narrative: the agents' "
    "reasoning came from llm.MockLLM's canned responses, not from a model, and narrating "
    "it would produce a close reading of nothing.\n\n"
    "What a mock run does check is the plumbing around the narrative — that games play "
    "through the referee, that traces are written, that extract_facts() reads them, and "
    "that the tables below render. The facts above are real in the sense that the referee "
    "really produced them; they are not real in any sense that matters for a case study."
)


# ------------------------------------------------------------------ stage 2

def play_batch(llm, games, out_dir, start=0):
    """Drive `games` games, writing one trace file each. Returns the per-game
    records the narrative stage needs, plus batch counters."""
    pub, tra = load_rules()
    os.makedirs(out_dir, exist_ok=True)

    played = []
    agg = dict(
        wins=Counter(), endings=Counter(), floats=Counter(), adjud=Counter(),
        illegal=Counter(), violations=Counter(), rope_fired=0,
        succession_trigger=0, succession_accept=0, plate_detections=0,
        zero_traitor_sweep=0,
        # Same shapes run_structural collects, so the dashboard can chart a
        # Sonnet batch and a heuristic batch with one set of drawing code.
        surv=defaultdict(Counter), seen=defaultdict(Counter),
        vote_acc=defaultdict(lambda: [0, 0]), banished_while_faithful=Counter(),
        detects_by_arch=Counter(), standing=Counter(),
        elim_cause=defaultdict(Counter), elim_role=defaultdict(Counter),
    )
    stopped = None

    for g in range(start, start + games):
        if llm.cost() >= llm.cap_usd:
            stopped = f"budget reached before game {g}"
            break
        assign = assignment_for(g)
        traces = []
        agents = ClaudeAgents(llm, assign, pub, tra, seed=g, trace_sink=traces)
        ref = Referee(agents, seed=g, game_id=g,
                      archetypes=[assign[f"P{i:02d}"] for i in range(1, 13)])
        t0 = time.time()
        try:
            s = ref.run()
        except BudgetExceeded as e:
            stopped = f"{e} — game {g} abandoned mid-play"
            print(f"  game {g:4d}  ABANDONED — {e}")
            break
        except Exception as e:
            agg["violations"]["EXCEPTION"] += 1
            print(f"  game {g:4d}  EXCEPTION {type(e).__name__}: {e}")
            continue

        for b in check(s):
            agg["violations"][b] += 1
        agg["wins"][s.winner] += 1
        n_alive = s.n_alive()
        agg["endings"]["Final 2" if n_alive <= 2 else
                       "Final 3" if n_alive == 3 else "Final 4+"] += 1
        for f in s.float_events:
            agg["floats"][f["tag"]] += 1
            if f["tag"] == "SUCCESSION_ACCEPT":
                agg["succession_accept"] += 1
        for a in s.adjudications:
            agg["adjud"][a["tag"]] += 1
            if a["tag"] == "ZERO_TRAITORS_FAITHFUL_WIN":
                agg["zero_traitor_sweep"] += 1
        for i in s.illegal_actions:
            agg["illegal"][i["tag"]] += 1
        if any(e.type == "ROPE_UP" for e in s.transcript):
            agg["rope_fired"] += 1
        agg["succession_trigger"] += len(s.metrics.get("succession_trigger", []))

        traitor_ids = {p.pid for p in s.players.values() if p.role == TRAITOR}
        for pid, p in s.players.items():
            a = assign[pid]
            agg["seen"][a][p.role] += 1
            if p.alive:
                agg["surv"][a][p.role] += 1
            else:
                if p.role == FAITHFUL and p.eliminated_by == "BANISHMENT":
                    agg["banished_while_faithful"][a] += 1
                agg["elim_cause"][p.eliminated_at or "?"][p.eliminated_by or "?"] += 1
                agg["elim_role"][p.eliminated_at or "?"][p.role] += 1
        for ev in s.transcript:
            if ev.type == "VOTE_REVEAL":
                for voter, tgt in ev.payload["ballots"].items():
                    if voter in assign and s.players[voter].role == FAITHFUL:
                        agg["vote_acc"][assign[voter]][1] += 1
                        if tgt in traitor_ids:
                            agg["vote_acc"][assign[voter]][0] += 1
        for k, v in s.metrics.items():
            if k.startswith("standing_win_"):
                pid = k.split("_")[-1]
                if pid in assign:
                    agg["standing"][assign[pid]] += len(v)

        # §8.3 detection is reasoning-gated at this tier: same unprompted-mention
        # parse run_agents.py uses. Never convert this to a probability.
        for t in traces:
            if t["tag"] == "dinner" and any(w in t["reasoning"].lower() for w in PLATE_WORDS):
                agg["plate_detections"] += 1
                agg["detects_by_arch"][t["archetype"]] += 1

        trace_path = os.path.join(out_dir, f"game_{g:04d}.jsonl")
        with open(trace_path, "w") as f:
            for t in traces:
                f.write(json.dumps(t) + "\n")

        played.append({"game_id": g, "winner": s.winner, "final_alive": n_alive,
                       "trace": traces, "trace_path": trace_path})
        print(f"  game {g:4d}  {s.winner:8s} final {n_alive:2d}  "
              f"{time.time()-t0:5.0f}s  {llm.summary()}")

    return played, agg, stopped


# ------------------------------------------------------------------ stage 3

def narrate_batch(played, spend_so_far, total_cap):
    """One Claude call per game, stopping before the ceiling. Returns the
    render_report() payload, narration spend, and how many were skipped."""
    import anthropic
    client = anthropic.Anthropic()

    sections, spent, skipped = [], 0.0, 0
    for rec in played:
        if spend_so_far + spent + NARRATION_HEADROOM_USD > total_cap:
            skipped = len(played) - len(sections)
            print(f"  narration stopped: ${total_cap - spend_so_far - spent:.2f} left, "
                  f"under the ${NARRATION_HEADROOM_USD:.2f} reserved per call "
                  f"({skipped} game(s) not narrated)")
            break
        facts = rr.extract_facts(rec["trace"], rec["winner"], rec["final_alive"])
        print(f"  narrating game {rec['game_id']} ({len(rec['trace'])} decisions)...")
        text, cost, in_tok, out_tok = rr.narrate_game(client, facts, rec["trace"])
        spent += cost
        print(f"    in={in_tok} out={out_tok} cost=${cost:.2f}")
        sections.append({"game_id": rec["game_id"], "facts": facts,
                         "narrative_html": rr.prose_to_html(text)})
    return sections, spent, skipped


# ------------------------------------------------------------------- driver

def metrics_from(agg, n):
    if n == 0:
        return {}
    pct = lambda x: 100.0 * x / n
    return {
        "traitor_win_pct": pct(agg["wins"].get("TRAITORS", 0)),
        "faithful_win_pct": pct(agg["wins"].get("FAITHFUL", 0)),
        "final_2_pct": pct(agg["endings"].get("Final 2", 0)),
        "final_3_pct": pct(agg["endings"].get("Final 3", 0)),
        "final_4plus_pct": pct(agg["endings"].get("Final 4+", 0)),
        "rope_pct": pct(agg["rope_fired"]),
        "anchor_break_pct": pct(agg["floats"].get("ANCHOR_BREAK", 0)),
        "zero_vote_council_pct": pct(agg["floats"].get("ZERO_VOTE_COUNCIL", 0)),
        "bloc_non_unanimous_per_game": agg["illegal"].get("BLOC_VOTE_NON_UNANIMOUS", 0) / n,
        "plate_detections": agg["plate_detections"],
        "plate_detect_per_game": agg["plate_detections"] / n,
        "succession_trigger_pct": pct(agg["succession_trigger"]),
        "succession_accept_pct": pct(agg["succession_accept"]),
        "invariant_violations": sum(agg["violations"].values()),
    }


def report_data(agg, n, model, elapsed_s):
    """Same shape as run_structural.report_data, so charts.html draws both
    tiers with one set of code. The numbers underneath are not comparable and
    the dashboard says so; the shape is, and that is all this is for."""
    return {
        "schema": 1,
        "kind": "reasoning",
        "games": n,
        "model": model,
        "elapsed_s": round(elapsed_s, 1),
        "params": params_snapshot(),
        "archetypes": [{"id": a, "name": ARCHETYPES[a]["name"]} for a in ALL_IDS],
        "survival": [
            {
                "id": a,
                "faithful_pct": (100.0 * agg["surv"][a][FAITHFUL] / agg["seen"][a][FAITHFUL]
                                 if agg["seen"][a][FAITHFUL] else None),
                "traitor_pct": (100.0 * agg["surv"][a][TRAITOR] / agg["seen"][a][TRAITOR]
                                if agg["seen"][a][TRAITOR] else None),
                "vote_accuracy_pct": (100.0 * agg["vote_acc"][a][0] / agg["vote_acc"][a][1]
                                      if agg["vote_acc"][a][1] else None),
                "banished_while_faithful_pct": (
                    100.0 * agg["banished_while_faithful"].get(a, 0) / agg["seen"][a][FAITHFUL]
                    if agg["seen"][a][FAITHFUL] else None),
            }
            for a in ALL_IDS
        ],
        "elimination_timing": [
            {
                "phase": ph,
                "murdered": agg["elim_cause"][ph].get("MURDER", 0),
                "banished": agg["elim_cause"][ph].get("BANISHMENT", 0),
                "were_traitor": agg["elim_role"][ph].get(TRAITOR, 0),
                "were_faithful": agg["elim_role"][ph].get(FAITHFUL, 0),
                "per_game": sum(agg["elim_cause"][ph].values()) / n,
            }
            for ph in PHASES if agg["elim_cause"].get(ph)
        ],
        "plate_detection": [
            {"id": a, "detections": agg["detects_by_arch"].get(a, 0),
             "per_game": agg["detects_by_arch"].get(a, 0) / n}
            for a in ALL_IDS
        ],
        "float_events": (
            [{"tag": t, "games": agg["floats"].get(t, 0),
              "pct": 100.0 * agg["floats"].get(t, 0) / n}
             for t in ("ANCHOR_BREAK", "SUCCESSION_ACCEPT", "ZERO_VOTE_COUNCIL")]
            + [{"tag": "ZERO_TRAITOR_SWEEP", "games": agg["zero_traitor_sweep"],
                "pct": 100.0 * agg["zero_traitor_sweep"] / n},
               {"tag": "ROPE_RAISED", "games": agg["rope_fired"],
                "pct": 100.0 * agg["rope_fired"] / n}]
        ),
        "standing_wins": [{"id": a, "count": agg["standing"].get(a, 0)} for a in ALL_IDS],
        "adjudications": [{"tag": k, "count": v, "per_game": v / n}
                          for k, v in agg["adjud"].most_common()],
        "illegal_actions": [{"tag": k, "count": v, "per_game": v / n}
                            for k, v in agg["illegal"].most_common()],
        "outcomes": {
            "traitor_win_pct": 100.0 * agg["wins"].get("TRAITORS", 0) / n,
            "faithful_win_pct": 100.0 * agg["wins"].get("FAITHFUL", 0) / n,
            "endings": {k: agg["endings"].get(k, 0) for k in ("Final 2", "Final 3", "Final 4+")},
        },
        "invariant_violations": sum(agg["violations"].values()),
    }


def clamp(games, budget):
    if games < 1:
        print(f"!! --games {games} is not a positive count; using 1")
        games = 1
    if games > MAX_GAMES:
        print(f"!! --games {games} exceeds the {MAX_GAMES}-game cap; clamping")
        games = MAX_GAMES
    if budget != budget or budget <= 0:            # NaN or non-positive
        print(f"!! --budget {budget} is not a usable ceiling; using ${MIN_BUDGET_USD:.2f}")
        budget = MIN_BUDGET_USD
    if budget < MIN_BUDGET_USD:
        print(f"!! --budget ${budget:.2f} is below the ${MIN_BUDGET_USD:.2f} floor; raising")
        budget = MIN_BUDGET_USD
    if budget > MAX_BUDGET_USD:
        print(f"!! --budget ${budget:.2f} exceeds the ${MAX_BUDGET_USD:.2f} cap; clamping")
        budget = MAX_BUDGET_USD
    return games, budget


def run_mock(args):
    """Everything except the two things that cost money: the agents are
    MockLLM, and no narration call is made. Output is quarantined in
    traces_mock/ and reports_mock/ (both gitignored) so a plumbing test can
    never end up on the published index."""
    games = min(max(args.games, 1), MAX_GAMES)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    traces_dir = args.traces_dir or os.path.join(REPO_ROOT, "traces_mock", stamp)
    out_path = args.out or os.path.join(REPO_ROOT, "reports_mock", f"reasoning_mock_{stamp}.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    print(f"MOCK reasoning batch: {games} game(s), MockLLM, $0")
    print(f"traces -> {os.path.relpath(traces_dir, REPO_ROOT)}\n")

    llm = MockLLM(seed=0)
    llm.cap_usd = float("inf")          # play_batch's budget checks, neutralised
    t0 = time.time()
    played, agg, stopped = play_batch(llm, games, traces_dir, start=args.start)
    if not played:
        print(f"\nno game completed — {stopped or 'see the exception above'}")
        return 1

    sections = [{"game_id": r["game_id"],
                 "facts": rr.extract_facts(r["trace"], r["winner"], r["final_alive"]),
                 "narrative_html": rr.prose_to_html(MOCK_NARRATIVE)} for r in played]
    rr.render_report(sections, out_path,
                     f"MOCK RUN &middot; {len(played)} game(s) &middot; MockLLM, no API calls, $0 "
                     f"&middot; {time.time()-t0:.0f}s &middot; not a report of anything")

    m = metrics_from(agg, len(played))
    print(f"\n{'='*66}")
    print(f"MOCK — {len(played)} game(s) | {llm.calls} mock calls | {time.time()-t0:.0f}s | $0")
    print(f"{'='*66}")
    print(f"  invariants         {m['invariant_violations']} violation(s)")
    print(f"  bloc non-unanimous {m['bloc_non_unanimous_per_game']:.2f}/game")
    print(f"\nreport   {os.path.relpath(out_path, REPO_ROOT)} (not committed, not indexed)")
    print("history  untouched — mock runs are not batches")
    return 1 if agg["violations"] else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=2)
    ap.add_argument("--budget", type=float, default=10.0, help="total USD ceiling, both stages")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default=DEFAULT_EFFORT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--traces-dir", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--mock", action="store_true",
                    help="plumbing test: MockLLM agents, no narration, no API key, $0. "
                         "Writes to traces_mock/ and reports_mock/ and appends no history "
                         "row, so a mock run can never reach the published index.")
    args = ap.parse_args()

    if args.mock:
        return run_mock(args)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set — this workflow cannot run without it.\n"
              "Repo Settings -> Secrets and variables -> Actions -> New repository secret.")
        return 2

    games, budget = clamp(args.games, args.budget)

    # Split the ceiling: the agent stage gets everything except a reserve big
    # enough to narrate the games it produces. Whatever the agent stage leaves
    # unspent flows back to narration, since narration checks total spend.
    reserve = min(0.30 * budget, NARRATION_HEADROOM_USD * games + 0.10)
    agent_cap = budget - reserve

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    traces_dir = args.traces_dir or os.path.join(REPO_ROOT, "traces_ci", stamp)

    print(f"reasoning batch: {games} game(s), model={args.model}, effort={args.effort}")
    print(f"parameters: {params_summary()}"
          + (f" ({', '.join(PARAM_OVERRIDES)})" if PARAM_OVERRIDES else ""))
    print(f"ceiling ${budget:.2f} total = ${agent_cap:.2f} agents + ${reserve:.2f} narration reserve")
    print(f"traces -> {os.path.relpath(traces_dir, REPO_ROOT)}\n")

    llm = BudgetedLLM(cap_usd=agent_cap, model=args.model,
                      workers=args.workers, effort=args.effort)

    t0 = time.time()
    played, agg, stopped = play_batch(llm, games, traces_dir, start=args.start)
    agent_spend = llm.cost()

    if not played:
        print(f"\nno game completed (spent ${agent_spend:.2f}). "
              f"{stopped or 'see the exception above'}")
        print("No report written and no history row appended — there is nothing to report on.")
        return 1

    print(f"\nstage 2 done: {len(played)} game(s), ${agent_spend:.2f}, "
          f"{llm.calls} calls, {llm.malformed} malformed\n")

    sections, narration_spend, skipped = narrate_batch(played, agent_spend, budget)
    total_spend = agent_spend + narration_spend
    elapsed = time.time() - t0

    out_path = args.out or unique_report_path("reasoning")
    report_name = os.path.basename(out_path)

    # Publish the traces before rendering: the report links to them per game,
    # and a link that lands nowhere is worse than no link.
    manifest = publish_traces.publish(
        report_name,
        [{"game_id": p["game_id"], "trace": p["trace"], "winner": p["winner"],
          "final_alive": p["final_alive"]} for p in played],
        label=(f"{datetime.date.today().isoformat()} · Reasoning · "
               f"{len(played)} game(s) · {args.model}"),
    )

    meta_bits = [
        f"N = {len(sections)} narrated of {len(played)} played",
        f"{args.model}, effort={args.effort}",
        f"agents ${agent_spend:.2f} + narration ${narration_spend:.2f} = "
        f"${total_spend:.2f} of ${budget:.2f} ceiling",
        f"params {params_summary()}",
        f"generated {datetime.date.today().isoformat()}",
    ]
    if stopped:
        meta_bits.append(f"batch halted: {stopped}")
    if skipped:
        meta_bits.append(f"{skipped} game(s) played but not narrated (budget)")
    rr.render_report(sections, out_path, " &middot; ".join(meta_bits),
                     batch_id=manifest["id"])
    data_path = write_report_data(
        report_name, report_data(agg, len(played), args.model, elapsed))

    notes = f"{llm.calls} calls, {llm.malformed} malformed"
    if stopped:
        notes += f"; halted: {stopped}"
    if skipped:
        notes += f"; {skipped} played but not narrated (budget)"

    row = new_row(
        kind="reasoning",
        report=os.path.basename(out_path),
        games=len(played),
        model=args.model,
        metrics=metrics_from(agg, len(played)),
        cost_usd=total_spend,
        elapsed_s=elapsed,
        notes=notes,
        params=params_snapshot(),
    )
    append_row(row)

    print(f"\n{'='*66}")
    print(f"REASONING — {len(played)} game(s) | {args.model} | {elapsed:.0f}s | "
          f"${total_spend:.2f} of ${budget:.2f}")
    print(f"{'='*66}")
    for k, v in agg["wins"].most_common():
        print(f"  {k:12s}{v}")
    print(f"  bloc non-unanimous {agg['illegal'].get('BLOC_VOTE_NON_UNANIMOUS', 0)} "
          f"({agg['illegal'].get('BLOC_VOTE_NON_UNANIMOUS', 0)/len(played):.2f}/game)")
    print(f"  plate detections   {agg['plate_detections']}")
    print(f"  invariants         {sum(agg['violations'].values())} violation(s)")
    print(f"  parameters         {params_summary()}")
    print(f"\nreport   {os.path.relpath(out_path, REPO_ROOT)}")
    print(f"data     {os.path.relpath(data_path, REPO_ROOT)}")
    print(f"traces   {os.path.relpath(traces_dir, REPO_ROOT)} "
          f"(published to reports/data/traces/{manifest['id']}/)")
    print("history  reports/history.json (+1 row)")

    return 1 if agg["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
