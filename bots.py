"""
Uniform-random agents. Zero API calls.

Purpose: exercise every code path in the referee without any intelligence.
If the machine is sound under random play, it is sound.
These bots deliberately do NOT detect the plate (§8.3 detection is
reasoning-gated; random bots never reason, so they never look).
"""

import random


class RandomAgents:
    def __init__(self, seed=0, swap_prob=0.0, coord=0.0):
        self.rng = random.Random(seed + 90210)
        self.swap_prob = swap_prob  # forced-swap knob for path testing only
        self.coord = coord          # probability a bloc/traitor group coordinates
        self._bloc_pick = {}        # bloc_id -> agreed target this council
        self._murder_pick = {}      # round-key -> agreed target

    # --- council ---
    def council_prompt(self, s):
        return "prompt"

    def speak(self, s, pid):
        return ""

    def nominate(self, s, pid, legal):
        """§5.3.1. Uniform random. Random bots have no read to commit."""
        return self.rng.choice(legal) if legal else None

    def defend(self, s, pid):
        """§5.3.3. Defense has no mechanical effect; random bots say nothing."""
        return ""

    def vote(self, s, pid, legal):
        if not legal:
            return None
        # Roped blocs coordinate with probability `coord`, modelling the fact
        # that three tethered humans can actually talk. Random bots cannot.
        p = s.players[pid]
        if s.rope_active and p.bloc is not None:
            key = (s.phase, p.bloc)
            if key not in self._bloc_pick:
                if self.rng.random() < self.coord:
                    self._bloc_pick[key] = self.rng.choice(legal)
                else:
                    self._bloc_pick[key] = None
            agreed = self._bloc_pick[key]
            if agreed is not None and agreed != pid and agreed in legal:
                return agreed
        return self.rng.choice(legal)

    # --- anchor ---
    def anchor_pass(self, s, holder, candidates):
        return self.rng.choice(candidates)

    # --- murder ---
    def bloc_propose(self, s, pid, legal, rnd):
        key = (s.phase, s.players[pid].bloc, rnd)
        if key not in self._bloc_pick:
            self._bloc_pick[key] = (self.rng.choice(legal)
                                    if self.rng.random() < self.coord else None)
        agreed = self._bloc_pick[key]
        if agreed is not None and agreed in legal:
            return agreed
        return self.rng.choice(legal)

    def murder_propose(self, s, traitor, legal, rnd):
        key = (s.phase, rnd)
        if key not in self._murder_pick:
            self._murder_pick[key] = (self.rng.choice(legal)
                                      if self.rng.random() < self.coord else None)
        agreed = self._murder_pick[key]
        if agreed is not None and agreed in legal:
            return agreed
        return self.rng.choice(legal)

    # --- plate ---
    def plate_detect(self, s, pid):
        return self.rng.random() < self.swap_prob

    def plate_swap(self, s, pid, reach):
        others = [x for x in reach if x != pid]
        return self.rng.choice(others) if others else None

    # --- wills ---
    def write_will(self, s, pid):
        return "one sentence."

    def will_recipient_self(self, s, pid, living):
        return self.rng.choice(living) if living else None

    def will_recipient_court(self, s, pid, living):
        return self.rng.choice(living) if living else None

    # --- succession ---
    def succession_elect(self, s, traitor):
        return self.rng.random() < 0.5

    def succession_offer(self, s, traitor, candidates):
        return self.rng.choice(candidates)

    def succession_respond(self, s, recruit):
        return self.rng.random() < 0.5

    # --- transmission ---
    def transmission_questions(self, s, living, menu):
        return self.rng.sample(menu, 3)

    def transmission_answers(self, s, dead, questions, living):
        return {q: (self.rng.choice(living) if living else None) for q in questions}

    # --- finale ---
    def finale_continue(self, s, pid):
        return self.rng.choice(["END", "BANISH"])
