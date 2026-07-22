"""
Structural / distributional harness — heuristic bots, high volume, $0.

Runs N games through the unmodified referee with HeuristicAgents (see
heuristic_bots.py for the parameter-to-decision mappings and their explicit
"modeling choice, not ground truth" caveat) and emits a standalone HTML
report to reports/structural_<date>.html.

    python3 run_structural.py                 # 5000 games, today's date
    python3 run_structural.py --games 20000
    python3 run_structural.py --games 500 --out reports/smoke.html

Seeds are fixed and derived only from the game index, so a given --games
value always reproduces the same run.
"""

import argparse
import datetime
import os
import random
import time
from collections import Counter, defaultdict

from referee import Referee, TRAITOR, FAITHFUL
from heuristic_bots import HeuristicAgents
from archetypes import ALL_IDS, ARCHETYPES
from run_skeleton import check
from report_common import html_shell, table, esc


def assignment_for(seed):
    """Seats + archetypes randomized per game, uncorrelated with seat id —
    same scheme as run_agents.py's assignment_for, kept independent here so
    this harness has no dependency on the Claude-agent stage."""
    rng = random.Random(seed * 7919 + 13)
    pids = [f"P{i:02d}" for i in range(1, 13)]
    ids = ALL_IDS[:]
    rng.shuffle(ids)
    return dict(zip(pids, ids))


def run(n_games):
    wins = Counter()
    endings = Counter()
    floats = Counter()
    adjud = Counter()
    illegal = Counter()
    violations = Counter()
    failures = []

    surv = defaultdict(Counter)          # archetype -> {role: survived_count}
    seen = defaultdict(Counter)          # archetype -> {role: games_count}
    banished_while_faithful = Counter()  # archetype -> count
    vote_acc = defaultdict(lambda: [0, 0])   # archetype -> [hits, total] (as Faithful)
    standing = Counter()                 # archetype -> standing_wins as Traitor
    detects = Counter()                  # archetype -> plate detections
    role_games = Counter()               # archetype -> {TRAITOR/FAITHFUL: n} for balance check

    rope_fired = 0
    anchor_live = []
    succession_trigger = 0
    succession_accept = 0
    zero_vote_council = 0
    zero_traitor_sweep = 0

    t0 = time.time()
    for g in range(n_games):
        assign = assignment_for(g)
        arch_list = [assign[f"P{i:02d}"] for i in range(1, 13)]
        agents = HeuristicAgents(seed=g)
        ref = Referee(agents, seed=g, game_id=g, archetypes=arch_list)
        try:
            s = ref.run()
        except Exception as ex:
            violations["EXCEPTION"] += 1
            failures.append((g, f"{type(ex).__name__}: {ex}"))
            continue

        bad = check(s)
        for b in bad:
            violations[b] += 1
            if len(failures) < 20:
                failures.append((g, b))

        wins[s.winner] += 1
        n = s.n_alive()
        endings["Final 2" if n <= 2 else "Final 3" if n == 3 else "Final 4+"] += 1

        for f in s.float_events:
            tag = f["tag"]
            floats[tag] += 1
            if tag == "ZERO_VOTE_COUNCIL":
                zero_vote_council += 1
            elif tag == "SUCCESSION_ACCEPT":
                succession_accept += 1
        for a in s.adjudications:
            adjud[a["tag"]] += 1
            if a["tag"] == "ZERO_TRAITORS_FAITHFUL_WIN":
                zero_traitor_sweep += 1
        for il in s.illegal_actions:
            illegal[il["tag"]] += 1

        if any(e.type == "ROPE_UP" for e in s.transcript):
            rope_fired += 1
        if s.anchor_live_councils is not None:
            anchor_live.append(s.anchor_live_councils)
        succession_trigger += len(s.metrics.get("succession_trigger", []))

        traitor_ids = {p.pid for p in s.players.values() if p.role == TRAITOR}
        for pid, p in s.players.items():
            a = assign[pid]
            seen[a][p.role] += 1
            role_games[a] += 1
            if p.alive:
                surv[a][p.role] += 1
            elif p.role == FAITHFUL and p.eliminated_by == "BANISHMENT":
                banished_while_faithful[a] += 1

        for ev in s.transcript:
            if ev.type == "VOTE_REVEAL":
                for voter, tgt in ev.payload["ballots"].items():
                    if voter in assign and s.players[voter].role == FAITHFUL:
                        vote_acc[assign[voter]][1] += 1
                        if tgt in traitor_ids:
                            vote_acc[assign[voter]][0] += 1

        for k, v in s.metrics.items():
            if k.startswith("standing_win_"):
                pid = k.split("_")[-1]
                if pid in assign:
                    standing[assign[pid]] += len(v)
        for pid in s.metrics.get("plate_detect_by_pid", []):
            if pid in assign:
                detects[assign[pid]] += 1

    elapsed = time.time() - t0
    return dict(
        n_games=n_games, elapsed=elapsed, wins=wins, endings=endings, floats=floats,
        adjud=adjud, illegal=illegal, violations=violations, failures=failures,
        surv=surv, seen=seen, banished_while_faithful=banished_while_faithful,
        vote_acc=vote_acc, standing=standing, detects=detects, role_games=role_games,
        rope_fired=rope_fired, anchor_live=anchor_live,
        succession_trigger=succession_trigger, succession_accept=succession_accept,
        zero_vote_council=zero_vote_council, zero_traitor_sweep=zero_traitor_sweep,
    )


