"""
Stage-2 harness. Claude agents, fixed seeds, archetype reporting.

    python3 run_agents.py --games 20 --model claude-haiku-4-5-20251001
    python3 run_agents.py --games 5 --mock        # free plumbing test

Always dry-run with --mock first. Then run 5 real games and read the traces
before committing to 200.
"""

import argparse
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict

from referee import Referee, TRAITOR, FAITHFUL
from archetypes import ALL_IDS, ARCHETYPES
from agents_claude import ClaudeAgents
from llm import LLM, MockLLM
from run_skeleton import check


def load_rules():
    base = os.path.join(os.path.dirname(__file__), "rules")
    with open(os.path.join(base, "public_rules.md")) as f:
        pub = f.read()
    with open(os.path.join(base, "traitor_brief.md")) as f:
        tra = f.read()
    if "[PLACEHOLDER" in pub or "[PLACEHOLDER" in tra:
        print("!" * 68)
        print("! WARNING: rules/ still contains PLACEHOLDER text.")
        print("! Agents are reading a restatement of the canon, not the real")
        print("! player-facing documents. Results measure the canon against")
        print("! itself and will NOT find document defects. See rules/README.md.")
        print("!" * 68 + "\n")
    return pub, tra


def assignment_for(seed):
    """Seats randomized; archetype uncorrelated with seat id (§5.2 of archetypes)."""
    rng = random.Random(seed * 7919 + 13)
    pids = [f"P{i:02d}" for i in range(1, 13)]
    ids = ALL_IDS[:]
    rng.shuffle(ids)
    return dict(zip(pids, ids))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=5)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default="traces")
    ap.add_argument("--budget", type=float, default=25.0,
                    help="USD ceiling; run halts when exceeded")
    args = ap.parse_args()

    pub, tra = load_rules()
    os.makedirs(args.out, exist_ok=True)
    llm = MockLLM(seed=0) if args.mock else LLM(model=args.model,
                                                workers=args.workers)

    wins = Counter(); endings = Counter(); floats = Counter()
    adjud = Counter(); illegal = Counter(); violations = Counter()
    surv = defaultdict(lambda: Counter())      # archetype -> {role: survived}
    seen = defaultdict(lambda: Counter())      # archetype -> {role: games}
    vote_acc = defaultdict(lambda: [0, 0])     # archetype -> [hits, total]
    detects = Counter(); standing = Counter()
    ballot1 = defaultdict(Counter)
    t0 = time.time()

    for g in range(args.start, args.start + args.games):
        if llm.cost() > args.budget:
            print(f"\n!! budget ${args.budget} exceeded — stopping at game {g}\n")
            break
        assign = assignment_for(g)
        traces = []
        agents = ClaudeAgents(llm, assign, pub, tra, seed=g, trace_sink=traces)
        ref = Referee(agents, seed=g, game_id=g,
                      archetypes=[assign[f"P{i:02d}"] for i in range(1, 13)])
        try:
            s = ref.run()
        except Exception as e:
            violations["EXCEPTION"] += 1
            print(f"  game {g}: EXCEPTION {type(e).__name__}: {e}")
            continue

        for b in check(s):
            violations[b] += 1

        wins[s.winner] += 1
        endings[s.n_alive()] += 1
        for f in s.float_events:
            floats[f["tag"]] += 1
        for a in s.adjudications:
            adjud[a["tag"]] += 1
        for i in s.illegal_actions:
            illegal[i["tag"]] += 1

        traitor_ids = {p.pid for p in s.players.values() if p.role == TRAITOR}
        for pid, p in s.players.items():
            a = assign[pid]
            seen[a][p.role] += 1
            if p.alive:
                surv[a][p.role] += 1
        for ev in s.transcript:
            if ev.type == "VOTE_REVEAL":
                for voter, tgt in ev.payload["ballots"].items():
                    if voter in assign and s.players[voter].role == FAITHFUL:
                        vote_acc[assign[voter]][1] += 1
                        if tgt in traitor_ids:
                            vote_acc[assign[voter]][0] += 1
            if ev.type == "FINALE_BALLOT_1":
                for voter, choice in ev.payload["ballots"].items():
                    ballot1[s.players[voter].role][choice] += 1
        for k, v in s.metrics.items():
            if k == "plate_detect":
                detects["total"] += len(v)
            if k.startswith("standing_win_"):
                standing[assign.get(k.split("_")[-1], "?")] += len(v)
        for t in traces:
            if t["tag"] == "dinner" and any(
                    w in t["reasoning"].lower()
                    for w in ("plate", "china", "motif", "cairn")):
                detects[t["archetype"]] += 1

        with open(os.path.join(args.out, f"game_{g:04d}.jsonl"), "w") as f:
            for t in traces:
                f.write(json.dumps(t) + "\n")
        print(f"  game {g:4d}  {s.winner:8s} final {s.n_alive()}  "
              f"{llm.summary()}")

    n = sum(wins.values()) or 1
    pct = lambda x: f"{100*x/n:5.1f}%"
    print(f"\n{'='*66}\nAGENT RUN — {n} games | model={llm.model} | "
          f"{time.time()-t0:.0f}s | {llm.summary()}\n{'='*66}\n")

    print("INVARIANT VIOLATIONS")
    print("  none\n" if not violations else
          "\n".join(f"  {k:40s}{v}" for k, v in violations.most_common()) + "\n")

    print("OUTCOMES")
    for k, v in wins.most_common():
        print(f"  {k:12s}{v:4d}  {pct(v)}")
    lo = wins["TRAITORS"] / n
    ci = 1.96 * (lo * (1 - lo) / n) ** 0.5
    print(f"  traitor win rate {100*lo:.1f}% +/- {100*ci:.1f}pts (95% CI)\n")

    print("ENDING SIZE")
    for k in sorted(endings):
        print(f"  Final {k:<8d}{endings[k]:4d}  {pct(endings[k])}")
    print()

    print("ARCHETYPE — survival to end, by role   [§5.2 bias: loud under-modelled]")
    print(f"  {'id':5s}{'name':18s}{'F surv':>8s}{'T surv':>8s}{'vote acc':>10s}")
    for a in ALL_IDS:
        sf, st = seen[a][FAITHFUL], seen[a][TRAITOR]
        f_s = f"{100*surv[a][FAITHFUL]/sf:.0f}%" if sf else "-"
        t_s = f"{100*surv[a][TRAITOR]/st:.0f}%" if st else "-"
        hits, tot = vote_acc[a]
        acc = f"{100*hits/tot:.0f}%" if tot else "-"
        print(f"  {a:5s}{ARCHETYPES[a]['name']:18s}{f_s:>8s}{t_s:>8s}{acc:>10s}")
    print("  (A03 Faithful survival is the headline: >40% means silence wins)\n")

    print("ROLE BALANCE CHECK  (each archetype should draw Traitor ~25%)")
    bad = [a for a in ALL_IDS
           if seen[a][TRAITOR] and abs(seen[a][TRAITOR] / max(1, seen[a][TRAITOR] + seen[a][FAITHFUL]) - 0.25) > 0.15]
    print("  ok\n" if not bad else f"  skewed: {bad}\n")

    print("PLATE DETECTION (§8.3, reasoning-gated)")
    if not detects:
        print("  zero detections — check the gate, or nobody looked\n")
    else:
        for k, v in detects.most_common():
            print(f"  {k:12s}{v}")
        print()

    print("TRAITOR DEADLOCK — standing_wins by archetype (§8.2 dominance check)")
    print("  none\n" if not standing else
          "\n".join(f"  {k:12s}{v}" for k, v in standing.most_common()) + "\n")

    print("FINALE BALLOT 1 by role")
    for role, c in ballot1.items():
        print(f"  {role:10s}" + "  ".join(f"{k}:{v}" for k, v in c.items()))
    print()

    print("FLOAT EVENTS");  [print(f"  {k:35s}{v:4d}  {pct(v)}") for k, v in floats.most_common()]
    print("\nREF_ADJUDICATION (bug list)")
    for k, v in adjud.most_common():
        print(f"  {k:40s}{v:5d}  {v/n:5.2f}/game")
    print("\nILLEGAL_ACTION (ambiguity list)")
    print("  none" if not illegal else
          "\n".join(f"  {k:40s}{v:5d}  {v/n:5.2f}/game" for k, v in illegal.most_common()))
    print(f"\ntraces written to {args.out}/\n")


if __name__ == "__main__":
    main()
