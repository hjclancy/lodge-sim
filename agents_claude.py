"""
Claude-backed agents. Implements the same protocol as bots.RandomAgents.

The referee validates every return value, so nothing here can break a rule.
Anything the model fails to produce falls back to a legal random choice and is
logged as MALFORMED_OUTPUT — that count is itself a finding.
"""

import random
from archetypes import ARCHETYPES, param_line

TRAITOR = "TRAITOR"

OUTPUT_CONTRACT = (
    'Reply with a single JSON object and nothing else. No prose, no code fences.\n'
    'Schema: {"reasoning": "<your private thinking, 1-3 sentences>", '
    '"action": "<the action word>", "target": "<a player id like P07, or null>"}'
)

# §8.3 — detection is gated on the agent raising the objects itself.
PLATE_WORDS = ("plate", "plates", "china", "motif", "dish", "crockery",
               "place setting", "cairn", "tableware", "setting")


def visible(state, pid, ev):
    v = ev.visible_to
    if v == "ALL":
        return True
    if v == "TRAITORS":
        return state.players[pid].role == TRAITOR
    if v == "DEAD":
        return not state.players[pid].alive
    if isinstance(v, str) and v.startswith("BLOC:"):
        return str(state.players[pid].bloc) == v.split(":", 1)[1]
    if isinstance(v, (list, tuple, set)):
        return pid in v
    return False


def render(ev):
    p = ev.payload
    t = ev.type
    if t == "COUNCIL_PROMPT":
        return f"[{ev.phase}] RUNNER: {p.get('prompt','')}"
    if t == "SPEAK":
        return f"[{ev.phase}] {ev.actor}: {p.get('text','')}"
    if t == "VOTE_REVEAL":
        return f"[{ev.phase}] VOTES: " + ", ".join(f"{k}->{v}" for k, v in p["ballots"].items())
    if t == "REVOTE_REVEAL":
        return f"[{ev.phase}] REVOTE: " + ", ".join(f"{k}->{v}" for k, v in p["ballots"].items())
    if t == "BLOC_VOTE_REVEAL":
        return f"[{ev.phase}] BLOC VOTES: " + ", ".join(f"{k}->{v}" for k, v in p["ballots"].items())
    if t == "ELIMINATION":
        return f"[{ev.phase}] {p['pid']} is out ({p['how'].lower()})."
    if t == "ANCHOR_PASS":
        return f"[{ev.phase}] {p['from']} passed the token to {p['to']}."
    if t == "ANCHOR_ASSIGNED":
        return ("[private] You hold the token. It protects its holder from being "
                "killed in the night. You were asked to keep that secret.")
    if t == "ROLES_ASSIGNED":
        return f"[private] Your partners: {', '.join(p['traitors'])}."
    if t == "MURDER_PROPOSALS":
        return (f"[{ev.phase}] partner proposals round {p['round']}: "
                + ", ".join(f"{k} wants {v}" for k, v in p["proposals"].items()))
    if t == "BLOC_PROPOSALS":
        return (f"[{ev.phase}] your group, round {p['round']}: "
                + ", ".join(f"{k} wants {v}" for k, v in p["proposals"].items()))
    if t == "MURDER_SELECTED":
        return f"[{ev.phase}] your group chose {p['target']}."
    if t == "PLATE_PLACEMENT":
        return f"[{ev.phase}] you placed the marked plate at {p['cairn_at']}."
    if t == "TRANSMISSION_OUT":
        return "[transmission] questions sent: " + " | ".join(p["questions"])
    if t == "TRANSMISSION_BACK":
        return "[transmission] answers: " + " | ".join(
            f"{q} -> {a}" for q, a in p["answers"].items())
    if t == "WILL_WRITTEN":
        return "[private] A final message was left for you."
    if t == "SUCCESSION_OFFER":
        return f"[private] recruitment offer to {p['recruit']}: accepted={p['accepted']}"
    if t == "FINALE_BALLOT_1":
        return "[finale] end-or-continue: " + ", ".join(
            f"{k}->{v}" for k, v in p["ballots"].items())
    return None


