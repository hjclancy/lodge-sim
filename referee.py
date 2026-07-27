"""
The Lodge — referee engine.
Implements REFEREE CANON v4. The referee decides; agents only choose.

Every agent return value is validated here before it touches state.
Nothing in this file may be overridden by an agent.

v4 changes (see referee_canon_v4.md §0):
  1. Councils gain a nomination round and a defense round; the ballot is
     restricted to two finalists (§5.1, §5.3).
  2. RPS is deleted. Ties resolve on a deterministic ladder (§5.4).
  3. Blocs vote from the slate and can never cast nothing (§5.5).
  4. Succession acceptance owes a make-up elimination at NIGHT_3 (§9.6).
  5. A zero-Traitor sweep no longer ends the game (§9.7).

Note on a convention this file keeps: §1 specifies reject → log → re-prompt
once → coerce. This engine has always coerced on the first invalid response
rather than re-prompting, in every phase. v4 does not change that; the new
nomination and defense paths follow the same convention as the old vote and
murder paths so the ILLEGAL_ACTION frequency table stays comparable across
versions. Re-prompting is a separate change to make everywhere at once.
"""

from dataclasses import dataclass, field
from typing import Optional, Any
import random

FAITHFUL = "FAITHFUL"
TRAITOR = "TRAITOR"

PHASES = [
    "SETUP", "THU_ARRIVAL", "COCKTAIL_HOUR", "RT_0", "NIGHT_1", "FRI_DISCOVERY",
    "RT_1", "RT_2", "RT_3", "SAT_AFTERNOON", "SAT_DINNER", "RT_4",
    "SUN_TRANSMISSION", "RT_5", "NIGHT_3", "RT_6_FINALE", "END",
]

ANCHOR_PASS_COUNCILS = {"RT_0", "RT_1", "RT_2", "RT_3"}
MURDER_WINDOWS = {"NIGHT_1", "SAT_DINNER", "NIGHT_3"}

# §5.3.1 — the nomination round runs at these councils and only when
# alive >= 5. RT_0 has no vote at all; RT_6 is exempt by name (§5.3.5) so
# that drift can never introduce a nomination round into the finale.
NOMINATION_COUNCILS = {"RT_1", "RT_2", "RT_3", "RT_4", "RT_5"}
NOMINATION_MIN_ALIVE = 5

# §5.4 — the small-count ladder is step 1 repeated. After this many failed
# revotes the tie resolves at random. This is the only random elimination
# left in the ruleset and is reachable only below NOMINATION_MIN_ALIVE.
SMALL_COUNT_REVOTES = 3

PLATE_SET = (["ice_axes"] * 3 + ["knotted_rope"] * 3 + ["signal_flags"] * 3
             + ["storm_lantern"] * 2 + ["cairn"])

TRANSMISSION_QUESTIONS = [
    "Who feels the safest right now?",
    "Who is playing the game the worst so far?",
    "Who is being trusted too easily?",
    "Who is playing the game the best so far?",
    "Who were you right about?",
    "Who were you wrong about?",
    "Who does not deserve to win?",
]


@dataclass
class Player:
    pid: str
    archetype: str
    role: str
    alive: bool = True
    eliminated_by: Optional[str] = None
    eliminated_at: Optional[str] = None
    bloc: Optional[int] = None
    will: Optional[str] = None


@dataclass
class Event:
    seq: int
    phase: str
    type: str
    actor: Optional[str]
    payload: dict
    visible_to: Any  # "ALL" | "TRAITORS" | "DEAD" | "BLOC:n" | [pids]


@dataclass
class GameState:
    game_id: int
    seed: int
    rules_version: str = "canon_v4"
    phase: str = "SETUP"
    players: dict = field(default_factory=dict)
    transcript: list = field(default_factory=list)

    anchor_holder: Optional[str] = None
    anchor_in_play: bool = False
    anchor_broken: bool = False
    anchor_rescinded: bool = False
    knows_anchor_meaning: set = field(default_factory=set)
    anchor_live_councils: Optional[int] = None  # councils before a Traitor knows

    rope_raised: bool = False
    rope_active: bool = False
    rope_spans_murder_window: bool = False
    rope_span_council: Optional[str] = None
    blocs: dict = field(default_factory=dict)  # bloc_id -> [pid]

    # Make-up eliminations owed at NIGHT_3 (§3.3, §8.4). Two independent
    # debts as of v4 — the Anchor's block and a Succession acceptance can
    # both be outstanding in the same game.
    anchor_makeup_owed: bool = False
    succession_makeup_owed: bool = False

    # §9.7 — set when living Traitors hit zero. The game does NOT end; every
    # later murder window produces no victim and the Faithful win is declared
    # at the finale reveal.
    sweep_active: bool = False

    # §5.3 — the current council's nomination round. Reset at the top of
    # every council. {nominator: (nominee, order_index)}; order_index is the
    # tiebreak resource for §5.3.2 and §5.4. The durable public record lives
    # in the transcript as NOMINATION events (§13.1).
    nominations: dict = field(default_factory=dict)
    slate: list = field(default_factory=list)          # the 2 finalists
    dropped_nominee: Optional[str] = None              # the named third

    first_successful_murder_done: bool = False
    successor_created: bool = False

    councils_held: int = 0
    winner: Optional[str] = None
    ended_at_count: Optional[int] = None

    adjudications: list = field(default_factory=list)
    illegal_actions: list = field(default_factory=list)
    float_events: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    _seq: int = 0

    # ---------- helpers ----------
    def living(self):
        return [p for p in self.players.values() if p.alive]

    def living_ids(self):
        return [p.pid for p in self.living()]

    def living_role(self, role):
        return [p for p in self.living() if p.role == role]

    def dead(self):
        return [p for p in self.players.values() if not p.alive]

    def n_alive(self):
        return len(self.living())

    def log(self, etype, payload=None, actor=None, visible_to="ALL"):
        self._seq += 1
        e = Event(self._seq, self.phase, etype, actor, payload or {}, visible_to)
        self.transcript.append(e)
        return e

    def adjudicate(self, tag, detail=""):
        self.adjudications.append({"phase": self.phase, "tag": tag, "detail": detail})
        self.log("REF_ADJUDICATION", {"tag": tag, "detail": detail}, visible_to=[])

    def illegal(self, tag, actor=None, detail=""):
        self.illegal_actions.append({"phase": self.phase, "tag": tag,
                                     "actor": actor, "detail": detail})
        self.log("ILLEGAL_ACTION", {"tag": tag, "detail": detail},
                 actor=actor, visible_to=[])

    def float_event(self, tag, detail=""):
        self.float_events.append({"phase": self.phase, "tag": tag, "detail": detail})
        self.log("FLOAT_EVENT", {"tag": tag, "detail": detail}, visible_to=[])

    def metric(self, key, value):
        self.metrics.setdefault(key, []).append(value)


