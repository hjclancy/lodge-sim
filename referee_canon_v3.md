# REFEREE CANON v3

Rules specification for the Lodge simulation. Target consumer: implementation agent.
Supersedes v2. Authority: session rulings by Jack (game runner), which supersede
`lodge_rules_narrative_TEANAWAY` wherever they conflict (see §14).

Written for machine implementation. No formatting or presentation requirements.

---

## 0. CHANGELOG — v2 → v3

| # | Change | Reason |
|---|---|---|
| 1 | **§12.1 finale restructured.** Mandatory banishment now resolves FIRST (bringing the count to Final 3), then Ballot 1, then optional Ballot 2. | v2 had the ballots preceding the banishment. RT_6 opens with 4 alive; the source ruling describes the ballot as taken "among 3 players" with a possible 1–1–1 tie, which requires exactly 3 voters. v2 as written ended 61% of games at Final 4. Verified against 5,000 skeleton games. |
| 2 | §9.5 — Succession decline at `SAT_DINNER` executes under phase label `SAT_DINNER`, not `SAT_AFTERNOON`. | Implementation defect; eliminations were being logged to a phase with an elimination cap of 0. |
| 3 | §8.4 — make-up exclusion set must drop null entries before filtering legal targets. | Implementation defect. |
| 4 | New §6.8 — Anchor holder banished while holding the token. | Unhandled in v2. Fires 0.38×/game. |
| 5 | New §19 — empirical baseline from stage-1 verification. | Gives stage 2 a diff target. |
| 6 | New §20 — stage-2 agent requirements, in particular the unanimity channel. | Stage 1 proved unanimity mechanics are unreachable without a real negotiation channel. |
| 7 | §15 open items annotated with observed frequency. | Prioritization. |

---

## 1. PRIME RULE

Referee decides. Agents choose only.

Agent output is a preference, never a ruling. Every returned action is validated
against this spec before mutating state. Invalid actions: reject, log
`ILLEGAL_ACTION`, re-prompt once. Second invalid response: coerce to phase default
(§13.3).

Any situation not covered here: resolve by stated default, log `REF_ADJUDICATION`
with description, surface in aggregate report. The `REF_ADJUDICATION` frequency
table is the primary deliverable of the simulation.

---

## 2. ENTITIES

### 2.1 Players
- 12 players, ids `P01`–`P12`.
- Roles at `SETUP`: 3 `TRAITOR`, 9 `FAITHFUL`. Assigned from seed.
- Traitors know each other from `SETUP`. Faithful know only their own role.
- A player is `alive: true` until eliminated.

### 2.2 Runner
Not a player. Never eliminated. Never votes. Holds no information the referee does
not hold. Performs: initial Anchor assignment, Council prompts, bloc assignment,
Will delivery, Transmission relay.

### 2.3 The Court (dead players)
Eliminated players join the Court. They retain original role for scoring. Behaviour
is unconstrained: may continue playing their side, go neutral, or switch. Referee
does not enforce or infer allegiance among the dead; it records stated positions
and lets the aggregate report find patterns.

Court functions: choose Will recipients (§11.2), answer the Last Transmission (§10).

### 2.4 Successor
A Faithful who accepts Succession (§9) becomes `TRAITOR`. Learns the identity of
the recruiting Traitor at the moment of acceptance, and nothing before — no
history, no prior roster.

---

## 3. COUNT

Nine eliminations bring 12 → 3. A tenth is possible and optional (§12.1 Ballot 2).
RT_0 is non-eliminating; RT_1–RT_6 supply six banishments; three murder windows
supply three murders.

### 3.1 Normal path

| Beat | Event | Alive after |
|---|---|---|
| SETUP | — | 12 |
| COCKTAIL_HOUR | Anchor assigned (secret) | 12 |
| RT_0 | no banishment; Anchor pass | 12 |
| NIGHT_1 | Murder #1 | 11 |
| RT_1 | banishment; Anchor pass | 10 |
| RT_2 | banishment; Anchor pass | 9 |
| ROPE_CHECK | 9 alive → rope up, spans RT_3 | 9 |
| RT_3 | bloc banishment; Anchor pass; Unrope | 8 |
| SAT_AFTERNOON | Succession window check | 8 |
| SAT_DINNER | Murder #2 (plate) | 7 |
| RT_4 | banishment; Anchor rescinded | 6 |
| SUN_TRANSMISSION | — | 6 |
| RT_5 | banishment | 5 |
| NIGHT_3 | Murder #3 | 4 |
| RT_6 | **mandatory banishment** | 3 |
| RT_6 Ballot 1 | End, or Banish Again | 3 |
| RT_6 Ballot 2 | optional banishment | 3 or 2 |

