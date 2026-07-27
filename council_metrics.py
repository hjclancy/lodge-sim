"""§17 report metrics that read the v4 council structure.

Both aggregate harnesses feed the same accumulator, so the structural and
reasoning reports cannot drift on what "nomination accuracy" or "conversion"
means. Everything here is derived from the public transcript — the nomination
record, the slate, the drop, the ballots — plus the final role table, which is
what the referee reveals on elimination anyway.

**Role is read at end of game, not at the moment of the nomination.** This is
the same approximation the existing vote-accuracy figure makes, and it matters
in exactly one place: a Successor (§9.4) spent most of the game Faithful and
is counted a Traitor throughout. At the measured ~13% acceptance rate that
shifts these figures by well under a point, but it is an approximation and not
a fact about the game.
"""

from collections import Counter, defaultdict

from referee import TRAITOR, FAITHFUL

TIE_LADDER_TAGS = ("TIE_LADDER_STEP_1", "TIE_LADDER_STEP_2", "TIE_LADDER_STEP_3",
                   "SMALL_COUNT_TIE_FORCED")


class CouncilMetrics:
    """Accumulates across games. Call add_game(state) once per completed game."""

    def __init__(self):
        self.games = 0
        # archetype -> [nominations landing on a Traitor, nominations made]
        self.nomination_accuracy = defaultdict(lambda: [0, 0])
        # [top nominee was banished, councils that produced a slate]
        self.conversion = [0, 0]
        # [dropped third was a Traitor, drops]
        self.dropped = [0, 0]
        self.tie_steps = Counter()
        self.sole_nominee = 0
        self.slate_tie_earliest = 0
        self.bloc_backstop = 0
        self.bloc_forced = 0
        self.bloc_abstain = 0
        self.sweep_games = 0
        self.councils_after_sweep = []
        self.defense_rounds = 0

    def add_game(self, s):
        self.games += 1
        traitor_ids = {p.pid for p in s.players.values() if p.role == TRAITOR}

        # --- nomination accuracy, Faithful nominators only ---
        # Restricted to Faithful for the same reason banishment accuracy is:
        # a Traitor naming a non-Traitor is playing correctly, so mixing the
        # two produces a number that measures nothing.
        for ev in s.transcript:
            if ev.type != "NOMINATION":
                continue
            nominator = ev.actor
            if nominator not in s.players or s.players[nominator].role != FAITHFUL:
                continue
            arch = s.players[nominator].archetype
            self.nomination_accuracy[arch][1] += 1
            if ev.payload["nominee"] in traitor_ids:
                self.nomination_accuracy[arch][0] += 1

        # --- conversion, drops, defenses ---
        banished_at = {}
        for ev in s.transcript:
            if ev.type == "ELIMINATION" and ev.payload["how"] == "BANISHMENT":
                banished_at[ev.phase] = ev.payload["pid"]

        for ev in s.transcript:
            if ev.type == "SLATE_SET":
                # finalists[0] is the top nominee: the slate is ranked by count
                # descending, ties to earliest nomination (referee §5.3.2).
                self.conversion[1] += 1
                if banished_at.get(ev.phase) == ev.payload["finalists"][0]:
                    self.conversion[0] += 1
                if ev.payload.get("dropped"):
                    self.dropped[1] += 1
                    if ev.payload["dropped"] in traitor_ids:
                        self.dropped[0] += 1
            elif ev.type == "SLATE_SOLE_NOMINEE":
                # Unanimity is conversion by definition — there is no ballot.
                self.conversion[0] += 1
                self.conversion[1] += 1
                self.sole_nominee += 1
            elif ev.type == "DEFENSE":
                self.defense_rounds += 1

        for a in s.adjudications:
            tag = a["tag"]
            if tag in TIE_LADDER_TAGS:
                self.tie_steps[tag] += 1
            elif tag == "SLATE_TIE_EARLIEST":
                self.slate_tie_earliest += 1
            elif tag == "BLOC_BACKSTOP_APPLIED":
                self.bloc_backstop += 1
            elif tag == "BLOC_FORCED_BY_MEMBERSHIP":
                self.bloc_forced += 1
            elif tag == "BLOC_ABSTAINS_BOTH_FINALISTS":
                self.bloc_abstain += 1

        # --- sweep (§9.7) ---
        if s.sweep_active:
            self.sweep_games += 1
            at = s.metrics.get("sweep_at_council")
            if at:
                self.councils_after_sweep.append(s.councils_held - at[0])

    # ---------------------------------------------------------- readouts

    def accuracy_rows(self, all_ids, names):
        """[(archetype id, label, pct or None, sample size)] in canonical order."""
        rows = []
        for aid in all_ids:
            hits, total = self.nomination_accuracy[aid]
            rows.append((aid, names[aid],
                         (100.0 * hits / total) if total else None, total))
        return rows

    def conversion_pct(self):
        hits, total = self.conversion
        return (100.0 * hits / total) if total else None

    def dropped_traitor_pct(self):
        hits, total = self.dropped
        return (100.0 * hits / total) if total else None

    def mean_councils_after_sweep(self):
        if not self.councils_after_sweep:
            return None
        return sum(self.councils_after_sweep) / len(self.councils_after_sweep)

    def tie_ladder_rows(self):
        """[(tag, count, share of resolved ties)] — the distribution §17 wants."""
        total = sum(self.tie_steps.values())
        return [(tag, self.tie_steps.get(tag, 0),
                 (100.0 * self.tie_steps.get(tag, 0) / total) if total else None)
                for tag in TIE_LADDER_TAGS]

    def as_data(self, all_ids, names):
        """The machine-readable shape the dashboard charts read."""
        return {
            "nomination_accuracy": [
                {"id": aid, "name": names[aid],
                 "pct": self._acc(aid)[0], "n": self._acc(aid)[1]}
                for aid in all_ids
            ],
            "tie_ladder": [
                {"tag": tag, "count": count, "pct": pct}
                for tag, count, pct in self.tie_ladder_rows()
            ],
            "conversion_pct": self.conversion_pct(),
            "dropped_traitor_pct": self.dropped_traitor_pct(),
            "dropped_total": self.dropped[1],
            "sole_nominee": self.sole_nominee,
            "slate_tie_earliest": self.slate_tie_earliest,
            "bloc_backstop": self.bloc_backstop,
            "bloc_forced": self.bloc_forced,
            "bloc_abstain": self.bloc_abstain,
            "sweep_games": self.sweep_games,
            "mean_councils_after_sweep": self.mean_councils_after_sweep(),
        }

    def _acc(self, aid):
        hits, total = self.nomination_accuracy[aid]
        return ((100.0 * hits / total) if total else None), total
