"""
Skeleton harness. Runs N games with random bots and asserts the
structural invariants from CANON v2 §16 stage 1.
"""

import sys
from collections import Counter
from referee import Referee, TRAITOR, FAITHFUL
from bots import RandomAgents


INVARIANTS = []


def check(state):
    """Returns list of violated invariant names."""
    bad = []
    s = state

    # 1. termination
    if s.phase != "END":
        bad.append("DID_NOT_TERMINATE")

    # 2. no negative / impossible counts
    n = s.n_alive()
    if n < 0 or n > 12:
        bad.append("IMPOSSIBLE_COUNT")

    # 3. anchor blocks at most once
    blocks = len(s.metrics.get("anchor_block", []))
    if blocks > 1:
        bad.append("ANCHOR_BLOCKED_TWICE")

    # 4. rope raises at most once
    ropes = sum(1 for e in s.transcript if e.type == "ROPE_UP")
    if ropes > 1:
        bad.append("ROPE_RAISED_TWICE")

    # 5. no player eliminated twice
    elim = [e.payload["pid"] for e in s.transcript if e.type == "ELIMINATION"]
    if len(elim) != len(set(elim)):
        bad.append("DOUBLE_ELIMINATION")

    # 6. dead never vote
    dead_at = {}
    for e in s.transcript:
        if e.type == "ELIMINATION":
            dead_at[e.payload["pid"]] = e.seq
    for e in s.transcript:
        if e.type in ("VOTE_REVEAL", "FINALE_BALLOT_2"):
            for voter in e.payload["ballots"]:
                if voter in dead_at and dead_at[voter] < e.seq:
                    bad.append("DEAD_VOTED")
                    break

    # 7. traitors never murdered by traitors at placement
    for e in s.transcript:
        if e.type == "MURDER_SELECTED":
            if s.players[e.payload["target"]].role == TRAITOR:
                # legal only if that player became a Successor later
                if not s.successor_created:
                    bad.append("TRAITOR_TARGETED_TRAITOR")

    # 8. per-phase elimination caps (§3)
    caps = {"RT_0": 0, "NIGHT_1": 1, "RT_1": 1, "RT_2": 1, "RT_3": 1,
            "SAT_DINNER": 1, "RT_4": 1, "SUN_TRANSMISSION": 0,
            "RT_5": 1, "NIGHT_3": 2, "RT_6_FINALE": 2}
    per_phase = {}
    for e in s.transcript:
        if e.type == "ELIMINATION":
            per_phase[e.phase] = per_phase.get(e.phase, 0) + 1
    for ph, cnt in per_phase.items():
        if ph not in caps:
            bad.append(f"ELIMINATION_IN_UNEXPECTED_PHASE({ph})")
        elif cnt > caps[ph]:
            bad.append(f"PHASE_CAP_EXCEEDED({ph}:{cnt})")

    # 8b. bookkeeping: alive + eliminated == 12
    if n + len(elim) != 12:
        bad.append("BOOKKEEPING_MISMATCH")

    # 9. ending size explained by float events / early sweep
    swept = any(a["tag"] == "ZERO_TRAITORS_FAITHFUL_WIN" for a in s.adjudications)
    drift = sum(1 for f in s.float_events
                if f["tag"] in ("ZERO_VOTE_COUNCIL", "SUCCESSION_ACCEPT"))
    if not swept:
        # baseline 3, +1 per absorbed drift, +1 if finale chose to end early
        if not (2 <= n <= 3 + drift):
            bad.append(f"ENDING_SIZE_UNEXPLAINED(n={n},drift={drift})")

    # 10. winner determined correctly
    ta = len(s.living_role(TRAITOR))
    expect = "TRAITORS" if ta > 0 else "FAITHFUL"
    if s.winner != expect:
        bad.append("WINNER_MISCOMPUTED")

    return bad