### 3.2 Drift path (Anchor blocks Murder #1)

| Beat | Event | Alive after |
|---|---|---|
| NIGHT_1 | murder voided; Anchor breaks/exits; make-up owed | 12 |
| RT_1 | banishment (no Anchor pass — token gone) | 11 |
| RT_2 | banishment | 10 |
| RT_3 | banishment | 9 |
| ROPE_CHECK | 9 alive → rope up, spans SAT_DINNER + RT_4 | 9 |
| SAT_AFTERNOON | Succession window check (roped) | 9 |
| SAT_DINNER | Murder #2 (plate), roped, bloc seating | 8 |
| RT_4 | banishment; Unrope at conclusion | 7 |
| SUN_TRANSMISSION | — | 7 |
| RT_5 | banishment | 6 |
| NIGHT_3 | make-up murder, then Murder #3 (sequential) | 4 |
| RT_6 | mandatory banishment, then ballots | 3 or 2 |

Both paths terminate at 3 (or 2 by election). Verified against 17,000 skeleton
games; zero invariant violations.

### 3.3 Drift sources

| Source | Delta | Repair | Observed rate |
|---|---|---|---|
| `ANCHOR_BREAK` (§6.6) | +1 | make-up murder at NIGHT_3 | 19.6% |
| `ZERO_VOTE_COUNCIL` (§7.5) | +1 | none — absorbed | 1.9% (coordinated bots) |
| `SUCCESSION_ACCEPT` (§9.6) | +1 | none — absorbed, ends at Final 4 | 13.1% |

Log all as `FLOAT_EVENT`. Referee must not attempt unspecified repairs.

---

## 4. PHASE MACHINE

Strict sequence. Each phase is `phase(state) -> state`.

```
SETUP
THU_ARRIVAL           no mechanics, no information exchange
COCKTAIL_HOUR         Anchor assigned secretly, Runner -> random FAITHFUL
RT_0                  prompt, discussion, NO VOTE, Anchor pass
NIGHT_1               Murder #1
FRI_DISCOVERY         absence revealed; Will delivered
RT_1                  standard council
RT_2                  standard council
[ROPE_CHECK]          if alive == 9 and rope not yet raised -> rope up
RT_3                  council (bloc voting iff roped)
[ROPE_CHECK]          if alive == 9 and rope not yet raised -> rope up
SAT_AFTERNOON         Succession offer window if live (§9.4)
SAT_DINNER            Murder #2 — plate placement, swaps, resolution
RT_4                  council; ANCHOR RESCINDED at conclusion
SUN_TRANSMISSION      Last Transmission
RT_5                  council
NIGHT_3               make-up murder (if owed) THEN Murder #3
RT_6_FINALE           mandatory banishment -> Ballot 1 -> optional Ballot 2
END                   score
```

A sweep check runs after every eliminating phase: if living Traitors == 0, the
game ends immediately (§9.7).

`ROPE_CHECK` runs after RT_2 and after RT_3. Rope raises at most once per game.
If `alive != 9` at both checks, the rope never raises — log
`REF_ADJUDICATION: ROPE_NEVER_TRIGGERED`. Reachable only via a
`ZERO_VOTE_COUNCIL` or `SUCCESSION_ACCEPT` earlier than the rope; it is a guard,
not an expected branch. Observed 0.1% of games.

Unrope occurs at the conclusion of the Council the rope spans — normal path RT_3,
drift path RT_4 — **whether or not that Council produced a banishment.** This
prevents the rope stranding on `ZERO_VOTE_COUNCIL`.

---

## 5. COUNCILS

### 5.1 Sequence
1. Runner delivers exactly one discussion prompt, referencing the most recent
   murder or banishment.
2. One round of discussion.
3. Vote (skipped at RT_0).
4. Banishment resolves.
5. Anchor pass (RT_0 through RT_3 only; see §6.3).

### 5.2 Discussion model
Live play is free-form, overlapping, simultaneous, time-limited. Not reproducible
by turn-taking agents.

Implementation: single speaking pass in randomized order. Each agent sees all prior
speech in that pass.