# ---------------------------------------------------------------- reporting

def ci95(k, n):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    half = 1.96 * (p * (1 - p) / n) ** 0.5
    return p, half


def render_report(r, out_path):
    n = r["n_games"]
    pct = lambda x: f"{100 * x / n:.1f}%"

    traitor_wins = r["wins"].get("TRAITORS", 0)
    tw_p, tw_ci = ci95(traitor_wins, n)

    ok = not r["violations"]
    status_pill = ('<span class="pill ok">zero invariant violations</span>' if ok
                    else f'<span class="pill bad">{sum(r["violations"].values())} violations</span>')

    summary = (
        f'<div class="summary">'
        f'Across {n:,} heuristic-bot games ({r["elapsed"]:.1f}s wall-clock, no API calls), '
        f'Traitors won {pct(traitor_wins)} of games (95% CI &plusmn;{100*tw_ci:.1f}pts) and '
        f'Faithful won {pct(r["wins"].get("FAITHFUL", 0))}. '
        f'The game most often ends at {max(r["endings"], key=r["endings"].get)} '
        f'({pct(max(r["endings"].values()))} of games). '
        f'The rope raised in {pct(r["rope_fired"])} of games. '
        f'{status_pill}'
        f'</div>'
    )

    disclaimer = (
        '<div class="disclaimer">'
        '<strong>What this report is and isn\'t.</strong> These are '
        f'{n:,} games played by <em>heuristic bots</em> — deterministic decision rules '
        'built from the twelve archetypes\' declared parameters (see heuristic_bots.py), '
        'not by reasoning agents and not by real players. They answer '
        '<strong>"how often" and "how distributed"</strong> — win rates, survival curves, '
        'mechanic firing rates — at a volume real reasoning agents can\'t reach '
        'affordably. They do not answer <strong>"why"</strong> or capture how an actual '
        'reasoning agent (or a human) would read the table, notice a tell, or change '
        'its mind mid-game. Questions about reasoning quality, what an archetype '
        'actually attends to, or how a specific game unfolded belong to the '
        'Sonnet reasoning report (reports/reasoning_*.html), not here.'
        '</div>'
    )

    parts = [summary, disclaimer]

    # -- outcomes --
    parts.append("<h2>Outcomes</h2>")
    parts.append(table(
        ["Winner", "Games", "Share", "95% CI"],
        [[w, f"{c:,}", pct(c),
          f"±{100*ci95(c, n)[1]:.1f}pts"] for w, c in r["wins"].most_common()],
    ))

    # -- ending size --
    parts.append("<h2>Ending size</h2>")
    order = ["Final 2", "Final 3", "Final 4+"]
    parts.append(table(
        ["Ending", "Games", "Share"],
        [[k, f"{r['endings'].get(k,0):,}", pct(r["endings"].get(k, 0))] for k in order],
    ))

    # -- archetype survival --
    parts.append("<h2>Archetype survival to end, by role</h2>")
    rows = []
    for a in ALL_IDS:
        name = ARCHETYPES[a]["name"]
        sf, st = r["seen"][a][FAITHFUL], r["seen"][a][TRAITOR]
        f_s = f"{100*r['surv'][a][FAITHFUL]/sf:.0f}%" if sf else "-"
        t_s = f"{100*r['surv'][a][TRAITOR]/st:.0f}%" if st else "-"
        hits, tot = r["vote_acc"][a]
        acc = f"{100*hits/tot:.0f}%" if tot else "-"
        bwf = r["banished_while_faithful"].get(a, 0)
        bwf_rate = f"{100*bwf/sf:.0f}%" if sf else "-"
        rows.append([f"{a} {name}", f_s, t_s, acc, bwf_rate])
    parts.append(table(
        ["Archetype", "Faithful survival", "Traitor survival", "Vote accuracy (as Faithful)",
         "Banished while Faithful"],
        rows,
        note=("Vote accuracy = share of a Faithful player's votes that landed on a living "
              "Traitor at the time. §5.2's known bias applies: this speech model discards "
              "volume/interruption, so loud archetypes (A02, A07) are under-modelled and "
              "quiet ones (A03, A10) are over-modelled."),
    ))

    # -- standing_wins --
    parts.append("<h2>Traitor deadlock — standing_wins by archetype (§8.2)</h2>")
    if r["standing"]:
        rows = [[f"{a} {ARCHETYPES[a]['name']}", f"{v:,}"] for a, v in r["standing"].most_common()]
        parts.append(table(["Archetype", "standing_wins"], rows,
                            note="Counts how often each archetype's held murder proposal won "
                                 "a §8.2 deadlock by longest standing. A large gap between "
                                 "top and bottom indicates the mechanic has a dominant "
                                 "strategy (hold and don't move)."))
    else:
        parts.append("<p>No forced deadlocks recorded.</p>")

    # -- plate detection --
    parts.append("<h2>Plate detection by archetype (§8.3)</h2>")
    if r["detects"]:
        rows = [[f"{a} {ARCHETYPES[a]['name']}", f"{v:,}", f"{100*v/n:.1f}% of games"]
                for a, v in r["detects"].most_common()]
        parts.append(table(["Archetype", "Detections", "Rate"], rows,
                            note="For this tier, detection is a gated roll on the archetype's "
                                 "`object` parameter (see heuristic_bots.py), not a reasoning "
                                 "trace — a deliberately different mechanism from the Claude "
                                 "tier's reasoning-gated detection. Expect concentration in "
                                 "A06/A12, the two highest-`object` archetypes."))
    else:
        parts.append('<p><span class="pill bad">zero detections</span> — check the `object` '
                      "gate threshold in heuristic_bots.py.</p>")

    # -- float events --
    parts.append("<h2>Float events</h2>")
    float_order = ["ANCHOR_BREAK", "SUCCESSION_ACCEPT", "ZERO_VOTE_COUNCIL"]
    rows = [[k, f"{r['floats'].get(k,0):,}", pct(r["floats"].get(k, 0))] for k in float_order]
    rows.append(["Zero-Traitor sweep (§9.7)", f"{r['zero_traitor_sweep']:,}", pct(r["zero_traitor_sweep"])])
    parts.append(table(["Event", "Games", "Rate"], rows))

    # -- rope + anchor --
    parts.append("<h2>Rope and Anchor</h2>")
    rows = [["Rope raised", f"{r['rope_fired']:,}", pct(r["rope_fired"])]]
    parts.append(table(["Mechanic", "Games", "Rate"], rows))
    if r["anchor_live"]:
        avg = sum(r["anchor_live"]) / len(r["anchor_live"])
        hist = Counter(r["anchor_live"])
        rows = []
        for k in range(5):
            rows.append([str(k), f"{hist.get(k, 0):,}"])
        rows.append(["5+", f"{sum(v for kk, v in hist.items() if kk >= 5):,}"])
        parts.append(table(
            ["Councils before a Traitor learns the Anchor's meaning", "Games"], rows,
            note=f"Mean {avg:.2f} councils across {len(r['anchor_live']):,} games where a "
                 "Traitor learned it at all."))
    else:
        parts.append("<p>No game recorded a Traitor learning the Anchor's meaning.</p>")

    # -- succession --
    parts.append("<h2>Succession</h2>")
    rows = [
        ["Triggered", f"{r['succession_trigger']:,}", pct(r["succession_trigger"])],
        ["Accepted", f"{r['succession_accept']:,}", pct(r["succession_accept"])],
    ]
    parts.append(table(["", "Games", "Rate"], rows))

    # -- REF_ADJUDICATION --
    parts.append("<h2>REF_ADJUDICATION frequency (the bug list)</h2>")
    if r["adjud"]:
        rows = [[k, f"{v:,}", f"{v/n:.2f}/game"] for k, v in r["adjud"].most_common()]
        parts.append(table(["Tag", "Count", "Rate"], rows))
    else:
        parts.append("<p>None.</p>")

    # -- ILLEGAL_ACTION --
    parts.append("<h2>ILLEGAL_ACTION frequency (the ambiguity list)</h2>")
    if r["illegal"]:
        rows = [[k, f"{v:,}", f"{v/n:.2f}/game"] for k, v in r["illegal"].most_common()]
        parts.append(table(["Tag", "Count", "Rate"], rows))
    else:
        parts.append("<p>None.</p>")

    # -- role balance --
    parts.append("<h2>Role balance check</h2>")
    bad_balance = [a for a in ALL_IDS
                   if r["seen"][a][TRAITOR] and
                   abs(r["seen"][a][TRAITOR] / max(1, r["role_games"][a]) - 0.25) > 0.05]
    if bad_balance:
        parts.append(f"<p>Archetypes drawing Traitor away from the ~25% target by more than "
                      f"5 points: {', '.join(bad_balance)}.</p>")
    else:
        parts.append('<p><span class="pill ok">balanced</span> — every archetype drew '
                      "Traitor within 5 points of the 25% target.</p>")

    # -- invariants --
    parts.append("<h2>Invariant check</h2>")
    if ok:
        parts.append('<p><span class="pill ok">zero invariant violations across '
                      f'{n:,} games</span> — run_skeleton.check() ran on every game.</p>')
    else:
        rows = [[k, f"{v:,}"] for k, v in r["violations"].most_common()]
        parts.append(table(["Violation", "Count"], rows))
        if r["failures"]:
            parts.append("<p>First failures:</p><ul>" +
                          "".join(f"<li>game {g}: {esc(msg)}</li>" for g, msg in r["failures"][:20]) +
                          "</ul>")

    header_meta = (f"n = {n:,} games &middot; heuristic bots (zero API calls) &middot; "
                   f"{r['elapsed']:.1f}s wall-clock &middot; "
                   f"generated {datetime.date.today().isoformat()}")
    body = "\n".join(parts)
    doc = html_shell(
        title=f"Lodge structural report ({n} games)",
        favicon_emoji="\U0001F4CA",
        header_title="The Lodge — Structural / Distributional Report",
        header_meta=header_meta,
        body_html=body,
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(doc)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=5000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out_path = args.out or f"reports/structural_{datetime.date.today().isoformat()}.html"

    r = run(args.games)

    pct = lambda x: f"{100 * x / args.games:.1f}%"
    print(f"\n{'='*66}\nSTRUCTURAL RUN — {args.games} games | heuristic bots | "
          f"{r['elapsed']:.1f}s | $0\n{'='*66}\n")
    print("INVARIANT VIOLATIONS")
    print("  none\n" if not r["violations"] else
          "\n".join(f"  {k:40s}{v}" for k, v in r["violations"].most_common()) + "\n")
    print("OUTCOMES")
    for k, v in r["wins"].most_common():
        print(f"  {k:12s}{v:6d}  {pct(v)}")
    print(f"\nreport written to {out_path}\n")

    render_report(r, out_path)
    return r


if __name__ == "__main__":
    main()