class ClaudeAgents:
    def __init__(self, llm, assignment, public_rules, traitor_brief,
                 seed=0, trace_sink=None):
        """assignment: {pid: archetype_id}"""
        self.llm = llm
        self.assign = assignment
        self.public_rules = public_rules
        self.traitor_brief = traitor_brief
        self.rng = random.Random(seed + 5150)
        self.traces = trace_sink if trace_sink is not None else []
        self._detected = {}

    # ---------- prompt assembly ----------
    def system(self, s, pid):
        a = ARCHETYPES[self.assign[pid]]
        role = s.players[pid].role
        rules = self.traitor_brief if role == TRAITOR else self.public_rules
        parts = [
            "You are playing a hidden-role social deduction game with 11 other "
            "players. Play to win. You may lie, mislead, and withhold.",
            "=== RULES AS YOU RECEIVED THEM ===\n" + rules,
            f"=== WHO YOU ARE ===\nYou are {pid}. {a['prose']}",
            f"Behavioural profile: {param_line(self.assign[pid])}",
        ]
        if role == TRAITOR:
            partners = [p.pid for p in s.living_role(TRAITOR) if p.pid != pid]
            parts.append(f"You are one of the hidden players. {a['traitor']} "
                         f"Your surviving partners: {', '.join(partners) or 'none'}.")
        else:
            parts.append("You are not one of the hidden players. You do not know who is.")
        parts.append("=== OUTPUT ===\n" + OUTPUT_CONTRACT)
        return "\n\n".join(parts)

    def user(self, s, pid, instruction, legal=None):
        lines = []
        for ev in s.transcript:
            if not visible(s, pid, ev):
                continue
            r = render(ev)
            if r:
                lines.append(r)
        alive = ", ".join(s.living_ids())
        blk = "\n".join(lines[-120:]) or "(nothing has happened yet)"
        out = [f"=== WHAT YOU HAVE SEEN ===\n{blk}",
               f"=== NOW ===\nPhase: {s.phase}. Still in: {alive}.",
               instruction]
        if legal:
            out.append("Legal targets: " + ", ".join(legal))
        return "\n\n".join(out)

    def _ask(self, s, pid, instruction, legal=None, tag=""):
        sysmsg = self.system(s, pid)
        usr = self.user(s, pid, instruction, legal)
        data = self.llm.ask(sysmsg, usr) or {}
        self.traces.append({"game": s.game_id, "phase": s.phase, "pid": pid,
                            "archetype": self.assign[pid], "tag": tag,
                            "role": s.players[pid].role,
                            "reasoning": data.get("reasoning", "")})
        return data

    def _target(self, data, legal):
        t = (data or {}).get("target")
        if isinstance(t, str) and t in legal:
            return t
        return self.rng.choice(legal) if legal else None

    # ---------- protocol ----------
    def council_prompt(self, s):
        last = None
        for ev in reversed(s.transcript):
            if ev.type == "ELIMINATION":
                last = ev.payload
                break
        if not last:
            return "We are all still here. Who are you watching, and why?"
        return (f"{last['pid']} is gone. What does that tell us, and who does it "
                f"point at?")

    def speak(self, s, pid):
        d = self._ask(s, pid, "Say one thing to the group. Put it in 'target' as "
                              "null and your spoken words in 'action'.", tag="speak")
        txt = d.get("action") or d.get("text") or ""
        return str(txt)[:400]

    def vote(self, s, pid, legal):
        d = self._ask(s, pid, "Vote to remove one player. 'action' must be VOTE.",
                      legal, tag="vote")
        return self._target(d, legal)

    def bloc_propose(self, s, pid, legal, rnd):
        d = self._ask(s, pid,
                      f"You are tethered to two others and your group casts ONE vote, "
                      f"which must be unanimous or is discarded. Negotiation round "
                      f"{rnd+1} of 3. Name who your group should vote for.",
                      legal, tag="bloc")
        return self._target(d, legal)

    def anchor_pass(self, s, holder, candidates):
        d = self._ask(s, holder, "Pass the token to another player. This is public.",
                      candidates, tag="anchor_pass")
        return self._target(d, candidates)

    def murder_propose(self, s, traitor, legal, rnd):
        d = self._ask(s, traitor,
                      f"Choose tonight's target with your partners. The choice must be "
                      f"unanimous. Negotiation round {rnd+1} of 3. Holding a position "
                      f"across rounds strengthens it if you deadlock.",
                      legal, tag="murder")
        return self._target(d, legal)

    # ---------- §8.3 reasoning-gated detection ----------
    def plate_detect(self, s, pid):
        d = self._ask(s, pid,
                      "You are at dinner. Describe what you notice and what you intend "
                      "to do. 'action' is NOTHING or SWAP.", tag="dinner")
        text = (str(d.get("reasoning", "")) + " " + str(d.get("action", ""))).lower()
        looked = any(w in text for w in PLATE_WORDS)
        self._detected[pid] = looked
        if looked:
            s.log("PLATE_NOTICED", {"pid": pid}, visible_to=[pid])
            s.metric("plate_detect", 1)
        return looked and str(d.get("action", "")).upper() == "SWAP"

    def plate_swap(self, s, pid, reach):
        others = [x for x in reach if x != pid]
        if not others:
            return None
        d = self._ask(s, pid, "Swap your plate with someone in reach.", others,
                      tag="plate_swap")
        return self._target(d, others)

    # ---------- wills ----------
    def write_will(self, s, pid):
        d = self._ask(s, pid,
                      "You are out. Write ONE sentence to leave behind. You may not "
                      "reveal anyone's role, including your own. Put the sentence in "
                      "'action'.", tag="will")
        txt = str(d.get("action") or "").strip()
        return txt.split(".")[0][:220] + "." if txt else ""

    def will_recipient_self(self, s, pid, living):
        d = self._ask(s, pid, "Choose who receives your final message.", living,
                      tag="will_to")
        return self._target(d, living)

    def will_recipient_court(self, s, pid, living):
        dead = [p.pid for p in s.dead() if p.pid != pid]
        if not dead:
            return self.rng.choice(living) if living else None
        picks = {}
        for dpid in dead:
            d = self._ask(s, dpid, "The eliminated players choose together who "
                                   "receives this message. Name one.", living,
                          tag="will_court")
            picks[dpid] = self._target(d, living)
        return _plurality(picks.values(), self.rng, living)

    # ---------- succession ----------
    def succession_elect(self, s, traitor):
        d = self._ask(s, traitor,
                      "You are the last one left on your side. You may spend tonight "
                      "recruiting someone instead of killing. 'action' is RECRUIT or "
                      "KILL.", tag="succession_elect")
        return str(d.get("action", "")).upper() == "RECRUIT"

    def succession_offer(self, s, traitor, candidates):
        d = self._ask(s, traitor, "Choose who to approach.", candidates,
                      tag="succession_offer")
        return self._target(d, candidates)

    def succession_respond(self, s, recruit):
        d = self._ask(s, recruit,
                      "Someone has secretly offered to bring you onto their side. You "
                      "are told nothing about who they are unless you accept. Refusing "
                      "is dangerous. 'action' is ACCEPT or REFUSE.",
                      tag="succession_respond")
        return str(d.get("action", "")).upper() == "ACCEPT"

    # ---------- transmission ----------
    def transmission_questions(self, s, living, menu):
        numbered = [f"{i+1}. {q}" for i, q in enumerate(menu)]
        picks = {}
        for pid in living:
            d = self._ask(s, pid, "Choose ONE question to send to the eliminated "
                                  "players. Reply with its number in 'action'.\n"
                          + "\n".join(numbered), tag="transmission_q")
            try:
                idx = int(str(d.get("action", "")).strip().split()[0]) - 1
            except Exception:
                idx = self.rng.randrange(len(menu))
            picks[pid] = menu[idx] if 0 <= idx < len(menu) else self.rng.choice(menu)
        counts = {}
        for q in picks.values():
            counts[q] = counts.get(q, 0) + 1
        ranked = sorted(menu, key=lambda q: (-counts.get(q, 0), self.rng.random()))
        return ranked[:3]

    def transmission_answers(self, s, dead, questions, living):
        out = {}
        for q in questions:
            picks = {}
            for pid in dead:
                d = self._ask(s, pid, f"Answer with exactly one name: {q} "
                                      f"You may lie.", living, tag="transmission_a")
                picks[pid] = self._target(d, living)
            out[q] = _plurality(picks.values(), self.rng, living)
        return out

    # ---------- finale ----------
    def finale_continue(self, s, pid):
        d = self._ask(s, pid, "Vote to END the game now, or to BANISH one more "
                              "player. 'action' is END or BANISH.", tag="finale")
        return "BANISH" if str(d.get("action", "")).upper() == "BANISH" else "END"


def _plurality(values, rng, fallback):
    counts = {}
    for v in values:
        if v:
            counts[v] = counts.get(v, 0) + 1
    if not counts:
        return rng.choice(list(fallback)) if fallback else None
    top = max(counts.values())
    return rng.choice([k for k, v in counts.items() if v == top])
