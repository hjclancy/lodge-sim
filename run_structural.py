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

from referee import Referee, PHASES, TRAITOR, FAITHFUL
from council_metrics import CouncilMetrics
from heuristic_bots import HeuristicAgents
from archetypes import (ALL_IDS, ARCHETYPES, PARAM_KEYS, PARAM_OVERRIDES,
                        PARAMS_DIGEST, params_snapshot, params_summary)
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

    elim_cause = defaultdict(Counter)    # phase -> {MURDER/BANISHMENT: n}
    elim_role = defaultdict(Counter)     # phase -> {TRAITOR/FAITHFUL: n}

    council = CouncilMetrics()      # §17 v4 metrics — see council_metrics.py
    anchor_live = []
    succession_trigger = 0
    succession_accept = 0

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
            if tag == "SUCCESSION_ACCEPT":
                succession_accept += 1
        for a in s.adjudications:
            adjud[a["tag"]] += 1
        for il in s.illegal_actions:
            illegal[il["tag"]] += 1

        council.add_game(s)
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
            else:
                if p.role == FAITHFUL and p.eliminated_by == "BANISHMENT":
                    banished_while_faithful[a] += 1
                # eliminated_at/eliminated_by are set by referee.eliminate, so
                # unlike the reasoning report's timeline these are read, not
                # inferred.
                phase = p.eliminated_at or "?"
                elim_cause[phase][p.eliminated_by or "?"] += 1
                elim_role[phase][p.role] += 1

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
        elim_cause=elim_cause, elim_role=elim_role, params=params_snapshot(),
        council=council, anchor_live=anchor_live,
        succession_trigger=succession_trigger, succession_accept=succession_accept,
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
    cm = r["council"]
    fmt_pct = lambda v: "-" if v is None else f"{v:.0f}%"

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
        f'The top nominee was banished in '
        f'{cm.conversion_pct():.0f}% of slate councils. '
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

    # -- banishment accuracy: §17 says run this before any balance change --
    parts.append("<h2>Banishment accuracy as Faithful, per archetype</h2>")
    parts.append(
        '<div class="disclaimer"><strong>Read this before acting on the win split.</strong> '
        'Base rate is 25&ndash;33%: three Traitors among nine to eleven other players. '
        'An archetype <em>below</em> base rate is evidence of a defective parameter '
        'mapping in heuristic_bots.py, not of a game property &mdash; a bot that votes '
        'worse than chance is a bug in the model of that persona. Canon §17 requires this '
        'diagnostic to come back clean before the Traitor/Faithful split (§15 item 5) is '
        'treated as a balance problem.</div>')
    rows = []
    for a in ALL_IDS:
        hits, tot = r["vote_acc"][a]
        nom_hits, nom_tot = cm.nomination_accuracy[a]
        rows.append([
            f"{a} {ARCHETYPES[a]['name']}",
            f"{100*hits/tot:.0f}%" if tot else "-",
            f"{tot:,}",
            f"{100*nom_hits/nom_tot:.0f}%" if nom_tot else "-",
            f"{nom_tot:,}",
        ])
    parts.append(table(
        ["Archetype", "Ballot accuracy", "Ballots cast", "Nomination accuracy",
         "Nominations made"],
        rows,
        note=("Both columns count only Faithful actors, and both count a hit as landing on "
              "a player whose role at end of game was Traitor &mdash; a Successor is "
              "therefore counted a Traitor for the whole game, which at the measured "
              "acceptance rate shifts these by well under a point. Ballot accuracy is now "
              "measured against a two-name slate, so its base rate is structurally higher "
              "than v3's: it is not comparable across canon versions. Nomination accuracy "
              "is the one to compare against the 25–33% base rate."),
    ))

    # -- archetype survival --
    parts.append("<h2>Archetype survival to end, by role</h2>")
    rows = []
    for a in ALL_IDS:
        name = ARCHETYPES[a]["name"]
        sf, st = r["seen"][a][FAITHFUL], r["seen"][a][TRAITOR]
        f_s = f"{100*r['surv'][a][FAITHFUL]/sf:.0f}%" if sf else "-"
        t_s = f"{100*r['surv'][a][TRAITOR]/st:.0f}%" if st else "-"
        bwf = r["banished_while_faithful"].get(a, 0)
        bwf_rate = f"{100*bwf/sf:.0f}%" if sf else "-"
        rows.append([f"{a} {name}", f_s, t_s, bwf_rate])
    parts.append(table(
        ["Archetype", "Faithful survival", "Traitor survival", "Banished while Faithful"],
        rows,
        note=("§5.2's known bias applies: this speech model discards volume and "
              "interruption, so loud archetypes (A02, A07) are under-modelled and quiet "
              "ones (A03, A10) are over-modelled. v4's nomination round is a second, "
              "structured speaking pass that forces every player to commit a public "
              "position, which partially compensates — expect A03 and A10 to move on that "
              "change alone."),
    ))

    # -- the nomination machinery (§5.3, new in v4) --
    parts.append("<h2>Nomination, slate and drop (§5.3)</h2>")
    conv = cm.conversion_pct()
    drop = cm.dropped_traitor_pct()
    rows = [
        ["Councils that produced a slate", f"{cm.conversion[1]:,}",
         f"{cm.conversion[1]/n:.2f}/game"],
        ["Top nominee banished", f"{cm.conversion[0]:,}", fmt_pct(conv)],
        ["Third nominee dropped", f"{cm.dropped[1]:,}", f"{cm.dropped[1]/n:.2f}/game"],
        ["Dropped nominee was a Traitor", f"{cm.dropped[0]:,}", fmt_pct(drop)],
        ["SLATE_TIE_EARLIEST", f"{cm.slate_tie_earliest:,}",
         f"{cm.slate_tie_earliest/n:.2f}/game"],
        ["SLATE_SOLE_NOMINEE", f"{cm.sole_nominee:,}", f"{cm.sole_nominee/n:.2f}/game"],
        ["Defense speeches", f"{cm.defense_rounds:,}", f"{cm.defense_rounds/n:.2f}/game"],
    ]
    parts.append(table(
        ["", "Count", "Rate"], rows,
        note=("Conversion is how often the most-nominated player is the one banished — how "
              "much the nomination round actually decides. The dropped-nominee row is the "
              "cost of the drop: every Traitor in that count was named by the table and "
              "removed from the ballot before anyone could vote on them. Sole-nominee "
              "banishments count as conversions by definition; there is no ballot."),
    ))

    # -- tie ladder (§5.4) --
    parts.append("<h2>Tie ladder (§5.4)</h2>")
    ladder = cm.tie_ladder_rows()
    total_ties = sum(c for _t, c, _p in ladder)
    if total_ties:
        parts.append(table(
            ["Step", "Ties resolved", "Share of ties", "Rate"],
            [[tag, f"{count:,}", fmt_pct(share), f"{count/n:.2f}/game"]
             for tag, count, share in ladder],
            note=("RPS is gone. Steps 1–3 are deterministic and step 3 always resolves, "
                  "because nomination order is a strict total ordering over nominees. "
                  "SMALL_COUNT_TIE_FORCED is the only random elimination left in the "
                  "ruleset and is reachable only below 5 alive, where there is no "
                  "nomination record for steps 2 and 3 to read."),
        ))
    else:
        parts.append("<p>No tied ballots.</p>")

    # -- bloc voting (§5.5) --
    parts.append("<h2>Bloc voting (§5.5)</h2>")
    parts.append(table(
        ["", "Count", "Rate"],
        [["BLOC_BACKSTOP_APPLIED", f"{cm.bloc_backstop:,}", f"{cm.bloc_backstop/n:.2f}/game"],
         ["BLOC_FORCED_BY_MEMBERSHIP", f"{cm.bloc_forced:,}", f"{cm.bloc_forced/n:.2f}/game"],
         ["BLOC_ABSTAINS_BOTH_FINALISTS", f"{cm.bloc_abstain:,}",
          f"{cm.bloc_abstain/n:.2f}/game"]],
        note=("The backstop is how often a bloc failed to reach unanimity in three rounds "
              "and was carried by its longest-standing member. It replaces v3's "
              "ZERO_VOTE_COUNCIL, which lost the vote entirely; a bloc can no longer cast "
              "nothing. BLOC_VOTE_NON_UNANIMOUS is retained in the illegal-action table "
              "as the matching diagnostic and no longer implies a lost vote."),
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
    float_order = ["ANCHOR_BREAK", "SUCCESSION_ACCEPT", "TRAITOR_SWEEP", "SWEEP_NO_MURDER"]
    rows = [[k, f"{r['floats'].get(k,0):,}", pct(r["floats"].get(k, 0))] for k in float_order]
    parts.append(table(["Event", "Games", "Rate"], rows,
                       note=("ZERO_VOTE_COUNCIL is absent because v4 removed it from the "
                             "ruleset (§5.5); any occurrence would be an implementation "
                             "defect and run_skeleton.check asserts its count is zero.")))

    # -- sweep (§9.7) --
    parts.append("<h2>Traitor sweep (§9.7)</h2>")
    mean_after = cm.mean_councils_after_sweep()
    parts.append(table(
        ["", "Games", "Rate"],
        [["Swept to zero living Traitors", f"{cm.sweep_games:,}", pct(cm.sweep_games)],
         ["Murder windows voided by the sweep", f"{r['floats'].get('SWEEP_NO_MURDER', 0):,}",
          f"{r['floats'].get('SWEEP_NO_MURDER', 0)/n:.2f}/game"]],
        note=(("Mean councils played after the sweep: "
               f"{mean_after:.2f}." if mean_after is not None else
               "No game recorded a sweep.")
              + " The game no longer ends at the sweep (v4 §9.7): play continues to RT_6, "
                "every later murder window produces no victim, and the Faithful win is "
                "declared at the finale reveal. The oversized finale that produces is the "
                "intended outcome of the branch, not drift — FINALE_OVERSIZED is "
                "suppressed for these games."),
    ))

    # -- anchor --
    parts.append("<h2>Anchor</h2>")
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

    # -- parameter set --
    parts.append("<h2>Parameter set</h2>")
    p = r["params"]
    if p["overrides"]:
        n_over = len(p["overrides"])
        phrase = ("One parameter was replaced" if n_over == 1
                  else f"{n_over} parameters were replaced")
        parts.append(
            '<p><span class="pill bad">overridden</span> This batch did not run on the '
            f'committed values. {phrase} for this run only, and never written back to '
            "archetypes.json:</p><ul>" +
            "".join(f"<li><code>{esc(c)}</code></li>" for c in p["overrides"]) + "</ul>")
    else:
        parts.append('<p><span class="pill ok">defaults</span> This batch ran on the '
                     "committed archetypes.json with no overrides.</p>")
    parts.append(table(
        ["Archetype"] + list(PARAM_KEYS),
        [[f"{a} {ARCHETYPES[a]['name']}"] + [f"{p['params'][a][k]:g}" for k in PARAM_KEYS]
         for a in ALL_IDS],
        note=(f"Digest {p['digest']}. Two batches with the same digest ran on the same "
              "numbers, whatever archetypes.json said at the time. These values are "
              "heuristic_bots.py's inputs; that file is explicit that its "
              "parameter-to-decision mapping is a modeling choice, so changing a number "
              "here changes what the model does, not what a person with that temperament "
              "would do."),
    ))

    # -- elimination timing --
    parts.append("<h2>Elimination timing</h2>")
    phases = [ph for ph in PHASES if r["elim_cause"].get(ph)]
    if phases:
        rows = []
        for ph in phases:
            c = r["elim_cause"][ph]
            role = r["elim_role"][ph]
            total = sum(c.values())
            rows.append([ph, f"{total:,}", f"{total/n:.2f}",
                         f"{c.get('MURDER', 0):,}", f"{c.get('BANISHMENT', 0):,}",
                         f"{role.get(TRAITOR, 0):,}", f"{role.get(FAITHFUL, 0):,}"])
        parts.append(table(
            ["Phase", "Eliminations", "Per game", "Murdered", "Banished",
             "Were Traitor", "Were Faithful"],
            rows,
            note=("Read from the referee's own eliminated_at/eliminated_by fields, not "
                  "inferred — unlike the reasoning report's timeline, which reconstructs "
                  "this from trace continuity because the event transcript isn't "
                  "persisted."),
        ))
    else:
        parts.append("<p>No eliminations recorded.</p>")

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
                   f"params {esc(params_summary())} &middot; "
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


# ------------------------------------------------------- machine-readable

def report_data(r):
    """The same numbers the HTML shows, in the shape the dashboard charts
    want. Kept next to render_report deliberately: if a series here stops
    matching a table there, the two are meant to be edited together."""
    n = r["n_games"]
    return {
        "schema": 1,
        "kind": "structural",
        "games": n,
        "model": "heuristic-bots",
        "elapsed_s": round(r["elapsed"], 1),
        "params": r["params"],
        "archetypes": [{"id": a, "name": ARCHETYPES[a]["name"]} for a in ALL_IDS],
        "survival": [
            {
                "id": a,
                "faithful_pct": (100.0 * r["surv"][a][FAITHFUL] / r["seen"][a][FAITHFUL]
                                 if r["seen"][a][FAITHFUL] else None),
                "traitor_pct": (100.0 * r["surv"][a][TRAITOR] / r["seen"][a][TRAITOR]
                                if r["seen"][a][TRAITOR] else None),
                "vote_accuracy_pct": (100.0 * r["vote_acc"][a][0] / r["vote_acc"][a][1]
                                      if r["vote_acc"][a][1] else None),
                "banished_while_faithful_pct": (
                    100.0 * r["banished_while_faithful"].get(a, 0) / r["seen"][a][FAITHFUL]
                    if r["seen"][a][FAITHFUL] else None),
            }
            for a in ALL_IDS
        ],
        "elimination_timing": [
            {
                "phase": ph,
                "murdered": r["elim_cause"][ph].get("MURDER", 0),
                "banished": r["elim_cause"][ph].get("BANISHMENT", 0),
                "were_traitor": r["elim_role"][ph].get(TRAITOR, 0),
                "were_faithful": r["elim_role"][ph].get(FAITHFUL, 0),
                "per_game": sum(r["elim_cause"][ph].values()) / n,
            }
            for ph in PHASES if r["elim_cause"].get(ph)
        ],
        "plate_detection": [
            {"id": a, "detections": r["detects"].get(a, 0),
             "per_game": r["detects"].get(a, 0) / n}
            for a in ALL_IDS
        ],
        "float_events": (
            [{"tag": t, "games": r["floats"].get(t, 0), "pct": 100.0 * r["floats"].get(t, 0) / n}
             for t in ("ANCHOR_BREAK", "SUCCESSION_ACCEPT", "TRAITOR_SWEEP",
                       "SWEEP_NO_MURDER")]
        ),
        # §17 v4 series — nomination accuracy, tie ladder, conversion, sweep.
        **r["council"].as_data(ALL_IDS, {a: ARCHETYPES[a]["name"] for a in ALL_IDS}),
        "standing_wins": [{"id": a, "count": r["standing"].get(a, 0)} for a in ALL_IDS],
        "adjudications": [{"tag": k, "count": v, "per_game": v / n}
                          for k, v in r["adjud"].most_common()],
        "illegal_actions": [{"tag": k, "count": v, "per_game": v / n}
                            for k, v in r["illegal"].most_common()],
        "outcomes": {
            "traitor_win_pct": 100.0 * r["wins"].get("TRAITORS", 0) / n,
            "faithful_win_pct": 100.0 * r["wins"].get("FAITHFUL", 0) / n,
            "endings": {k: r["endings"].get(k, 0) for k in ("Final 2", "Final 3", "Final 4+")},
        },
        "invariant_violations": sum(r["violations"].values()),
    }


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