Known bias — print on every report: this model preserves positional information
asymmetry but discards volume, dominance, and interruption. It under-models loud
archetypes and over-models quiet ones. Archetype survival figures must be read
against this.

### 5.3 Standard vote
- Plurality. No majority threshold.
- Simultaneous commitment, then full public reveal of every ballot.
- No self-votes. No abstentions. Both `ILLEGAL_ACTION`.
- Dead do not vote.
- Ballots collected in parallel; declared order is random and does not affect
  outcome.

### 5.4 Tie procedure
1. Revote between tied players only. Tied players do not vote. All other living
   players must vote for one of them.
2. If tie persists: rock-paper-scissors between tied players. Referee resolves as
   uniform random. Log `RPS_RESOLUTION`.

Three-way tie: same procedure, all three excluded from voting, then RPS
round-robin. Log `REF_ADJUDICATION: THREE_WAY_TIE`.

Degenerate small-count case: at 4 alive, a 2–2 tie excludes both tied players,
leaving 2 voters who may split 1–1 and fall through to RPS. This is a consequence
of the ruled procedure, not an error.

### 5.5 Bloc vote (roped Councils only)
Applies to whichever Council the rope spans — RT_3 normal path, RT_4 drift path.

- Three blocs, one vote each. Unanimous or nothing.
- A bloc that cannot agree casts no vote.
- Any unroped remainder players vote individually.
- Plurality across cast votes.
- 1–1–1 → immediate three-way RPS between the three named players. No revote step.
- All blocs deadlock → zero votes → no banishment → `FLOAT_EVENT: ZERO_VOTE_COUNCIL`.
- One bloc voting while two deadlock → that bloc's named player is banished. Legal
  and intended.

---

## 6. THE ANCHOR

### 6.1 Properties
- Protects against murder only. Banishment ignores it entirely.
- Held by exactly one living player at a time.
- Breaks and exits permanently on its first successful block. **At most one block
  and one make-up murder per game.**
- Rescinded permanently at the conclusion of RT_4 if not already broken.

### 6.2 Initial assignment
At `COCKTAIL_HOUR`, Runner assigns the Anchor secretly to a player. Runner will not
assign it to a Traitor. Implementation: uniform random selection among `FAITHFUL`.
Not visible to any player except the recipient.

### 6.3 Passing
- Passed at the conclusion of RT_0, RT_1, RT_2, RT_3.
- Holder must pass to another living player of their choosing. Self-retention is
  `ILLEGAL_ACTION: ANCHOR_SELF_RETAIN`.
- **Passes are public.** The object's location is known to all from the conclusion
  of RT_0 onward.
- No pass at RT_4; the token is rescinded at that Council's conclusion. A pass at
  RT_4 would protect nobody, as no murder window falls between the pass and the
  rescission.
- The last protected player is therefore the RT_3 recipient, who covers `SAT_DINNER`.

### 6.4 Secrecy of meaning — soft secret
The Anchor's *function* is disclosed only to each holder, who is instructed to keep
it secret. **Disclosure is legal and unpunished.** False claims of holding it, or
of knowing its meaning, are legal.

Knowledge model:
- `knows_anchor_meaning: set[player_id]`, initially `{initial_holder}`.
- Every player who holds the Anchor is added on receipt. Knowledge is monotonic —
  it persists after passing the token on.
- A knowing player may disclose to any player they choose (agent decision), adding
  the recipient to the set.
- Strategy directive to Traitor agents (not a rule): a Traitor who learns the
  meaning informs all living Traitors immediately, and no one else.

Consequence to instrument: protection is live only until the first Traitor learns
the meaning. Report `anchor_live_councils`. Skeleton baseline: a Traitor knows by
council 2.04 on average, in 70.7% of games.

### 6.5 Traitor pass behaviour
Traitors holding the Anchor preference passing to a living fellow Traitor. Strategy
directive, not a rule — a Traitor may pass to a Faithful for cover. Log
`ANCHOR_PASS` with roles of both parties so the report can measure roster leakage
through the pass chain.

### 6.6 Block resolution
If the Anchor holder is the resolved murder victim:
1. Murder is voided. No elimination that window.
2. Anchor breaks and exits play permanently.
3. Make-up murder owed, resolved at `NIGHT_3` (§8.4).
4. Log `FLOAT_EVENT: ANCHOR_BREAK`.

Traitors are informed the murder failed. They are **not** granted a redirect within
the same window.