def main(n_games=1000, swap_prob=0.0, coord=0.0, verbose=False):
    wins = Counter()
    endings = Counter()
    floats = Counter()
    adjud = Counter()
    illegal = Counter()
    violations = Counter()
    anchor_blocks = 0
    anchor_live = []
    rope_fired = 0
    succession_trigger = 0
    succession_accept = 0
    plate_swapped = 0
    plate_killed_traitor = 0
    elim_phase = Counter()
    failures = []

    for i in range(n_games):
        agents = RandomAgents(seed=i, swap_prob=swap_prob, coord=coord)
        ref = Referee(agents, seed=i, game_id=i)
        try:
            s = ref.run()
        except Exception as ex:
            failures.append((i, f"{type(ex).__name__}: {ex}"))
            violations["EXCEPTION"] += 1
            continue

        bad = check(s)
        for b in bad:
            violations[b] += 1
            if len(failures) < 10:
                failures.append((i, b))

        wins[s.winner] += 1
        endings[s.n_alive()] += 1
        for f in s.float_events:
            floats[f["tag"]] += 1
        for a in s.adjudications:
            adjud[a["tag"]] += 1
        for il in s.illegal_actions:
            illegal[il["tag"]] += 1
        anchor_blocks += len(s.metrics.get("anchor_block", []))
        if s.anchor_live_councils is not None:
            anchor_live.append(s.anchor_live_councils)
        if any(e.type == "ROPE_UP" for e in s.transcript):
            rope_fired += 1
        succession_trigger += len(s.metrics.get("succession_trigger", []))
        succession_accept += len(s.metrics.get("succession_accept", []))
        plate_swapped += sum(s.metrics.get("plate_swapped", []))
        plate_killed_traitor += len(s.metrics.get("plate_killed_traitor", []))
        for p in s.players.values():
            if not p.alive:
                elim_phase[p.eliminated_at] += 1

    pct = lambda x: f"{100*x/n_games:5.1f}%"

    print(f"\n{'='*62}")
    print(f"SKELETON RUN — {n_games} games | swap_prob={swap_prob} | coord={coord}")
    print(f"{'='*62}\n")

    print("INVARIANT VIOLATIONS")
    if not violations:
        print("  none — all invariants held\n")
    else:
        for k, v in violations.most_common():
            print(f"  {k:45s} {v:5d}  {pct(v)}")
        print()
        for gid, msg in failures[:10]:
            print(f"    game {gid}: {msg}")
        print()

    print("OUTCOMES")
    for k, v in wins.most_common():
        print(f"  {k:20s} {v:5d}  {pct(v)}")
    print()

    print("ENDING SIZE (players alive at END)")
    for k in sorted(endings):
        print(f"  Final {k:<14d} {endings[k]:5d}  {pct(endings[k])}")
    print()

    print("FLOAT EVENTS")
    if not floats:
        print("  none")
    for k, v in floats.most_common():
        print(f"  {k:35s} {v:5d}  {pct(v)}")
    print()

    print("MECHANIC FIRING RATES")
    print(f"  rope raised                         {rope_fired:5d}  {pct(rope_fired)}")
    print(f"  anchor blocked a murder             {anchor_blocks:5d}  {pct(anchor_blocks)}")
    if anchor_live:
        avg = sum(anchor_live) / len(anchor_live)
        print(f"  anchor meaning leaked to a Traitor  {len(anchor_live):5d}  {pct(len(anchor_live))}"
              f"   (mean council {avg:.2f})")
    else:
        print("  anchor meaning leaked to a Traitor      0")
    print(f"  succession triggered                {succession_trigger:5d}  {pct(succession_trigger)}")
    print(f"  succession accepted                 {succession_accept:5d}  {pct(succession_accept)}")
    print(f"  plate swapped                       {plate_swapped:5d}  {pct(plate_swapped)}")
    print(f"  plate swap killed a Traitor         {plate_killed_traitor:5d}  {pct(plate_killed_traitor)}")
    print()

    print("REF_ADJUDICATION FREQUENCY  (the bug list)")
    for k, v in adjud.most_common():
        print(f"  {k:40s} {v:6d}  {v/n_games:6.2f}/game")
    print()

    print("ILLEGAL_ACTION FREQUENCY  (the ambiguity list)")
    if not illegal:
        print("  none")
    for k, v in illegal.most_common():
        print(f"  {k:40s} {v:6d}  {v/n_games:6.2f}/game")
    print()

    print("ELIMINATION TIMING")
    order = ["NIGHT_1", "RT_1", "RT_2", "RT_3", "SAT_DINNER", "RT_4",
             "RT_5", "NIGHT_3", "RT_6_FINALE"]
    for k in order:
        if k in elim_phase:
            print(f"  {k:15s} {elim_phase[k]:6d}")
    for k in elim_phase:
        if k not in order:
            print(f"  {k:15s} {elim_phase[k]:6d}  <-- unexpected phase")
    print()

    return violations


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    sp = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    cd = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    v = main(n, sp, cd)
    sys.exit(1 if v else 0)
