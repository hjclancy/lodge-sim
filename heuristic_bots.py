"""
Heuristic agents — deterministic-parameter bots, zero API calls.

MODELING CHOICE, NOT GROUND TRUTH. Every mapping below is one implementer's
translation of an archetype's ten parameters (volubility, trust, stubborn,
record, object, disclosure, coalition, contrarian, accusation, risk) into a
concrete decision rule. A different implementer could map the same parameters
to different behaviour and get different numbers. Survival rates, vote
accuracy, standing_wins, and every other figure in the structural report
describe how these particular mappings play out at volume — they are not
discovered facts about how a human with that temperament would actually play.
Read the structural report as "how often, under this parameterization," never
as "how real players behave."

This sits between bots.RandomAgents (stage 1, zero intelligence, exercises
every code path) and agents_claude.py (stage 2, real reasoning, real cost).
Heuristic bots are free and fast, so they can run at volumes (thousands of
games) neither of the other two tiers can reach, in exchange for having no
actual judgement — only the archetype's declared parameters and whatever is
public in the transcript.

Information discipline, enforced throughout:
  - A bot may always use its own role and its own archetype's parameters.
  - A Traitor may use the living Traitor roster (`_fellow_traitors`) — Traitors
    know each other from SETUP per canon §2.1. This is the only place a bot
    reads another living player's true role.
  - Nothing here ever reads the true role of a still-living non-self player.
    Faithful "record" weighting is built entirely from `_suspicion_scores`,
    which only uses public vote history and the roles of *already-eliminated*
    players (revealed publicly on elimination — see referee.eliminate, which
    logs role with visible_to="ALL"). This keeps Faithful bots better than
    random but not omniscient, per the brief.
  - `speak()` output is flavor text only. Nothing in this file or in
    referee.py parses another agent's speech — there is no NLU layer — so
    `disclosure`/`accusation`/`volubility` influence what gets logged, not
    what any other bot decides. Documented per-method below.
"""

import random
from archetypes import ARCHETYPES
from referee import TRAITOR, FAITHFUL

NEGATIVE_HINTS = ("worst", "wrong", "trusted too easily", "does not deserve")


def _question_polarity(q):
    """Crude polarity read on the seven fixed Transmission questions, used
    only to decide whether the Court's answer should point at a currently
    suspicious player or a currently trusted one. Not a canon mechanic."""
    ql = q.lower()
    return "negative" if any(h in ql for h in NEGATIVE_HINTS) else "positive"