For `SAT_DINNER`, the block checks whoever holds the **cairn plate at the end of
dinner**, not the Traitors' intended target (§8.3).

### 6.7 Pass while roped
The Anchor is a personal token. The pass is made by the individual holder and does
not require bloc unanimity. Log `REF_ADJUDICATION: ANCHOR_PASS_ROPED`.

### 6.8 Holder banished while holding — NEW IN v3
The holder can only leave play by banishment; a murder attempt on them triggers
§6.6 instead. When the holder is banished at a Council that carries a pass
(RT_0–RT_3):

**Default:** the banished holder makes the pass as their final act, before leaving
play. The token continues to circulate. Log
`REF_ADJUDICATION: ANCHOR_HOLDER_BANISHED`.

Alternative not taken: the token exits with them. Observed 0.38×/game — this is a
common event and the ruling is load-bearing. Confirm (§15).

---

## 7. ROPING UP

### 7.1 Trigger
Trigger-based, not schedule-based. Raises when exactly 9 players are alive, checked
after RT_2 and after RT_3. Raises at most once per game.

- Normal path: raises after RT_2, spans RT_3.
- Drift path: raises after RT_3, spans `SAT_DINNER` and RT_4.

### 7.2 Composition
Runner assigns. Three blocs of three.

Default with 3 Traitors alive: `3F` / `2F+1T` / `1F+2T`.
With fewer than 3 Traitors alive: maximum 1 Traitor per bloc.

Any player who cannot be placed in a bloc of three is left unroped and votes
individually. Log `REF_ADJUDICATION: ROPE_REMAINDER`.

### 7.3 Composition override — rope spanning a murder window
**When the rope spans a murder window (drift path only), all living Traitors are
assigned to the same bloc**, padded with Faithful to size three.

Rationale: information is bloc-constrained and enforced (§7.4). Without the
override, Traitors split across blocs cannot satisfy the unanimity requirement for
Murder #2, and the murder becomes unresolvable. The override supersedes §7.2.

With 3 Traitors alive, the Traitor bloc contains zero Faithful. This is legal —
plate placement is global (§8.3), so target reach is unaffected.

### 7.4 Information constraint
While roped, a player may exchange private information **only** with their two bloc
partners. Any private channel to a non-partner is
`ILLEGAL_ACTION: ROPE_INFO_BREACH`. Enforced by the referee — filtered from the
agent's visible transcript, not merely discouraged.

Public speech (Council discussion, table talk) is unaffected.

### 7.5 Voting while roped
See §5.5.

### 7.6 Unrope
At the conclusion of the spanned Council, regardless of whether a banishment
occurred.

---

## 8. MURDERS

### 8.1 General
- Exactly three windows: `NIGHT_1`, `SAT_DINNER`, `NIGHT_3`. Plus a make-up murder
  at `NIGHT_3` if owed.
- Murder is mandatory. Traitors may not decline.
- Target selection must be unanimous among **living** Traitors. At 2, both must
  agree. At 1, that Traitor decides alone.
- Traitors may not target Traitors. `ILLEGAL_ACTION: TRAITOR_TARGETS_TRAITOR`.
- The Anchor holder is a legal target. Targeting them triggers §6.6.

### 8.2 Deadlock procedure
Three rounds of Traitor discussion. If no unanimous target emerges:

**Longest-standing unbroken proposal wins.**

- A Traitor's standing begins at the round they first named a target and **breaks
  the moment they switch.** Switching and switching back restarts the clock at the
  later round.
- Tie in standing: uniform random between them. Log.
- No Traitor has standing (all churned every round): uniform random from all names
  proposed across the three rounds. Log.
- At 1 living Traitor, unanimity is trivially satisfied; the procedure never runs.

Log `REF_ADJUDICATION: TRAITOR_DEADLOCK_FORCED` on any forced resolution.

**Metric:** log per-Traitor `standing_wins`. This mechanic rewards naming first and
refusing to move; if one seat wins a large majority of contested targets, the
mechanic contains a dominant strategy and should be reported prominently.

### 8.3 Murder #2 — Murder in Plain Sight
Saturday dinner plate mechanic.

Plate set: crossed ice axes ×3, knotted rope ×3, signal flags ×3, storm lantern ×2,
**cairn ×1**. The cairn is the Murder Plate.

The tell is the **motif on the face**. No underside mark, no foot ring, no hairline
variation. Any such reference is a defect.