# =====================================================================
# REFEREE
# =====================================================================

class Referee:
    def __init__(self, agents, seed=0, game_id=0, archetypes=None):
        self.agents = agents          # object implementing the agent protocol
        self.rng = random.Random(seed)
        self.state = GameState(game_id=game_id, seed=seed)
        self.archetypes = archetypes

    # ---------------- setup ----------------
    def setup(self):
        s = self.state
        s.phase = "SETUP"
        pids = [f"P{i:02d}" for i in range(1, 13)]
        roles = [TRAITOR] * 3 + [FAITHFUL] * 9
        self.rng.shuffle(roles)
        arch = self.archetypes or ["random"] * 12
        for pid, role, a in zip(pids, roles, arch):
            s.players[pid] = Player(pid=pid, archetype=a, role=role)
        s.log("ROLES_ASSIGNED",
              {"traitors": [p.pid for p in s.players.values() if p.role == TRAITOR]},
              visible_to="TRAITORS")

    # ---------------- elimination ----------------
    def eliminate(self, pid, how):
        s = self.state
        p = s.players[pid]
        if not p.alive:
            s.adjudicate("DOUBLE_ELIMINATION", f"{pid} already dead")
            return
        p.alive = False
        p.eliminated_by = how
        p.eliminated_at = s.phase
        s.log("ELIMINATION", {"pid": pid, "how": how, "role": p.role})

        # Anchor holder banished: they make the pass on the way out (§6.3 gap).
        if pid == s.anchor_holder and how == "BANISHMENT" and s.anchor_in_play:
            s.adjudicate("ANCHOR_HOLDER_BANISHED",
                         "holder passes as final act before leaving play")

    # ---------------- anchor ----------------
    def assign_anchor(self):
        s = self.state
        s.phase = "COCKTAIL_HOUR"
        faithful = [p.pid for p in s.living_role(FAITHFUL)]
        holder = self.rng.choice(faithful)
        s.anchor_holder = holder
        s.anchor_in_play = True
        s.knows_anchor_meaning.add(holder)
        s.log("ANCHOR_ASSIGNED", {"pid": holder}, visible_to=[holder])

    def anchor_pass(self):
        """Conclusion of RT_0..RT_3. Public. Holder chooses; must not self-retain."""
        s = self.state
        if not s.anchor_in_play or s.anchor_broken or s.anchor_rescinded:
            return
        holder = s.anchor_holder
        candidates = [pid for pid in s.living_ids() if pid != holder]
        if not candidates:
            s.adjudicate("ANCHOR_NO_PASS_TARGET")
            return

        choice = self.agents.anchor_pass(s, holder, candidates)
        if choice not in candidates:
            s.illegal("ANCHOR_SELF_RETAIN", actor=holder, detail=str(choice))
            choice = self.rng.choice(candidates)

        s.anchor_holder = choice
        s.knows_anchor_meaning.add(choice)
        s.log("ANCHOR_PASS",
              {"from": holder, "to": choice,
               "from_role": s.players[holder].role,
               "to_role": s.players[choice].role})
        self._check_anchor_knowledge()

    def _check_anchor_knowledge(self):
        """Record how many councils elapse before any Traitor knows the meaning."""
        s = self.state
        if s.anchor_live_councils is not None:
            return
        for pid in s.knows_anchor_meaning:
            if s.players[pid].role == TRAITOR:
                s.anchor_live_councils = s.councils_held
                s.log("ANCHOR_MEANING_LEAKED", {"pid": pid}, visible_to="TRAITORS")
                return

    def anchor_blocks(self, victim_pid):
        """True if the murder is voided. Breaks and exits the token."""
        s = self.state
        if not (s.anchor_in_play and not s.anchor_broken and not s.anchor_rescinded):
            return False
        if victim_pid != s.anchor_holder:
            return False
        s.anchor_broken = True
        s.anchor_in_play = False
        s.anchor_makeup_owed = True
        s.float_event("ANCHOR_BREAK", f"blocked murder of {victim_pid}")
        s.log("ANCHOR_BLOCK", {"pid": victim_pid}, visible_to="TRAITORS")
        s.metric("anchor_block", 1)
        return True

    def rescind_anchor(self):
        s = self.state
        if s.anchor_in_play and not s.anchor_broken:
            s.anchor_rescinded = True
            s.anchor_in_play = False
            s.log("ANCHOR_RESCINDED", {"last_holder": s.anchor_holder})

    # ---------------- rope ----------------
    def rope_check(self, after_phase):
        s = self.state
        if s.rope_raised or s.n_alive() != 9:
            return
        s.rope_raised = True
        s.rope_active = True
        # Rope raised after RT_2 spans RT_3 (no murder window inside).
        # Rope raised after RT_3 spans SAT_DINNER and RT_4 (murder window inside).
        if after_phase == "RT_2":
            s.rope_span_council = "RT_3"
            s.rope_spans_murder_window = False
        else:
            s.rope_span_council = "RT_4"
            s.rope_spans_murder_window = True
        self.assign_blocs()
        s.log("ROPE_UP", {"spans": s.rope_span_council,
                          "murder_window": s.rope_spans_murder_window,
                          "blocs": {k: v for k, v in s.blocs.items()}})

    def assign_blocs(self):
        """Runner assigns. §7.2 default, §7.3 override when spanning a murder window."""
        s = self.state
        traitors = [p.pid for p in s.living_role(TRAITOR)]
        faithful = [p.pid for p in s.living_role(FAITHFUL)]
        self.rng.shuffle(faithful)
        blocs = {0: [], 1: [], 2: []}

        if s.rope_spans_murder_window:
            # §7.3 — all living Traitors in one bloc, padded with Faithful.
            blocs[0] = list(traitors)
            while len(blocs[0]) < 3 and faithful:
                blocs[0].append(faithful.pop())
            idx = 1
            while faithful:
                if len(blocs[idx]) >= 3:
                    idx += 1
                if idx > 2:
                    break
                blocs[idx].append(faithful.pop())
            s.adjudicate("ROPE_TRAITOR_BLOC_OVERRIDE",
                         f"{len(traitors)} traitors in one bloc")
        else:
            # §7.2 — 3F / 2F+1T / 1F+2T with 3 traitors; else max 1 per bloc.
            if len(traitors) >= 3:
                blocs[1] = [traitors[0]]
                blocs[2] = [traitors[1], traitors[2]]
            else:
                for i, t in enumerate(traitors):
                    blocs[(i % 2) + 1].append(t)
            for b in (0, 1, 2):
                while len(blocs[b]) < 3 and faithful:
                    blocs[b].append(faithful.pop())

        leftover = faithful
        if leftover:
            s.adjudicate("ROPE_REMAINDER", f"{len(leftover)} unroped")
        s.blocs = blocs
        for bid, members in blocs.items():
            for pid in members:
                s.players[pid].bloc = bid

    def unrope(self):
        s = self.state
        if not s.rope_active:
            return
        s.rope_active = False
        for p in s.players.values():
            p.bloc = None
        s.log("UNROPE", {})

    # ---------------- councils ----------------
    def council(self, name, voting=True):
        """§5.1 — prompt, discussion, nomination, slate, defense, vote,
        banishment, Anchor pass."""
        s = self.state
        s.phase = name
        s.councils_held += 1
        s.nominations = {}
        s.slate = []
        s.dropped_nominee = None

        prompt = self.agents.council_prompt(s)
        s.log("COUNCIL_PROMPT", {"prompt": prompt})

        # single randomized speaking pass (§5.2)
        order = s.living_ids()[:]
        self.rng.shuffle(order)
        for pid in order:
            speech = self.agents.speak(s, pid)
            s.log("SPEAK", {"text": speech}, actor=pid)

        banished = None
        if voting:
            roped_here = s.rope_active and s.rope_span_council == name
            if name in NOMINATION_COUNCILS and s.n_alive() >= NOMINATION_MIN_ALIVE:
                self.nomination_round()
                sole = self.resolve_slate()
                if sole is not None:
                    # §5.3.2 — unanimous nomination banishes with no defense
                    # and no ballot. Cannot produce count drift.
                    banished = sole
                else:
                    self.defense_round()
                    banished = (self.bloc_vote(s.slate) if roped_here
                                else self.standard_vote(s.slate))
            else:
                # §5.3.5 small-count exemption. RT_0 never reaches here
                # (voting=False) and RT_6 runs through finale().
                s.adjudicate("NOMINATION_EXEMPT_SMALL_COUNT",
                             f"{s.n_alive()} alive at {name}")
                banished = (self.bloc_vote(None) if roped_here
                            else self.standard_vote(None))
            if banished:
                self.eliminate(banished, "BANISHMENT")

        # anchor pass (§6.3)
        if name in ANCHOR_PASS_COUNCILS:
            self.anchor_pass()

        if name == "RT_4":
            self.rescind_anchor()

        # unrope at conclusion of the spanned council, banishment or not (§7.6)
        if s.rope_active and s.rope_span_council == name:
            self.unrope()

        return banished

    # ---------------- nomination, slate, defense (§5.3) ----------------
    def nomination_round(self):
        """§5.3.1. Sequential and spoken, in a per-council randomized order
        that is logged. Every living player names exactly one other living
        player, seeing every nomination made before theirs."""
        s = self.state
        order = s.living_ids()[:]
        self.rng.shuffle(order)
        s.log("NOMINATION_ORDER", {"order": list(order)})

        # Assigned before the loop, not after: agents read prior nominations
        # off this dict during the round, and the round is sequential
        # precisely so that they can.
        record = {}
        s.nominations = record

        for idx, pid in enumerate(order):
            legal = [x for x in s.living_ids() if x != pid]
            if not legal:
                s.adjudicate("NO_LEGAL_NOMINEE", pid)
                continue
            pick = self.agents.nominate(s, pid, legal)
            if pick == pid:
                s.illegal("SELF_NOMINATE", actor=pid)
                pick = self.rng.choice(legal)
            elif pick not in legal:
                if pick is None:
                    s.illegal("ABSTENTION", actor=pid)
                elif pick in s.players and not s.players[pick].alive:
                    s.illegal("DEAD_NOMINATE", actor=pid, detail=str(pick))
                else:
                    s.illegal("MALFORMED_OUTPUT", actor=pid, detail=f"nominate {pick}")
                pick = self.rng.choice(legal)
            record[pid] = (pick, idx)
            # Public and durable (§13.1) — who named whom, in what order.
            s.log("NOMINATION", {"nominee": pick, "order": idx}, actor=pid)

    def _nomination_stats(self):
        """-> (counts, earliest). `earliest[n]` is the order index of the
        first player to name n, which is a strict total order over nominees:
        each nominator names exactly one, so no two nominees can share it.
        That is what makes §5.4 step 3 always resolve."""
        counts, earliest = {}, {}
        for _nominator, (nominee, idx) in self.state.nominations.items():
            counts[nominee] = counts.get(nominee, 0) + 1
            if nominee not in earliest or idx < earliest[nominee]:
                earliest[nominee] = idx
        return counts, earliest

    def resolve_slate(self):
        """§5.3.2. Sets state.slate to the 2 finalists and returns None, or
        returns a player id to banish immediately (sole-nominee case)."""
        s = self.state
        counts, earliest = self._nomination_stats()
        if not counts:
            s.adjudicate("NO_NOMINATIONS_RECORDED")
            s.slate = []
            return None

        # Ties for any position resolve to the earliest-nominated player.
        ranked = sorted(counts, key=lambda n: (-counts[n], earliest[n]))

        if len(ranked) == 1:
            sole = ranked[0]
            s.adjudicate("SLATE_SOLE_NOMINEE", f"{sole} named by every player")
            s.log("SLATE_SOLE_NOMINEE", {"pid": sole, "nominations": counts[sole]})
            s.metric("slate_sole_nominee", 1)
            s.slate = [sole]
            return sole

        if len(ranked) == 2:
            s.slate = ranked[:2]
            s.adjudicate("SLATE_ONLY_TWO", "no drop occurred")
            s.log("SLATE_SET", {"finalists": list(s.slate), "dropped": None,
                                "counts": {k: counts[k] for k in ranked[:2]}})
            return None

        provisional = ranked[:3]
        dropped = provisional[2]
        # The tie only matters where it changes the slate or the drop: at the
        # 2/3 boundary (who is dropped) or the 3/4 boundary (who is in).
        contested = (counts[dropped] == counts[provisional[1]]
                     or (len(ranked) > 3 and counts[dropped] == counts[ranked[3]]))
        if contested:
            s.adjudicate("SLATE_TIE_EARLIEST",
                         f"{dropped} dropped on earliest-nomination order")
            s.metric("slate_tie_earliest", 1)

        s.dropped_nominee = dropped
        s.slate = provisional[:2]
        # Named aloud before removal (§5.3.2). Role is deliberately absent:
        # this event is visible to everyone and being dropped reveals nothing.
        s.log("SLATE_DROP", {"pid": dropped, "nominations": counts[dropped]})
        s.log("SLATE_SET", {"finalists": list(s.slate), "dropped": dropped,
                            "counts": {k: counts[k] for k in provisional}})
        return None

    def defense_round(self):
        """§5.3.3. The two finalists speak once each, earlier-nominated first."""
        s = self.state
        _counts, earliest = self._nomination_stats()
        for pid in sorted(s.slate, key=lambda p: earliest.get(p, 10 ** 6)):
            text = self.agents.defend(s, pid)
            s.log("DEFENSE", {"text": text}, actor=pid)

    def _cast_ballot(self, pid, legal, slate_mode, context=""):
        """One validated ballot. `legal` already excludes the voter, so a
        finalist voting under a slate has exactly one legal choice: the other
        finalist. They therefore cancel and the rest of the table decides."""
        s = self.state
        choice = self.agents.vote(s, pid, legal)
        if choice == pid:
            s.illegal("SELF_VOTE", actor=pid, detail=context)
        elif choice not in legal:
            if choice is None:
                s.illegal("ABSTENTION", actor=pid, detail=context)
            elif choice in s.players and not s.players[choice].alive:
                s.illegal("DEAD_VOTE", actor=pid, detail=str(choice))
            elif slate_mode:
                s.illegal("VOTE_OFF_SLATE", actor=pid, detail=str(choice))
            else:
                s.illegal("MALFORMED_OUTPUT", actor=pid, detail=str(choice))
        else:
            return choice
        return self.rng.choice(legal)

    def standard_vote(self, targets=None):
        """§5.3.4. `targets` is the slate when one exists; None means the
        small-count exemption (§5.3.5) and every living player is a legal
        target."""
        s = self.state
        voters = s.living_ids()
        pool = list(targets) if targets else voters
        ballots = {}
        for pid in voters:
            legal = [x for x in pool if x != pid]
            if not legal:
                s.adjudicate("NO_LEGAL_VOTE_TARGET", pid)
                continue
            ballots[pid] = self._cast_ballot(pid, legal, targets is not None)
        s.log("VOTE_REVEAL", {"ballots": dict(ballots),
                              "slate": list(targets) if targets else None})
        return self.resolve_vote(ballots, voters, targets)

    def resolve_vote(self, ballots, voters, targets):
        """Plurality of the cast ballots, then §5.4's ladder."""
        s = self.state
        tally = {}
        for v in ballots.values():
            tally[v] = tally.get(v, 0) + 1
        if not tally:
            return None
        top = max(tally.values())
        tied = [k for k, v in tally.items() if v == top]
        if len(tied) == 1:
            return tied[0]

        if targets is not None:
            if len(tied) > 2:
                # Structurally impossible on a two-name ballot. If this ever
                # fires the slate leaked; §17 asserts the count is zero.
                s.adjudicate("THREE_WAY_TIE", f"{len(tied)} tied on a slate ballot")
            return self._slate_tie_ladder(tied, voters)
        return self._small_count_tie(tied, voters)

    def _slate_tie_ladder(self, tied, voters):
        """§5.4. Stop at the first step that breaks the tie. Step 3 always
        resolves, so this never returns None and never rolls a die."""
        s = self.state

        # Step 1 — second discussion round (everyone but the finalists), then
        # a revote. Skipped at a roped council: there is no individual ballot
        # to re-cast without dissolving the blocs, and steps 2 and 3 resolve
        # deterministically anyway.
        roped_here = s.rope_active and s.rope_span_council == s.phase
        if not roped_here:
            for pid in [p for p in voters if p not in tied]:
                s.log("SPEAK", {"text": self.agents.speak(s, pid),
                                "context": "tie_break"}, actor=pid)
            rb = {}
            for pid in voters:
                legal = [x for x in tied if x != pid]
                if not legal:
                    continue
                rb[pid] = self._cast_ballot(pid, legal, True, context="revote")
            s.log("REVOTE_REVEAL", {"ballots": dict(rb), "candidates": list(tied)})
            t2 = {}
            for v in rb.values():
                t2[v] = t2.get(v, 0) + 1
            if t2:
                top2 = max(t2.values())
                tied2 = [k for k, v in t2.items() if v == top2]
                if len(tied2) == 1:
                    s.adjudicate("TIE_LADDER_STEP_1", "revote after discussion")
                    s.metric("tie_ladder_step", 1)
                    return tied2[0]

        counts, earliest = self._nomination_stats()

        # Step 2 — higher nomination count carries.
        by_count = sorted(tied, key=lambda p: -counts.get(p, 0))
        if counts.get(by_count[0], 0) != counts.get(by_count[1], 0):
            s.adjudicate("TIE_LADDER_STEP_2",
                         f"{by_count[0]} had more nominations")
            s.metric("tie_ladder_step", 2)
            return by_count[0]

        # Step 3 — earliest nomination carries. Always resolves.
        by_early = sorted(tied, key=lambda p: earliest.get(p, 10 ** 6))
        s.adjudicate("TIE_LADDER_STEP_3", f"{by_early[0]} nominated earliest")
        s.metric("tie_ladder_step", 3)
        return by_early[0]

    def _small_count_tie(self, tied, voters):
        """§5.4 under the small-count exemption: no nomination record, so the
        ladder collapses to step 1 repeated. After three revotes, resolve at
        random — the only random elimination left in the ruleset."""
        s = self.state
        for _attempt in range(SMALL_COUNT_REVOTES):
            for pid in [p for p in voters if p not in tied]:
                s.log("SPEAK", {"text": self.agents.speak(s, pid),
                                "context": "tie_break"}, actor=pid)
            rb = {}
            for pid in voters:
                legal = [x for x in tied if x != pid]
                if not legal:
                    continue
                rb[pid] = self._cast_ballot(pid, legal, True, context="revote")
            s.log("REVOTE_REVEAL", {"ballots": dict(rb), "candidates": list(tied)})
            t2 = {}
            for v in rb.values():
                t2[v] = t2.get(v, 0) + 1
            if not t2:
                break
            top2 = max(t2.values())
            tied2 = [k for k, v in t2.items() if v == top2]
            if len(tied2) == 1:
                s.adjudicate("TIE_LADDER_STEP_1", "small-count revote")
                s.metric("tie_ladder_step", 1)
                return tied2[0]
            tied = tied2
        winner = self.rng.choice(tied)
        s.adjudicate("SMALL_COUNT_TIE_FORCED",
                     f"{len(tied)} tied after {SMALL_COUNT_REVOTES} revotes")
        s.metric("small_count_tie_forced", 1)
        s.log("SMALL_COUNT_TIE_FORCED", {"candidates": list(tied), "result": winner})
        return winner

    def _bloc_backstop(self, bid, members, rounds):
        """§5.5. Reuses §8.2's longest-standing procedure: the member who
        named their pick first and never moved off it carries the bloc. Ties
        in standing resolve to the earlier-speaking member — `members` is in
        speaking order, so the first of them wins. A bloc never casts
        nothing."""
        s = self.state
        last = rounds[-1]
        standing = {}
        for pid in members:
            final = last[pid]
            r = len(rounds) - 1
            while r - 1 >= 0 and rounds[r - 1][pid] == final:
                r -= 1
            standing[pid] = r
        best = min(standing.values())
        carrier = next(p for p in members if standing[p] == best)
        target = last[carrier]
        # Retained as a diagnostic (§13.2): it now records that the backstop
        # was needed, not that a vote was lost.
        s.illegal("BLOC_VOTE_NON_UNANIMOUS", detail=f"bloc {bid}")
        s.adjudicate("BLOC_BACKSTOP_APPLIED", f"bloc {bid} carried by {carrier}")
        s.log("BLOC_BACKSTOP", {"bloc": bid, "carrier": carrier, "target": target},
              visible_to=f"BLOC:{bid}")
        s.metric("bloc_backstop", 1)
        s.metric(f"bloc_standing_win_{carrier}", 1)
        return target

    def bloc_vote(self, targets=None):
        """§5.5. Three blocs, one vote each, chosen from the slate.

        Unanimity is reached through bloc-internal deliberation: up to three
        rounds in which each member sees the others' prior-round proposals.
        Without that channel, independent choosing agrees ~1 time in 81 and
        every bloc deadlocks. As of v4 a deadlock no longer loses the vote —
        the longest-standing member carries the bloc.
        """
        s = self.state
        finalists = list(targets) if targets else None
        cast = {}

        for bid, members in s.blocs.items():
            alive_members = [m for m in members if s.players[m].alive]
            if not alive_members:
                continue

            if finalists:
                # A bloc may not vote for a finalist who is one of its own
                # members — that would be a self-vote by that member (§5.5).
                inside = [f for f in finalists if f in alive_members]
                if len(inside) == 2:
                    s.adjudicate("BLOC_ABSTAINS_BOTH_FINALISTS", f"bloc {bid}")
                    s.log("BLOC_ABSTAIN", {"bloc": bid, "reason": "both finalists"})
                    s.metric("bloc_abstains_both_finalists", 1)
                    continue
                if len(inside) == 1:
                    forced = next(f for f in finalists if f != inside[0])
                    cast[bid] = forced
                    s.adjudicate("BLOC_FORCED_BY_MEMBERSHIP",
                                 f"bloc {bid} -> {forced}")
                    s.log("BLOC_VOTE_FORCED", {"bloc": bid, "target": forced},
                          visible_to=f"BLOC:{bid}")
                    continue

            pool = finalists if finalists else s.living_ids()
            rounds = []
            agreed = None
            for rnd in range(3):
                proposals = {}
                for pid in alive_members:
                    legal = [x for x in pool if x != pid]
                    if not legal:
                        continue
                    pick = self.agents.bloc_propose(s, pid, legal, rnd)
                    if pick not in legal:
                        s.illegal("MALFORMED_OUTPUT", actor=pid, detail="bloc_propose")
                        pick = self.rng.choice(legal)
                    proposals[pid] = pick
                if not proposals:
                    break
                rounds.append(proposals)
                s.log("BLOC_PROPOSALS", {"bloc": bid, "round": rnd,
                                         "proposals": proposals},
                      visible_to=f"BLOC:{bid}")
                if len(set(proposals.values())) == 1:
                    agreed = next(iter(proposals.values()))
                    break
            if agreed is None and rounds:
                agreed = self._bloc_backstop(bid, list(rounds[-1]), rounds)
            if agreed is not None:
                cast[bid] = agreed

        roped = {pid for m in s.blocs.values() for pid in m}
        remainder = [p for p in s.living_ids() if p not in roped]
        ballots = {f"bloc{b}": v for b, v in cast.items()}
        pool = finalists if finalists else s.living_ids()
        for pid in remainder:
            legal = [x for x in pool if x != pid]
            if not legal:
                continue
            ballots[pid] = self._cast_ballot(pid, legal, finalists is not None)

        s.log("BLOC_VOTE_REVEAL", {"ballots": dict(ballots),
                                   "slate": finalists})

        # §5.5 — with three blocs and two finalists, at least one bloc
        # contains neither, so a banishment always results and the count is
        # preserved. If this ever fails the bloc assignment is broken.
        assert ballots, (
            "no vote cast at a roped council — §5.5 guarantees at least one "
            "bloc can always vote")

        return self.resolve_vote(ballots, list(s.living_ids()), targets)

    # ---------------- murders ----------------
    def select_target(self, exclude=()):
        """§8.1–8.2. Unanimous among living Traitors; else longest-standing."""
        s = self.state
        traitors = [p.pid for p in s.living_role(TRAITOR)]
        exclude = tuple(x for x in exclude if x)
        legal = [p.pid for p in s.living()
                 if p.role != TRAITOR and p.pid not in exclude]
        if not legal:
            s.adjudicate("NO_LEGAL_MURDER_TARGET")
            return None
        if len(traitors) == 1:
            t = self.agents.murder_propose(s, traitors[0], legal, 0)
            return t if t in legal else self.rng.choice(legal)

        rounds = []
        for r in range(3):
            proposals = {}
            for t in traitors:
                pick = self.agents.murder_propose(s, t, legal, r)
                if pick not in legal:
                    s.illegal("TRAITOR_TARGETS_TRAITOR", actor=t, detail=str(pick))
                    pick = self.rng.choice(legal)
                proposals[t] = pick
            rounds.append(proposals)
            s.log("MURDER_PROPOSALS", {"round": r, "proposals": proposals},
                  visible_to="TRAITORS")
            if len(set(proposals.values())) == 1:
                return list(proposals.values())[0]

        # deadlock: longest-standing unbroken proposal
        last = rounds[-1]
        standing_round = {}
        for t in traitors:
            final = last[t]
            r = len(rounds) - 1
            while r - 1 >= 0 and rounds[r - 1][t] == final:
                r -= 1
            standing_round[t] = r
        best = min(standing_round.values())
        if best == len(rounds) - 1:
            names = [p for rd in rounds for p in rd.values()]
            target = self.rng.choice(names)
            s.adjudicate("TRAITOR_DEADLOCK_FORCED", "no standing; random from proposed")
        else:
            winners = [t for t, r in standing_round.items() if r == best]
            winner = self.rng.choice(winners)
            target = last[winner]
            s.metric(f"standing_win_{winner}", 1)
            s.adjudicate("TRAITOR_DEADLOCK_FORCED", f"standing winner {winner}")
        return target

    def _sweep_voids_window(self, label):
        """§9.7 — with zero living Traitors nobody selects, so the window
        produces no victim and no Will. Returns True if the window is void."""
        s = self.state
        if s.living_role(TRAITOR):
            return False
        s.sweep_active = True
        s.float_event("SWEEP_NO_MURDER", f"{label} voided at {s.phase}")
        s.log("MURDER_VOIDED", {"label": label, "reason": "no living traitors"},
              visible_to=[])
        s.metric("sweep_no_murder", 1)
        return True

    def overnight_murder(self, label, exclude=()):
        s = self.state
        if self._sweep_voids_window(label):
            return None
        target = self.select_target(exclude=exclude)
        if target is None:
            return None
        s.log("MURDER_SELECTED", {"target": target, "label": label},
              visible_to="TRAITORS")
        if self.anchor_blocks(target):
            s.log("MURDER_VOIDED", {"target": target}, visible_to="TRAITORS")
            return None
        self.eliminate(target, "MURDER")
        self.write_will(target)
        return target

    def plate_murder(self, forced_target=None):
        """§8.3. Placement global pre-meal; swaps reach-constrained; plate rules."""
        s = self.state
        if forced_target is None and self._sweep_voids_window("MURDER_2"):
            return None
        seats = s.living_ids()[:]
        self.rng.shuffle(seats)

        target = forced_target or self.select_target()
        if target is None:
            return None

        plates = {}
        pool = PLATE_SET[:]
        self.rng.shuffle(pool)
        pool.remove("cairn")
        plates[target] = "cairn"
        for pid in seats:
            if pid != target:
                plates[pid] = pool.pop()
        s.log("PLATE_PLACEMENT", {"cairn_at": target}, visible_to="TRAITORS")

        # swaps — reasoning-gated (§8.3). Random bots never detect.
        for pid in seats:
            if not self.agents.plate_detect(s, pid):
                continue
            if s.rope_active:
                reach = [x for x in s.blocs.get(s.players[pid].bloc, [])
                         if s.players[x].alive]
            else:
                reach = seats
            if pid not in reach:
                s.illegal("PLATE_OUT_OF_REACH", actor=pid)
                continue
            partner = self.agents.plate_swap(s, pid, reach)
            if partner and partner in reach and partner != pid:
                plates[pid], plates[partner] = plates[partner], plates[pid]
                s.log("PLATE_SWAP", {"a": pid, "b": partner}, visible_to=[pid])

        victim = next(p for p, m in plates.items() if m == "cairn")
        s.metric("plate_swapped", 1 if victim != target else 0)
        if victim != target and s.players[victim].role == TRAITOR:
            s.metric("plate_killed_traitor", 1)

        if self.anchor_blocks(victim):
            s.log("MURDER_VOIDED", {"target": victim}, visible_to="TRAITORS")
            return None
        self.eliminate(victim, "MURDER")
        self.write_will(victim)
        return victim

    def write_will(self, pid):
        s = self.state
        text = self.agents.write_will(s, pid)
        s.players[pid].will = text
        if not s.first_successful_murder_done:
            recipient = self.agents.will_recipient_self(s, pid, s.living_ids())
            s.first_successful_murder_done = True
        else:
            recipient = self.agents.will_recipient_court(s, pid, s.living_ids())
        if recipient not in s.living_ids():
            recipient = self.rng.choice(s.living_ids()) if s.living_ids() else None
        s.log("WILL_WRITTEN", {"writer": pid, "recipient": recipient},
              visible_to=[recipient] if recipient else [])

    # ---------------- succession ----------------
    def succession_available(self):
        s = self.state
        return len(s.living_role(TRAITOR)) == 1

    def try_succession(self, window):
        """§9. Returns None if the window was not consumed, else
        {"outcome": "ACCEPTED"|"DECLINED", "victim": pid|None}. A decline
        becomes the murder, so it carries a victim; an acceptance produces no
        victim and owes a make-up (§9.6)."""
        s = self.state
        if not self.succession_available():
            return None
        traitor = s.living_role(TRAITOR)[0].pid
        elect = self.agents.succession_elect(s, traitor)
        s.log("SUCCESSION_ELECTION", {"recruit_mode": elect},
              visible_to=[traitor])
        if not elect:
            return None
        candidates = [p.pid for p in s.living_role(FAITHFUL)]
        if not candidates:
            return None
        recruit = self.agents.succession_offer(s, traitor, candidates)
        if recruit not in candidates:
            recruit = self.rng.choice(candidates)
        accepted = self.agents.succession_respond(s, recruit)
        s.log("SUCCESSION_OFFER", {"recruit": recruit, "accepted": accepted},
              visible_to=[traitor, recruit])
        s.metric("succession_trigger", 1)
        if accepted:
            s.players[recruit].role = TRAITOR
            s.successor_created = True
            s.float_event("SUCCESSION_ACCEPT", f"{recruit} joined")
            s.metric("succession_accept", 1)
            # §9.6 (new in v4) — the window owed an elimination and produced
            # none. The debt is repaired at NIGHT_3, not absorbed.
            s.succession_makeup_owed = True
            return {"outcome": "ACCEPTED", "victim": None}
        # declined -> the offer becomes the murder
        s.metric("succession_decline", 1)
        victim = None
        if window == "SAT_DINNER":
            self.state.phase = "SAT_DINNER"
            victim = self.plate_murder(forced_target=recruit)
        else:
            if not self.anchor_blocks(recruit):
                self.eliminate(recruit, "MURDER")
                self.write_will(recruit)
                victim = recruit
        return {"outcome": "DECLINED", "victim": victim}

    # ---------------- night 3 (§8.4) ----------------
    def night_3(self):
        """Up to three sequential eliminations: Anchor make-up, Succession
        make-up, Murder #3. Each gets a full independent selection and
        negotiation; no target may repeat within the night."""
        s = self.state
        s.phase = "NIGHT_3"

        labels = []
        if s.anchor_makeup_owed:
            labels.append("ANCHOR_MAKEUP")
        if s.succession_makeup_owed:
            labels.append("SUCCESSION_MAKEUP")
        labels.append("MURDER_3")
        s.anchor_makeup_owed = False
        s.succession_makeup_owed = False

        victims = []
        for label in labels:
            if self._sweep_voids_window(label):
                continue
            outcome = self.try_succession("NIGHT_3")
            if outcome is not None:
                if outcome["victim"]:
                    victims.append(outcome["victim"])
                elif s.succession_makeup_owed:
                    # Acceptance inside NIGHT_3 owes a make-up with no later
                    # window to pay it in — so pay it here. The successor is
                    # now a living Traitor, so Succession cannot trigger
                    # again and this resolves as an ordinary murder.
                    s.succession_makeup_owed = False
                    v = self.overnight_murder("SUCCESSION_MAKEUP",
                                              exclude=tuple(victims))
                    if v:
                        victims.append(v)
                continue
            v = self.overnight_murder(label, exclude=tuple(victims))
            if v:
                victims.append(v)

        if len(victims) == 3:
            s.adjudicate("TRIPLE_NIGHT_3",
                         "anchor make-up + succession make-up + murder 3")
            s.metric("triple_night_3", 1)
        s.metric("night_3_victims", len(victims))
        return victims

    # ---------------- transmission ----------------
    def transmission(self):
        s = self.state
        s.phase = "SUN_TRANSMISSION"
        living = s.living_ids()
        dead = [p.pid for p in s.dead()]
        if not dead:
            s.adjudicate("TRANSMISSION_NO_DEAD")
            return
        qs = self.agents.transmission_questions(s, living, TRANSMISSION_QUESTIONS)
        s.log("TRANSMISSION_OUT", {"questions": qs})
        answers = self.agents.transmission_answers(s, dead, qs, living)
        s.log("TRANSMISSION_BACK", {"answers": answers})
        s.adjudicate("TRANSMISSION_CONSENSUS_FORCED", "plurality applied")

    # ---------------- finale ----------------
    def finale(self):
        """RT_6. Mandatory banishment brings the count to Final 3, THEN the
        End/Banish-Again ballot among the finalists, then optional Ballot 2."""
        s = self.state
        s.phase = "RT_6_FINALE"
        s.councils_held += 1

        prompt = self.agents.council_prompt(s)
        s.log("COUNCIL_PROMPT", {"prompt": prompt})
        order = s.living_ids()[:]
        self.rng.shuffle(order)
        for pid in order:
            s.log("SPEAK", {"text": self.agents.speak(s, pid)}, actor=pid)

        # 1. mandatory banishment (the ninth elimination). RT_6 is exempt
        # from the nomination round by name (§5.3.5), so this is a direct
        # vote across all living players.
        banished = self.standard_vote(None)
        if banished:
            self.eliminate(banished, "BANISHMENT")
        self.check_sweep()

        voters = s.living_ids()
        if len(voters) > 3 and not s.sweep_active:
            # §9.7 — an oversized finale is the intended outcome of the sweep
            # branch, not drift to be reported as a defect.
            s.adjudicate("FINALE_OVERSIZED", f"{len(voters)} finalists (drift)")

        # 2. Ballot 1 — End The Game or Banish Again
        ballot1 = {pid: self.agents.finale_continue(s, pid) for pid in voters}
        s.log("FINALE_BALLOT_1", {"ballots": dict(ballot1)})
        banish_votes = sum(1 for v in ballot1.values() if v == "BANISH")
        if banish_votes <= len(voters) - banish_votes:
            s.ended_at_count = len(voters)   # tie or majority -> end
            return

        # 3. Ballot 2 — banishment
        ballots = {}
        for pid in voters:
            legal = [x for x in voters if x != pid]
            choice = self.agents.vote(s, pid, legal)
            if choice not in legal:
                s.illegal("SELF_VOTE", actor=pid)
                choice = self.rng.choice(legal)
            ballots[pid] = choice
        s.log("FINALE_BALLOT_2", {"ballots": dict(ballots)})

        tally = {}
        for v in ballots.values():
            tally[v] = tally.get(v, 0) + 1
        top = max(tally.values())
        tied = [k for k, v in tally.items() if v == top]

        if len(voters) == 3 and len(tied) > 1:
            s.ended_at_count = 3          # 1-1-1 ends at Final 3 (§12.1)
            return
        winner = tied[0] if len(tied) == 1 else self._small_count_tie(tied, voters)
        self.eliminate(winner, "BANISHMENT")
        self.check_sweep()
        s.ended_at_count = s.n_alive()

    # ---------------- scoring ----------------
    def score(self):
        s = self.state
        s.phase = "END"
        traitors_alive = len(s.living_role(TRAITOR))
        s.winner = "TRAITORS" if traitors_alive > 0 else "FAITHFUL"
        if s.ended_at_count is None:
            s.ended_at_count = s.n_alive()
        s.log("GAME_END", {"winner": s.winner, "alive": s.n_alive(),
                           "traitors_alive": traitors_alive})

    def check_sweep(self):
        """§9.7 — zero living Traitors no longer ends the game. Records the
        sweep once and lets play continue to RT_6; the Faithful win is
        declared at the finale reveal. Returns True on the transition only."""
        s = self.state
        if s.sweep_active or s.living_role(TRAITOR):
            return False
        s.sweep_active = True
        s.float_event("TRAITOR_SWEEP", f"zero living Traitors at {s.phase}")
        s.metric("sweep_phase", s.phase)
        s.metric("sweep_at_council", s.councils_held)
        s.log("TRAITOR_SWEEP", {"phase": s.phase}, visible_to=[])
        return True

    # ---------------- main loop ----------------
    def run(self):
        s = self.state
        self.setup()

        s.phase = "THU_ARRIVAL"
        self.assign_anchor()

        # §9.7 — the sweep check no longer short-circuits the game. It records
        # the transition and play continues to RT_6 in every branch.
        self.council("RT_0", voting=False)
        self.check_sweep()

        s.phase = "NIGHT_1"
        self.overnight_murder("MURDER_1")

        s.phase = "FRI_DISCOVERY"

        for name in ("RT_1", "RT_2"):
            self.council(name)
            self.check_sweep()
        self.rope_check("RT_2")

        self.council("RT_3")
        self.check_sweep()
        self.rope_check("RT_3")

        s.phase = "SAT_AFTERNOON"
        consumed = self.try_succession("SAT_DINNER")

        s.phase = "SAT_DINNER"
        if consumed is None:
            self.plate_murder()
        self.check_sweep()

        self.council("RT_4")
        self.check_sweep()

        self.transmission()

        self.council("RT_5")
        self.check_sweep()

        self.night_3()
        self.check_sweep()

        self.finale()
        self.score()
        return s