class HeuristicAgents:
    def __init__(self, seed=0):
        self.rng = random.Random(seed + 424242)
        # Per-agent-instance memory. One instance runs a whole game, so these
        # dicts persist for the game's lifetime, which is what lets bloc-mates
        # converge on a shared suggestion and lets a Traitor's murder proposal
        # actually hold across negotiation rounds.
        self._last_murder_proposal = {}   # traitor pid -> last-proposed target
        self._bloc_suggestion = {}        # (phase, bloc, round) -> suggested target
        self._buddy_cache = {}            # pid -> stable "coalition" ally pid

    # ---------- shared helpers ----------

    def _p(self, s, pid):
        return ARCHETYPES[s.players[pid].archetype]["params"]

    def _fellow_traitors(self, s, pid):
        """Only meaningful if pid is itself a living Traitor — see module
        docstring on information discipline."""
        if s.players[pid].role != TRAITOR:
            return []
        return [p.pid for p in s.living_role(TRAITOR) if p.pid != pid]

    def _avoid_fellow_traitor(self, s, pid, choice, legal):
        """Self-preservation: a Traitor bot never knowingly votes/nominates a
        living fellow Traitor for elimination when a legal alternative
        exists. murder_propose never needs this (the referee's own `legal`
        already excludes Traitors from murder targets); vote() and
        bloc_propose do, since their `legal` includes everyone."""
        fellow = self._fellow_traitors(s, pid)
        if choice in fellow:
            alt = [x for x in legal if x not in fellow]
            if alt:
                return self.rng.choice(alt)
        return choice

    def _weighted_choice(self, items, weights):
        total = sum(weights)
        if total <= 0:
            return self.rng.choice(items)
        r = self.rng.random() * total
        upto = 0.0
        for it, w in zip(items, weights):
            upto += w
            if upto >= r:
                return it
        return items[-1]

    def _suspicion_scores(self, s):
        """Public-information suspicion model. Built only from facts any
        living player could legitimately know: the public vote history
        (VOTE_REVEAL / REVOTE_REVEAL) and the roles of players already
        eliminated (public on elimination). A vote cast for someone since
        revealed a Traitor lowers the voter's suspicion (they were right); a
        vote cast for someone since revealed Faithful raises it slightly
        (a "wasted" or misdirecting vote). Evolves as the game reveals more
        roles — a vote can look prescient or bad only in hindsight, same as
        for a real player."""
        scores = {pid: 0.0 for pid in s.living_ids()}
        revealed_traitor = {p.pid for p in s.dead() if p.role == TRAITOR}
        revealed_faithful = {p.pid for p in s.dead() if p.role == FAITHFUL}
        for ev in s.transcript:
            if ev.type in ("VOTE_REVEAL", "REVOTE_REVEAL"):
                for voter, target in ev.payload["ballots"].items():
                    if voter not in scores:
                        continue
                    if target in revealed_traitor:
                        scores[voter] -= 1.0
                    elif target in revealed_faithful:
                        scores[voter] += 0.5
        return scores

    def _least_suspicious(self, s, candidates):
        suspicion = self._suspicion_scores(s)
        return min(candidates, key=lambda x: suspicion.get(x, 0.0))

    def _plurality_target(self, s, legal):
        """The top vote-getter of the most recently completed public vote,
        restricted to still-legal targets. Votes are simultaneous and only
        revealed after the fact (canon §5.3), so "the current plurality" for
        a bot about to vote can only mean the last *completed* result, not
        an in-progress tally nobody has seen yet."""
        for ev in reversed(s.transcript):
            if ev.type in ("VOTE_REVEAL", "BLOC_VOTE_REVEAL", "REVOTE_REVEAL"):
                tally = {}
                for v in ev.payload["ballots"].values():
                    tally[v] = tally.get(v, 0) + 1
                if not tally:
                    continue
                top = max(tally.values())
                candidates = [k for k, v in tally.items() if v == top and k in legal]
                return self.rng.choice(candidates) if candidates else None
        return None

    def _last_vote_of(self, s, pid):
        if pid is None:
            return None
        for ev in reversed(s.transcript):
            if ev.type in ("VOTE_REVEAL", "BLOC_VOTE_REVEAL", "REVOTE_REVEAL"):
                if pid in ev.payload["ballots"]:
                    return ev.payload["ballots"][pid]
        return None

    def _buddy(self, s, pid):
        """A stable, once-picked "coalition" ally — models a player who has
        settled on one person to vote with, per `coalition`. Re-picked only
        if the previous buddy has died."""
        buddy = self._buddy_cache.get(pid)
        if buddy is None or buddy not in s.living_ids():
            others = [x for x in s.living_ids() if x != pid]
            buddy = self.rng.choice(others) if others else None
            self._buddy_cache[pid] = buddy
        return buddy

    # ---------- council ----------

    def council_prompt(self, s):
        return "prompt"

    def speak(self, s, pid):
        """Flavor only — see module docstring. `volubility` gates whether
        anything is logged at all (and stands in for length/assertiveness,
        which there is nothing downstream to measure). `accusation` gates
        whether the line names a suspect, weighted toward whoever currently
        looks most suspicious. `disclosure` gates a token-holder's willingness
        to mention holding something — note the engine has no distinct
        "disclose anchor meaning" action (see referee.anchor_pass:
        knows_anchor_meaning only grows by holding the token), so this line
        never actually changes who knows the Anchor's meaning."""
        p = self._p(s, pid)
        if self.rng.random() > p["volubility"]:
            return ""
        bits = []
        if self.rng.random() < p["accusation"]:
            legal = [x for x in s.living_ids() if x != pid]
            if legal:
                suspicion = self._suspicion_scores(s)
                weights = [max(suspicion.get(x, 0.0), 0.05) for x in legal]
                bits.append(f"I'm watching {self._weighted_choice(legal, weights)}.")
        if s.anchor_holder == pid and self.rng.random() < p["disclosure"]:
            bits.append("I'm holding something. I won't say what it does.")
        return " ".join(bits) if bits else "Still thinking."

    def _nomination_leader(self, s, legal):
        """Who is currently ahead in this council's nomination round, among
        players still legal to name. Ties resolve to the earliest nomination,
        matching the referee's own §5.3.2 rule so a contrarian bot pushes
        against the player the slate would actually favour."""
        counts, earliest = {}, {}
        for _nominator, (nominee, idx) in s.nominations.items():
            if nominee not in legal:
                continue
            counts[nominee] = counts.get(nominee, 0) + 1
            if nominee not in earliest or idx < earliest[nominee]:
                earliest[nominee] = idx
        if not counts:
            return None
        return sorted(counts, key=lambda n: (-counts[n], earliest[n]))[0]

    def nominate(self, s, pid, legal):
        """§5.3.1. Same parameter blend as vote(), with two differences the
        nomination round introduces: it is sequential and public, so prior
        nominations are visible and `contrarian` has something concrete to
        push against; and it is an accusation rather than a ballot, so
        `accusation` — which vote() ignores — is the strongest term.

        MODELING CHOICE, not ground truth, on the same terms as every other
        mapping in this file:
          accusation  commit hard to whoever currently looks worst
          record      weight by public vote history, softer than accusation
          contrarian  name someone other than the round's current leader
          coalition   follow the ally's nomination, and shield the ally
          baseline    a constant 0.6 so a maxed parameter never fully
                      determines the choice

        A real player's nomination is also a bid for the floor and a signal
        to everyone who has not spoken yet. None of that is modelled: this
        picks a name. Nomination accuracy figures should be read the same way
        as vote accuracy — as what this parameterization does, not as what a
        person with that temperament would do."""
        if not legal:
            return None
        p = self._p(s, pid)
        suspicion = self._suspicion_scores(s)
        leader = self._nomination_leader(s, legal)
        buddy = self._buddy(s, pid)
        buddy_pick = s.nominations.get(buddy, (None, None))[0]

        w_accusation = p["accusation"]
        w_record = p["record"]
        w_contrarian = p["contrarian"] if leader else 0.0
        w_coalition = p["coalition"] if buddy_pick in legal else 0.0
        w_base = 0.6

        total = w_accusation + w_record + w_contrarian + w_coalition + w_base
        roll = self.rng.random() * total

        if roll < w_accusation:
            choice = max(legal, key=lambda x: suspicion.get(x, 0.0))
        else:
            roll -= w_accusation
            if roll < w_record:
                weights = [max(suspicion.get(x, 0.0), 0.05) for x in legal]
                choice = self._weighted_choice(legal, weights)
            else:
                roll -= w_record
                if roll < w_contrarian:
                    choices = [x for x in legal if x != leader] or legal
                    choice = self.rng.choice(choices)
                else:
                    roll -= w_contrarian
                    if roll < w_coalition:
                        choice = buddy_pick
                    else:
                        choice = self.rng.choice(legal)

        # `coalition` also shields: a high-coalition player is reluctant to
        # put their own ally on the slate.
        if choice == buddy and self.rng.random() < p["coalition"]:
            alt = [x for x in legal if x != buddy]
            if alt:
                choice = self.rng.choice(alt)

        return self._avoid_fellow_traitor(s, pid, choice, legal)

    def defend(self, s, pid):
        """§5.3.3. Templated and mechanically inert. `volubility` picks the
        register and `accusation` decides whether the defense redirects at
        someone else.

        Nothing downstream reads this string. That is not an oversight in the
        implementation, it is the honest shape of the model: a real defense
        moves votes, and this tier's vote() has no channel through which a
        defense could move one. Expect the defense round to show up in the
        structural report as pure cost — it changes no number here. It is the
        Claude tier that can test whether a defense does anything."""
        p = self._p(s, pid)
        others = [x for x in s.living_ids() if x != pid]
        if self.rng.random() < p["accusation"] and others:
            suspicion = self._suspicion_scores(s)
            weights = [max(suspicion.get(x, 0.0), 0.05) for x in others]
            return (f"This is the wrong name. Look at "
                    f"{self._weighted_choice(others, weights)}.")
        if self.rng.random() < p["volubility"]:
            return "I have been consistent all weekend. Check the record."
        return "I have nothing to add."

    def vote(self, s, pid, legal):
        """Blend of contrarianism, coalition, and record (§ brief). A
        constant baseline weight is always in the mix so a maxed-out `record`
        never fully overrides the noise — Faithful accuracy is meant to be
        better than chance, not omniscient."""
        if not legal:
            return None
        p = self._p(s, pid)
        plurality = self._plurality_target(s, legal)
        buddy = self._buddy(s, pid)
        buddy_vote = self._last_vote_of(s, buddy)

        w_contrarian = p["contrarian"] if plurality else 0.0
        w_coalition = p["coalition"] if buddy_vote in legal else 0.0
        w_record = p["record"]
        w_base = 0.6

        total = w_contrarian + w_coalition + w_record + w_base
        roll = self.rng.random() * total

        if roll < w_contrarian:
            choices = [x for x in legal if x != plurality] or legal
            choice = self.rng.choice(choices)
        else:
            roll -= w_contrarian
            if roll < w_coalition:
                choice = buddy_vote
            else:
                roll -= w_coalition
                if roll < w_record:
                    suspicion = self._suspicion_scores(s)
                    weights = [max(suspicion.get(x, 0.0), 0.05) for x in legal]
                    choice = self._weighted_choice(legal, weights)
                else:
                    choice = self.rng.choice(legal)

        return self._avoid_fellow_traitor(s, pid, choice, legal)

    # ---------- anchor ----------

    def anchor_pass(self, s, holder, candidates):
        """Traitor holders prefer passing to a fellow Traitor for cover
        (canon §6.5 strategy directive), scaled by `coalition`. Faithful
        holders lean, scaled by `trust`, toward passing to whoever currently
        looks least suspicious — protecting someone they believe in."""
        p = self._p(s, holder)
        fellow = [x for x in self._fellow_traitors(s, holder) if x in candidates]
        if fellow and self.rng.random() < (0.4 + 0.5 * p["coalition"]):
            return self.rng.choice(fellow)
        if self.rng.random() < p["trust"]:
            return self._least_suspicious(s, candidates)
        return self.rng.choice(candidates)

    # ---------- murder ----------

    def bloc_propose(self, s, pid, legal, rnd):
        """Unanimity emerges from a shared per-(phase, bloc, round)
        "suggestion" that every member independently proposes with
        probability scaled by the mean of coalition and stubbornness — high
        on both and the bloc converges; low on both and it churns and
        deadlocks, exactly like an uncoordinated random bot would."""
        p = self._p(s, pid)
        bloc = s.players[pid].bloc
        key = (s.phase, bloc, rnd)
        if key not in self._bloc_suggestion:
            self._bloc_suggestion[key] = self.rng.choice(legal)
        suggestion = self._bloc_suggestion[key]
        coord_prob = min(1.0, (p["coalition"] + p["stubborn"]) / 2)
        if suggestion in legal and self.rng.random() < coord_prob:
            choice = suggestion
        else:
            choice = self.rng.choice(legal)
        return self._avoid_fellow_traitor(s, pid, choice, legal)

    def murder_propose(self, s, traitor, legal, rnd):
        """§8.2's exact mechanism: `stubborn` governs whether a Traitor holds
        its previous round's proposal (building standing toward the
        longest-standing tiebreak) or switches to a fresh pick (resetting the
        standing clock). Round 0 always picks fresh. `legal` here already
        excludes Traitors (enforced by referee.select_target), so no
        self-preservation filter is needed."""
        p = self._p(s, traitor)
        prev = self._last_murder_proposal.get(traitor)
        if rnd > 0 and prev in legal and self.rng.random() < p["stubborn"]:
            pick = prev
        else:
            pick = self._weighted_target_pick(s, traitor, legal)
        self._last_murder_proposal[traitor] = pick
        return pick

    def _weighted_target_pick(self, s, traitor, legal):
        """A Traitor-side threat heuristic: favor removing players whose
        archetype `accusation` trait is high (loud accusers read as threats
        — this is their own declared trait, an observable of table
        behaviour, not a peek at anyone's secret role) and who currently
        look least suspicious (credible players are the more dangerous
        long-term vote-swingers). Not omniscient targeting of who "knows"
        anything specific about the Traitors."""
        suspicion = self._suspicion_scores(s)
        weights = []
        for pid in legal:
            acc = self._p(s, pid)["accusation"]
            susp = suspicion.get(pid, 0.0)
            weights.append(max(0.3 + acc - 0.15 * susp, 0.05))
        return self._weighted_choice(legal, weights)

    # ---------- plate (§8.3) ----------

    def plate_detect(self, s, pid):
        """`object` as a GATED roll, not a flat rate (per canon §8.3's own
        warning, carried over as a design constraint for this tier too):
        below a threshold the bot essentially never notices; above it, the
        chance rises linearly with `object`, topping out well under certain.
        This is the heuristic-tier stand-in for the Claude tier's
        reasoning-gate — there is no reasoning trace here to gate on, so the
        parameter itself is the gate."""
        obj = self._p(s, pid)["object"]
        threshold = 0.55
        if obj <= threshold:
            return False
        chance = (obj - threshold) / (1 - threshold) * 0.45
        detected = self.rng.random() < chance
        if detected:
            s.metric("plate_detect_by_pid", pid)
        return detected

    def plate_swap(self, s, pid, reach):
        """Detection (above) already gated on `object`; whether the bot acts
        on it — actually reaching over to swap a plate, a visible and
        committal act — is gated on `risk`."""
        others = [x for x in reach if x != pid]
        if not others:
            return None
        if self.rng.random() < self._p(s, pid)["risk"]:
            return self.rng.choice(others)
        return None

    # ---------- wills ----------

    def write_will(self, s, pid):
        return "Watch the quiet ones."

    def will_recipient_self(self, s, pid, living):
        if not living:
            return None
        buddy = self._buddy(s, pid)
        return buddy if buddy in living else self._least_suspicious(s, living)

    def will_recipient_court(self, s, pid, living):
        """The Court decides as a group (referee calls this once, not per
        dead player), so there is no single archetype to hang this on —
        falls back to the shared suspicion model only."""
        if not living:
            return None
        return self._least_suspicious(s, living)

    # ---------- succession ----------

    def succession_elect(self, s, traitor):
        """Recruiting instead of killing is itself a gamble (foregoes a
        guaranteed elimination for an uncertain ally), so it scales with
        `risk` around a moderate baseline rather than a coin flip."""
        return self.rng.random() < (0.2 + 0.6 * self._p(s, traitor)["risk"])

    def succession_offer(self, s, traitor, candidates):
        """Prefer a "clean" recruit — low current public suspicion — since
        their acceptance is less likely to itself look suspicious."""
        suspicion = self._suspicion_scores(s)
        weights = [1.0 / (1.0 + max(suspicion.get(pid, 0.0), 0.0)) for pid in candidates]
        return self._weighted_choice(candidates, weights)

    def succession_respond(self, s, recruit):
        return self.rng.random() < self._p(s, recruit)["risk"]

    # ---------- transmission ----------

    def transmission_questions(self, s, living, menu):
        return self.rng.sample(menu, 3)

    def transmission_answers(self, s, dead, questions, living):
        """The Court's collective answer per question, aimed by the
        question's rough polarity: a negatively-framed question ("worst",
        "wrong", ...) names whoever currently looks most suspicious; a
        positively-framed one names whoever looks least suspicious."""
        if not living:
            return {q: None for q in questions}
        suspicion = self._suspicion_scores(s)
        answers = {}
        for q in questions:
            if _question_polarity(q) == "negative":
                weights = [max(suspicion.get(pid, 0.0), 0.05) for pid in living]
            else:
                weights = [1.0 / (1.0 + max(suspicion.get(pid, 0.0), 0.0)) for pid in living]
            answers[q] = self._weighted_choice(living, weights)
        return answers

    # ---------- finale ----------

    def finale_continue(self, s, pid):
        """`risk` governs whether a finalist gambles on one more banishment
        (BANISH) or locks in the current standing (END)."""
        return "BANISH" if self.rng.random() < self._p(s, pid)["risk"] else "END"