Sequence:
1. **Placement (pre-meal, global reach).** Traitors set the table together and may
   place the cairn at any seat. Placement is the murder decision, executed
   publicly. Not constrained by rope blocs — table-setting precedes seating.
2. **Seating.** Normal path: unconstrained. Drift path (roped): seating is by bloc.
3. **Swaps (during meal, local reach).** A player may move plates only within
   physical reach. Normal path: reach is global. Drift path (roped): reach is
   bloc-local. Out-of-reach attempts are `ILLEGAL_ACTION: PLATE_OUT_OF_REACH`.
4. **Resolution.** Whoever holds the cairn at the end of dinner is the victim.

**THE MURDER FOLLOWS THE PLATE.** Intent is irrelevant.

- A swap may kill a Traitor. Legal outcome; the §8.1 targeting prohibition governs
  placement, not resolution.
- A swap onto the Anchor holder voids the murder and breaks the token (§6.6).
- **Chain swaps: resolve final table state only.** No intent tracking, no ordering.
  Where the cairn ends up is the entire ruling.

Faithful knowledge: the Faithful do **not** know this mechanic exists. Victim learns
after dinner, simultaneously with everyone else.

**Detection model.** Counterplay (notice / swap / refuse / accuse) is gated on
reasoning, not a die roll. An agent receives a detection opportunity only if it
independently raises the plates, the china, or the motifs in its own reasoning
during `SAT_DINNER`. Agents that never look never check. Do not implement a flat
probability — that would hand the Faithful a free save and inflate their win rate.

Correct identification requires reasoning that the cairn specifically is the mark.
Every other motif is a tool of the living; the cairn is a marker of the dead. The
tell is semantic.

### 8.4 NIGHT_3 with make-up owed
Two sequential kills, resolved in order:
1. Make-up murder: full selection procedure (§8.1–8.2), full three-round negotiation.
2. Murder #3: fresh selection procedure, fresh negotiation.

A target may not be selected twice. Two distinct victims. Two Wills, delivered
separately (§11.1). The exclusion set must drop null entries before filtering.

### 8.5 Murder #3
Standard overnight murder. Anchor has left play; cannot be blocked.

---

## 9. SUCCESSION

Supersedes the auto-win on Reference Card 3. The Faithful do not win by eliminating
Traitors while Succession remains available.

### 9.1 Trigger conditions
All must hold:
- Exactly **1** living Traitor.
- A murder window is opening.

Available windows: `SAT_DINNER`, `NIGHT_3`, and the `NIGHT_3` make-up window.
`NIGHT_1` is impossible (3 Traitors alive). The former pre-RT_5 cutoff is lifted.

### 9.2 Election
**Succession is optional.** The lone Traitor elects whether to use the window for
recruitment or for a normal murder. Log the election.

