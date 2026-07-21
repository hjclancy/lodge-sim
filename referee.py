"""
The Lodge — referee engine.
Implements REFEREE CANON v2. The referee decides; agents only choose.

Every agent return value is validated here before it touches state.
Nothing in this file may be overridden by an agent.
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
    rules_version: str = "canon_v2"
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

    makeup_owed: bool = False
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
        s.makeup_owed = True
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
        s = self.state
        s.phase = name
        s.councils_held += 1

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
            if roped_here:
                banished = self.bloc_vote()
            else:
                banished = self.standard_vote()
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

    def standard_vote(self):
        s = self.state
        voters = s.living_ids()
        ballots = {}
        for pid in voters:
            legal = [x for x in voters if x != pid]
            choice = self.agents.vote(s, pid, legal)
            if choice == pid:
                s.illegal("SELF_VOTE", actor=pid)
                choice = self.rng.choice(legal)
            elif choice not in legal:
                s.illegal("ABSTENTION" if choice is None else "DEAD_VOTE",
                          actor=pid, detail=str(choice))
                choice = self.rng.choice(legal)
            ballots[pid] = choice
        s.log("VOTE_REVEAL", {"ballots": dict(ballots)})
        return self.resolve_plurality(ballots, voters)

    def resolve_plurality(self, ballots, voters):
        """§5.3–5.4. Plurality, then revote excluding tied, then RPS."""
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

        if len(tied) > 2:
            s.adjudicate("THREE_WAY_TIE", f"{len(tied)} tied")

        # revote: tied players excluded from voting, all others must pick one
        revoters = [p for p in voters if p not in tied]
        rb = {}
        for pid in revoters:
            choice = self.agents.vote(s, pid, tied)
            if choice not in tied:
                s.illegal("MALFORMED_OUTPUT", actor=pid, detail="revote")
                choice = self.rng.choice(tied)
            rb[pid] = choice
        s.log("REVOTE_REVEAL", {"ballots": dict(rb), "candidates": tied})

        t2 = {}
        for v in rb.values():
            t2[v] = t2.get(v, 0) + 1
        if t2:
            top2 = max(t2.values())
            tied2 = [k for k, v in t2.items() if v == top2]
            if len(tied2) == 1:
                return tied2[0]
            tied = tied2

        winner = self.rng.choice(tied)
        s.log("RPS_RESOLUTION", {"candidates": tied, "result": winner})
        s.metric("rps_resolution", 1)
        return winner

    def bloc_vote(self):
        """§5.5. Three blocs, one vote each, unanimous or nothing.

        Unanimity is reached through bloc-internal deliberation: up to three
        rounds in which each member sees the others' prior-round proposals.
        This implements the rule faithfully (three tethered people can talk);
        it does not change it. Without the channel, independent choosing
        agrees ~1 time in 81 and every bloc deadlocks.
        """
        s = self.state
        cast = {}
        for bid, members in s.blocs.items():
            alive_members = [m for m in members if s.players[m].alive]
            if not alive_members:
                continue
            agreed = None
            for rnd in range(3):
                proposals = {}
                for pid in alive_members:
                    legal = [x for x in s.living_ids() if x != pid]
                    pick = self.agents.bloc_propose(s, pid, legal, rnd)
                    if pick not in legal:
                        s.illegal("MALFORMED_OUTPUT", actor=pid, detail="bloc_propose")
                        pick = self.rng.choice(legal)
                    proposals[pid] = pick
                s.log("BLOC_PROPOSALS", {"bloc": bid, "round": rnd,
                                         "proposals": proposals},
                      visible_to=f"BLOC:{bid}")
                if len(set(proposals.values())) == 1:
                    agreed = next(iter(proposals.values()))
                    break
            if agreed is not None:
                cast[bid] = agreed
            else:
                s.illegal("BLOC_VOTE_NON_UNANIMOUS", detail=f"bloc {bid}")
                s.log("BLOC_DEADLOCK", {"bloc": bid})

        roped = {pid for m in s.blocs.values() for pid in m}
        remainder = [p for p in s.living_ids() if p not in roped]
        ballots = {f"bloc{b}": v for b, v in cast.items()}
        for pid in remainder:
            legal = [x for x in s.living_ids() if x != pid]
            ballots[pid] = self.agents.vote(s, pid, legal)

        s.log("BLOC_VOTE_REVEAL", {"ballots": dict(ballots)})

        if not ballots:
            s.float_event("ZERO_VOTE_COUNCIL", "all blocs deadlocked")
            return None

        tally = {}
        for v in ballots.values():
            tally[v] = tally.get(v, 0) + 1
        top = max(tally.values())
        tied = [k for k, v in tally.items() if v == top]
        if len(tied) == 1:
            return tied[0]
        winner = self.rng.choice(tied)
        s.log("RPS_RESOLUTION", {"candidates": tied, "result": winner,
                                 "context": "bloc_1_1_1"})
        s.metric("rps_resolution", 1)
        return winner

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

    def overnight_murder(self, label, exclude=()):
        s = self.state
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
        """§9. Returns True if succession consumed the window."""
        s = self.state
        if not self.succession_available():
            return False
        traitor = s.living_role(TRAITOR)[0].pid
        elect = self.agents.succession_elect(s, traitor)
        s.log("SUCCESSION_ELECTION", {"recruit_mode": elect},
              visible_to=[traitor])
        if not elect:
            return False
        candidates = [p.pid for p in s.living_role(FAITHFUL)]
        if not candidates:
            return False
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
            return True
        # declined -> the offer becomes the murder
        s.metric("succession_decline", 1)
        if window == "SAT_DINNER":
            self.state.phase = "SAT_DINNER"
            self.plate_murder(forced_target=recruit)
        else:
            if not self.anchor_blocks(recruit):
                self.eliminate(recruit, "MURDER")
                self.write_will(recruit)
        return True

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

        # 1. mandatory banishment (the ninth elimination)
        banished = self.standard_vote()
        if banished:
            self.eliminate(banished, "BANISHMENT")
        if self.check_sweep():
            s.ended_at_count = s.n_alive()
            return

        voters = s.living_ids()
        if len(voters) > 3:
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
            s.ended_at_count = 3          # 1-1-1 ends at Final 3, no RPS
            return
        winner = tied[0] if len(tied) == 1 else self.resolve_plurality(ballots, voters)
        self.eliminate(winner, "BANISHMENT")
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
        """§9.7 — zero living Traitors ends the game immediately."""
        s = self.state
        if len(s.living_role(TRAITOR)) == 0:
            s.adjudicate("ZERO_TRAITORS_FAITHFUL_WIN")
            return True
        return False

    # ---------------- main loop ----------------
    def run(self):
        s = self.state
        self.setup()

        s.phase = "THU_ARRIVAL"
        self.assign_anchor()

        self.council("RT_0", voting=False)
        if self.check_sweep():
            self.score(); return s

        s.phase = "NIGHT_1"
        self.overnight_murder("MURDER_1")

        s.phase = "FRI_DISCOVERY"

        for name in ("RT_1", "RT_2"):
            self.council(name)
            if self.check_sweep():
                self.score(); return s
        self.rope_check("RT_2")

        self.council("RT_3")
        if self.check_sweep():
            self.score(); return s
        self.rope_check("RT_3")

        s.phase = "SAT_AFTERNOON"
        consumed = self.try_succession("SAT_DINNER")

        s.phase = "SAT_DINNER"
        if not consumed:
            self.plate_murder()
        if self.check_sweep():
            self.score(); return s

        self.council("RT_4")
        if self.check_sweep():
            self.score(); return s

        self.transmission()

        self.council("RT_5")
        if self.check_sweep():
            self.score(); return s

        s.phase = "NIGHT_3"
        first_victim = None
        if s.makeup_owed:
            consumed = self.try_succession("NIGHT_3")
            if not consumed:
                first_victim = self.overnight_murder("MAKEUP")
            s.makeup_owed = False
        consumed = self.try_succession("NIGHT_3")
        if not consumed:
            self.overnight_murder(
                "MURDER_3", exclude=(first_victim,) if first_victim else ())
        if self.check_sweep():
            self.score(); return s

        self.finale()
        self.score()
        return s