`REF_ADJUDICATION: SUCCESSION_OPTIONAL` — the source ruling ("Traitors must
unanimously select someone to offer") is ambiguous as to whether Succession is
mandatory when triggered. Defaulted to optional. Confirm (§15).

### 9.3 Offer
- The lone Traitor selects the recruit (unanimity collapses to one decider).
- The recruit is told nothing about the Traitors — no names, no history — until
  acceptance.
- Recruit accepts or declines.

### 9.4 SAT_DINNER staging
Offer is made privately on Saturday afternoon, before the meal.

- **Accepted:** no cairn is placed. Plates are set as ordinary cover. No elimination
  that window.
- **Declined:** the offer becomes the murder. The refuser receives the cairn.

### 9.5 Decline resolution
At `SAT_DINNER`, the decline-murder **executes through the plate** and inherits
every rule in §8.3 — murder follows the plate, swaps redirect it, Anchor blocks it.
One rule for one window. The resulting elimination is logged under phase
`SAT_DINNER`, not `SAT_AFTERNOON`.

At `NIGHT_3`, a decline is an ordinary overnight murder.

### 9.6 Acceptance and drift
Acceptance produces zero eliminations in a window that owed one. Game runs to Final
4. Absorbed, not repaired. Log `FLOAT_EVENT: SUCCESSION_ACCEPT`.

The successor enters with a clean voting record, no Traitor history, and sincere
prior play.

### 9.7 Zero living Traitors
Succession triggers at exactly 1. A sweep to 0 living Traitors falls through every
ruled mechanic: no one can recruit, and no murder can be produced.

**Default:** Faithful win immediately at the moment the count reaches 0. Game ends.
Log `REF_ADJUDICATION: ZERO_TRAITORS_FAITHFUL_WIN`.

Observed 12.8% of skeleton games. **Not a rare edge case.** Requires ruling (§15).

---

## 10. THE LAST TRANSMISSION

`SUN_TRANSMISSION`, between RT_4 and RT_5.

- Living reach the dead as a bloc. No choice of who is contacted.
- Living select 3 questions from the fixed menu of 7.
- Dead answer with exactly one name per question.
- Public. Everyone hears both transmissions.
- One transmission out, one back. No follow-ups.
- The dead may lie.

### 10.1 The seven questions
1. Who feels the safest right now?
2. Who is playing the game the worst so far?
3. Who is being trusted too easily?
4. Who is playing the game the best so far?
5. Who were you right about?
6. Who were you wrong about?
7. Who does not deserve to win?

### 10.2 Consensus procedure — forced plurality, both sides
Applies identically to the living selecting questions and the Court selecting
answers.

- Up to three discussion rounds.
- Then plurality of that body.
- Ties broken uniformly at random. Log.
- Log `REF_ADJUDICATION: TRANSMISSION_CONSENSUS_FORCED` when plurality is invoked.

Every eliminated player has standing in the Court vote — banished and murdered
alike, Traitor and Faithful.

The Court's internal deliberation is private to the dead. Only the three returned
names are public.

### 10.3 Structural note
Dead Traitors are numerically outnumbered in the Court by Sunday (typically 5F:1–2T).
Under forced plurality they can influence but not carry an answer. This makes the
Transmission a structurally pro-Faithful mechanic and one of the few reliable
information injections the Faithful receive.

**Metric:** report Faithful win rate with the Transmission enabled vs. neutralized
(answers randomized), to measure how load-bearing it is.

---

## 11. WILLS

### 11.1 Spec
- **Murdered players only.** Banished players write nothing.
- Exactly one sentence. Over-length → `ILLEGAL_ACTION: WILL_OVER_LENGTH`, re-prompt.
- May accuse, warn, misdirect, or tell the truth.
- May **not** reveal the role of any active player, or the writer's own role.
  Violation → `ILLEGAL_ACTION: WILL_REVEALS_ROLE`, re-prompt.
- Delivered privately via the Runner. The Runner never confirms or denies anything
  said about a Will afterward.
- The `SAT_DINNER` plate victim writes one. A make-up murder victim writes one.
- At `NIGHT_3` with two victims, two Wills are written and delivered separately.

### 11.2 Recipient selection
- **First successful murder:** the writer chooses the recipient.
- **Every murder after:** the Court chooses as a group.

"First" means first murder that **produces a victim.** In the drift path `NIGHT_1`
is voided, so the `SAT_DINNER` victim is the first Will writer and chooses their own
recipient.

Court recipient selection uses the §10.2 forced-plurality procedure.

### 11.3 Instrument note
Because the Court chooses recipients from the second murder onward, and the Court
contains dead Traitors who may still be playing their side, Will delivery is itself
a Traitor instrument. Log recipient selection with the allegiance composition of the
Court and the role of the recipient.

---

## 12. WIN CONDITIONS

- **Any surviving Traitor at game end → Traitors win.**
- **Faithful win only on a clean sweep** — zero Traitors standing at the end,
  wherever the end lands.
- No individual winner. No last-Faithful-standing. Purely team resolution.
- A Successor counts as a Traitor.

### 12.1 RT_6 Finale — RESTRUCTURED IN v3

RT_6 opens with 4 living players on the normal path (more under drift). It runs in
three steps.

**Step 1 — mandatory banishment.** Prompt, one discussion round, standard vote
(§5.3), standard tie procedure (§5.4). This is the ninth elimination and brings the
count to Final 3. A sweep check runs here; if it returns zero Traitors, the game
ends immediately.

**Step 2 — Ballot 1: End The Game or Banish Again.** Binary. All remaining players
vote. Plurality. With 3 voters this always resolves 2–1 or 3–0. With 4 voters
(drift) a 2–2 tie is possible; **tie defaults to ending the game.** Log
`REF_ADJUDICATION: FINALE_OVERSIZED` when more than 3 players reach this ballot.

**Step 3 — Ballot 2: banishment.** Only if Ballot 1 returns Banish Again. Standard
vote rules, no self-votes.
- At 3 voters: 1–1–1 tie → **game ends immediately at Final 3. No RPS.**
- At 3 voters: 2–1 → that player is banished; game ends at **Final 2**. No further
  vote exists.
- At 4 voters (drift): standard tie procedure (§5.4) applies; game ends at Final 3
  after the banishment.

**Metric:** log Ballot 1 votes by role. A Traitor in the finals has already won and
has no incentive to continue; the continue-vote is functionally a Faithful
instrument and the split is a tell.

---

## 13. INFORMATION, ILLEGAL ACTIONS, DEFAULTS

### 13.1 Visibility
Every event carries `visible_to`: `ALL` | `TRAITORS` | `DEAD` | `BLOC:<id>` |
`[player_ids]`.

An agent's prompt is the transcript filtered to what it can see, in order. No
separate memory system.

Public and durable: all vote ballots, all banishment outcomes, all Anchor passes
(location only, not meaning), both Transmission halves, Council prompts.

Private: role assignments, Traitor deliberation, Court deliberation, Will contents
and recipients, initial Anchor assignment, Anchor meaning, Succession offers,
bloc-internal speech while roped.

### 13.2 Illegal action catalogue
`SELF_VOTE`, `ABSTENTION`, `DEAD_VOTE`, `TRAITOR_TARGETS_TRAITOR`,
`MURDER_OUT_OF_WINDOW`, `ANCHOR_SELF_RETAIN`, `WILL_REVEALS_ROLE`,
`WILL_OVER_LENGTH`, `ROPE_INFO_BREACH`, `MALFORMED_OUTPUT`,
`BLOC_VOTE_NON_UNANIMOUS`, `PLATE_OUT_OF_REACH`.

The frequency table of these across all runs is the **rulebook ambiguity list** —
each represents a place a reasonable reader tried something the rules forbid without
saying so.

### 13.3 Coercion defaults (second invalid response)
| Action | Default |
|---|---|
| vote | uniform random legal target |
| murder selection | §8.2 deadlock procedure |
| anchor pass | uniform random living player |
| will | empty string |
| speech | silence |
| plate placement | uniform random legal seat |
| succession election | murder (not recruit) |
| transmission question/answer | §10.2 plurality |

---

## 14. DIVERGENCE FROM `lodge_rules_narrative_TEANAWAY`

This canon governs. The player-facing document is wrong in seven places and must be
amended before February. Recorded so the amendment work item is not lost.

| # | Document | Canon |
|---|---|---|
| 1 | Anchor holder protects self or another; self-protection notifies Traitors | Mandatory pass to another player |
| 2 | Anchor passes Councils 1–3; rescinded Sunday morning | Passes RT_0–RT_3; rescinded at conclusion of RT_4 |
| 3 | Targeted holder simply saved, no consequence | Breaks, exits, count drifts, make-up murder |
| 4 | Votes written; Runner calls each player by name with explanation | Simultaneous commitment, public reveal |
| 5 | Tie → unspecified "secret mechanism" | Revote excluding tied players → RPS |
| 6 | Traitors *may* murder; Plain Sight at Runner's discretion | Three mandatory murders, fixed windows |
| 7 | No mention of bloc voting during Roping Up | Blocs vote unanimous-or-nothing while roped |

Absent from the document entirely: RT_0, Cocktail Hour Anchor assignment,
soft-secret Anchor meaning, trigger-based roping, Succession, the RT_6 three-step
finale.

Amendment should follow the simulation, not precede it.

---

## 15. OPEN — REQUIRES RULING BEFORE RESULTS ARE MEANINGFUL

Ordered by observed frequency in stage-1 verification.

| # | Item | § | Default taken | Observed rate |
|---|---|---|---|---|
| 1 | Anchor holder banished while holding the token — does the token pass or exit with them? | 6.8 | Passes as final act | 0.38×/game |
| 2 | Zero living Traitors — is it an immediate Faithful win? | 9.7 | Yes, immediate | 12.8% of games |
| 3 | Succession optional vs. mandatory when triggered | 9.2 | Optional | 28.3% trigger rate |
| 4 | Anchor pass at RT_4 — rescinded outright, or passed then rescinded? | 6.3 | Rescinded, no pass | every game |
| 5 | Rope never triggering — confirm fallback is "no roping" | 4 | No roping | 0.1% |

None block stage 2 mechanically. All change the results.

---

## 16. BUILD STAGES

1. **Skeleton — COMPLETE.** Referee + uniform-random bots, zero API calls.
   17,000 games across five configurations, zero invariant violations.
2. **Agents.** Claude personas. 200 games, fixed seeds. 6–8 archetypes distributed
   across 12 seats; randomize which archetypes draw Traitor each game.
3. **Report.** See §17.
4. **Iterate.** One rule change per version. Same seeds. Diff reports.
   `CHANGELOG.md`, one line per version: what changed, why, what moved.

---

## 17. REPORT METRICS

Required in every aggregate report:

- Traitor win rate, ±95% CI. At n=200 the margin is ≈±7pts; do not over-read a 52/48.
- Ending council distribution; frequency of Final 4 / Final 3 / Final 2.
- Elimination timing histogram by seat and by role.
- `REF_ADJUDICATION` frequency table — **the bug list.**
- `ILLEGAL_ACTION` frequency table — **the ambiguity list.**
- `FLOAT_EVENT` frequency by type.
- Archetype survival rate, annotated with the §5.2 bias warning.
- Anchor: block rate, `anchor_live_councils` distribution, holder-targeting rate,
  pass-chain roster leakage.
- Plate: detection rate, swap rate, swap-kills-Traitor rate.
- Traitor deadlock: forced-resolution rate, per-seat `standing_wins`.
- Succession: trigger rate, accept/decline split.
- Transmission: Faithful win rate enabled vs. neutralized.
- RT_6 Ballot 1 split by role.

---

## 18. STANDING PRINCIPLE

The rulebook prose is the deliverable, not the code. The simulation is an
instrument, not an authority. Where the data and the intended experience conflict,
the experience governs and the finding is recorded.

---

## 19. EMPIRICAL BASELINE — STAGE 1

Random-choice agents, 5,000 games, `coord=1.0` (agents can reach agreement),
`swap_prob=0` (detection is reasoning-gated; random bots never look).

**These are not predictions.** Random Faithful banish at chance, so the Traitor
figure is close to a floor. The value of this table is as a diff target: when
agents are swapped in, movement away from these numbers is attributable to
reasoning rather than to the machine.

| Metric | Value |
|---|---|
| Traitor win rate | 82.4% |
| Faithful win rate | 17.6% |
| Ending at Final 3 | 57.4% |
| Ending at Final 2 | 28.1% |
| Ending at Final 4+ | 14.5% |
| `ANCHOR_BREAK` | 19.6% |
| `SUCCESSION_ACCEPT` | 13.1% |
| `ZERO_VOTE_COUNCIL` | 1.9% |
| Rope raised | 99.9% |
| Anchor meaning reaches a Traitor | 70.7%, mean council 2.04 |
| Succession triggered | 28.3% |
| Zero-Traitor sweep | 12.8% |
| `THREE_WAY_TIE` | 0.85×/game |
| `ANCHOR_HOLDER_BANISHED` | 0.38×/game |
| `BLOC_VOTE_NON_UNANIMOUS` | 0.76×/game |

**Structural findings:**

1. The drift path is not an edge case. `ANCHOR_BREAK` at ~20% means roughly one
   weekend in five ropes through Saturday dinner. Plan for it.
2. The Anchor's protective life is about two Councils. Soft secrecy decays fast.
3. Bloc unanimity is the most fragile mechanic in the game. Uncoordinated agents
   deadlock 96% of the time; even perfectly coordinated ones fail 1.9%.

---

## 20. STAGE-2 AGENT REQUIREMENTS

Derived from stage-1 findings. These are implementation requirements, not rules.

1. **Unanimity mechanics require a real negotiation channel.** Three agents each
   choosing independently from nine names agree ~1 time in 81. Traitor murder
   selection (§8.2) and bloc voting (§5.5) must run as multi-turn exchanges where
   each agent sees the others' proposals before committing, or every game will take
   the drift path and every bloc vote will deadlock. This is the single most
   important difference between the skeleton bots and the agent implementation.
2. **Plate detection must stay reasoning-gated (§8.3).** Do not add a probability.
   Parse the agent's own reasoning for unprompted mention of the plates, the china,
   or the motifs; grant a detection opportunity only then.
3. **Anchor meaning propagation is an agent decision, not a referee rule.** The
   referee tracks `knows_anchor_meaning` and enforces nothing. Disclosure must be a
   choice the agent makes and can be lied about.
4. **Archetype assignment must be randomized against role each game.** A table where
   the same archetype always draws Traitor teaches half of what is needed.
5. **Fixed seeds.** Rule changes must be diffed against identical configurations.

*Canon v3.*
