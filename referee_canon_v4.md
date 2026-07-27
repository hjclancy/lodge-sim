# REFEREE CANON v4

Rules specification for the Lodge simulation. Target consumer: implementation agent.
Supersedes v3. Authority: session rulings by Jack (game runner), which supersede
`lodge_rules_narrative_TEANAWAY` wherever they conflict (see §14).

Written for machine implementation. No formatting or presentation requirements.

---

## 0. CHANGELOG — v3 → v4

All five changes are responses to measured heuristic-batch frequencies exceeding
Jack's acceptable thresholds.

| # | Change | Driver |
|---|---|---|
| 1 | **§5.1 / §5.3 — nomination and defense rounds added.** Councils now run discussion → sequential spoken nomination → provisional slate of 3 → lowest dropped → 2 finalists defend → vote restricted to the 2. | `THREE_WAY_TIE` 0.79/game, target 0.002. A two-name ballot makes three-way ties structurally impossible. |
| 2 | **§5.4 — RPS deleted.** Replaced with a deterministic ladder: revote after discussion → higher nomination count → earliest nomination. | Coin flips deciding eliminations ruled impermissible for February. |
| 3 | **§5.5 — blocs vote from the slate**, with a longest-standing backstop when a bloc cannot agree. A bloc can never cast nothing. | `ZERO_VOTE_COUNCIL` 0.325/game, target 0.002. Now structurally impossible. |
| 4 | **§9.6 — Succession acceptance now owes a make-up elimination** at `NIGHT_3`, matching the `ANCHOR_BREAK` pattern. Drift is repaired, not absorbed. | `FINALE_OVERSIZED` 0.34/game, target 0.10. |
| 5 | **§9.7 — a zero-Traitor sweep no longer ends the game.** Play continues to `RT_6`; murder windows produce no victim; the Faithful win is declared at the finale reveal. | Experiential ruling. Win rate unchanged — a sweep was already a Faithful win. |
| 6 | Flag 4's ruling "no nomination or accusation step" is **formally superseded** by change 1. Recorded so the reversal is not silently lost. | — |

**Not changed in v4:** the Traitor/Faithful win split (measured 9:1, target 6:4).
Changes 1–3 remove noise that suppresses Faithful performance; the split is to be
**re-measured after this version** before any win-condition surgery. Do not stack a
balance change onto this release (§16.4).

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
Not a player. Never eliminated. Never votes. Never nominates. Holds no information
the referee does not hold. Performs: initial Anchor assignment, Council prompts,
nomination order, bloc assignment, Will delivery, Transmission relay.

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
| RT_1 | nomination → banishment; Anchor pass | 10 |
| RT_2 | nomination → banishment; Anchor pass | 9 |
| ROPE_CHECK | 9 alive → rope up, spans RT_3 | 9 |
| RT_3 | nomination → bloc banishment; Anchor pass; Unrope | 8 |
| SAT_AFTERNOON | Succession window check | 8 |
| SAT_DINNER | Murder #2 (plate) | 7 |
| RT_4 | nomination → banishment; Anchor rescinded | 6 |
| SUN_TRANSMISSION | — | 6 |
| RT_5 | nomination → banishment | 5 |
| NIGHT_3 | Murder #3 | 4 |
| RT_6 | mandatory banishment (no nomination) | 3 |
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
| RT_4 | bloc banishment; Unrope at conclusion | 7 |
| SUN_TRANSMISSION | — | 7 |
| RT_5 | banishment | 6 |
| NIGHT_3 | make-up murder, then Murder #3 (sequential) | 4 |
| RT_6 | mandatory banishment, then ballots | 3 or 2 |

Both paths terminate at 3 (or 2 by election).

### 3.3 Drift sources — REVISED IN v4

| Source | Delta | Repair | v3 observed |
|---|---|---|---|
| `ANCHOR_BREAK` (§6.6) | +1 | make-up murder at NIGHT_3 | 19.6% |
| `SUCCESSION_ACCEPT` (§9.6) | +1 | **make-up murder at NIGHT_3 (NEW)** | 13.1% |
| `ZERO_VOTE_COUNCIL` (§5.5) | +1 | **eliminated — now impossible** | 0.325/game |
| `SWEEP_NO_MURDER` (§9.7) | +1 per void window | none — expected, not repaired | new in v4 |

Log all as `FLOAT_EVENT`. Referee must not attempt unspecified repairs.

**`NIGHT_3` may now owe up to three eliminations** — Anchor make-up, Succession
make-up, and Murder #3 — when both repairs are pending in the same game. The count
resolves correctly. Log `REF_ADJUDICATION: TRIPLE_NIGHT_3`. Combined probability is
roughly 2–3%; flagged for Jack's attention as a live-play pacing problem (three
sequential Traitor negotiations in one night), not a mechanical defect.

---

## 4. PHASE MACHINE

Strict sequence. Each phase is `phase(state) -> state`.

```
SETUP
THU_ARRIVAL           no mechanics, no information exchange
COCKTAIL_HOUR         Anchor assigned secretly, Runner -> random FAITHFUL
RT_0                  prompt, discussion, NO NOMINATION, NO VOTE, Anchor pass
NIGHT_1               Murder #1
FRI_DISCOVERY         absence revealed; Will delivered
RT_1                  standard council (nomination)
RT_2                  standard council (nomination)
[ROPE_CHECK]          if alive == 9 and rope not yet raised -> rope up
RT_3                  council (nomination; bloc voting iff roped)
[ROPE_CHECK]          if alive == 9 and rope not yet raised -> rope up
SAT_AFTERNOON         Succession offer window if live (§9.4)
SAT_DINNER            Murder #2 — plate placement, swaps, resolution
RT_4                  council (nomination); ANCHOR RESCINDED at conclusion
SUN_TRANSMISSION      Last Transmission
RT_5                  council (nomination)
NIGHT_3               make-up murders (if owed) THEN Murder #3
RT_6_FINALE           mandatory banishment -> Ballot 1 -> optional Ballot 2
END                   score
```

**A sweep check runs after every eliminating phase.** If living Traitors == 0, set
`sweep_active = true`. The game does **not** end (§9.7 — changed in v4).

`ROPE_CHECK` runs after RT_2 and after RT_3. Rope raises at most once per game.
If `alive != 9` at both checks, the rope never raises — log
`REF_ADJUDICATION: ROPE_NEVER_TRIGGERED`.

Unrope occurs at the conclusion of the Council the rope spans — normal path RT_3,
drift path RT_4 — regardless of banishment outcome.

---

## 5. COUNCILS

### 5.1 Sequence — RESTRUCTURED IN v4

1. Runner delivers exactly one discussion prompt, referencing the most recent
   murder or banishment.
2. **Free discussion.** One round. Model per §5.2.
3. **Nomination round** (§5.3). Skipped at RT_0, skipped at RT_6, skipped when
   `alive < 5`.
4. **Slate resolution** (§5.3.2). Provisional slate of 3 → lowest dropped →
   2 finalists.
5. **Defense round** (§5.3.3). Each finalist speaks once.
6. **Vote** (§5.3.4). Simultaneous, restricted to the 2 finalists.
7. Banishment resolves.
8. Anchor pass (RT_0 through RT_3 only; see §6.3).

### 5.2 Discussion model
Live play is free-form, overlapping, simultaneous, time-limited. Not reproducible
by turn-taking agents.

Implementation: single speaking pass in randomized order. Each agent sees all prior
speech in that pass.

Known bias — print on every report: this model preserves positional information
asymmetry but discards volume, dominance, and interruption. It under-models loud
archetypes and over-models quiet ones. Archetype survival figures must be read
against this.

**v4 note:** the nomination round (§5.3) is a second, structured speaking pass and
partially compensates — it forces every player to commit a public position, which
the free-discussion model otherwise lets quiet archetypes avoid. Expect A03 and A10
survival to move on this change alone.

### 5.3 Nomination, slate, defense, vote — NEW IN v4

#### 5.3.1 Nomination round
- Applies at **RT_1 through RT_5**, and only when `alive >= 5`.
- **Sequential and spoken**, in an order randomized by the referee each Council.
  Order is logged.
- Every living player names exactly one other living player. No abstention
  (`ILLEGAL_ACTION: ABSTENTION`). No self-nomination
  (`ILLEGAL_ACTION: SELF_NOMINATE`).
- Nominations are **public and durable** — the full record (who named whom, in what
  order) is visible to all and persists in the transcript.
- Nomination order is the tiebreak resource for §5.3.2 and §5.4. Being nominated
  earlier is mechanically advantageous to nominate and disadvantageous to receive.

**Rationale for sequential rather than simultaneous:** an ordering is required for
the deterministic tiebreak ladder, and public sequential accusation is what the
February table will actually do. The *vote* remains simultaneous (§5.3.4), which
preserves the Flag 4 anti-bandwagon protection where it matters.

#### 5.3.2 Slate resolution
Tally nomination counts.

- **Provisional slate** = the top 3 distinct nominees by count.
- **Ties for any slate position: the earliest-nominated player advances.** Log
  `REF_ADJUDICATION: SLATE_TIE_EARLIEST`.
- The **lowest-ranked of the 3 is dropped**, publicly and by name. The drop is a
  logged, visible event (`SLATE_DROP`) — the third nominee is named aloud before
  being removed from contention.
- **2 finalists** remain and go to defense and ballot.

Degenerate cases:
- **Exactly 2 distinct nominees:** both are finalists. No drop occurs. Log
  `REF_ADJUDICATION: SLATE_ONLY_TWO`.
- **Exactly 1 distinct nominee** (unanimous nomination): that player is **banished
  immediately without a vote or defense.** Log
  `REF_ADJUDICATION: SLATE_SOLE_NOMINEE`. This cannot produce count drift and is
  the intended pressure against casual unanimous pile-ons.
- **More than 3 distinct nominees:** only the top 3 enter the provisional slate;
  the remainder are not named as nominees.

#### 5.3.3 Defense round
Only the **2 finalists** speak, once each, in nomination order (earlier-nominated
first). Skipped entirely on `SLATE_SOLE_NOMINEE`.

Agent protocol: `defend(state, pid) -> str`.

#### 5.3.4 Vote
- **Restricted to the 2 finalists.** A ballot naming anyone else is
  `ILLEGAL_ACTION: VOTE_OFF_SLATE`; reject and re-prompt, then coerce (§13.3).
- Simultaneous commitment, then full public reveal of every ballot.
- No self-votes, no abstentions. Both finalists must vote, and each may only vote
  for the other; they therefore cancel, and the remaining players decide.
- Dead do not vote.
- Plurality of the two. No majority threshold.

#### 5.3.5 Small-count exemption
When `alive < 5`, the nomination, slate, and defense steps are **skipped entirely**
and the Council runs a direct vote across all living players under §5.3.4's
simultaneous-and-public rules, with the legal target set being every living player
other than the voter. Log `REF_ADJUDICATION: NOMINATION_EXEMPT_SMALL_COUNT`.

`RT_6` is exempt **by name**, not by count, so that drift cannot introduce a
nomination round into the finale.

### 5.4 Tie procedure — RPS DELETED IN v4

A two-name ballot cannot produce a three-way tie. A 1–1-style split remains
possible. Resolve in strict order, stopping at the first step that breaks it:

1. **Second discussion round, then revote.** All living players except the two
   finalists speak once; the ballot is re-cast under §5.3.4 rules.
2. **Higher nomination count carries.** The finalist who received more nominations
   is banished.
3. **Earliest nomination carries.** The finalist nominated earlier in the round is
   banished.

Step 3 always resolves, because nomination order is a strict total ordering. Log
`REF_ADJUDICATION: TIE_LADDER_STEP_<n>`.

`RPS_RESOLUTION` is **removed from the rules entirely.** Any occurrence in a run is
an implementation defect, not a game outcome. Assert its count is zero.

Under the small-count exemption (§5.3.5) there is no nomination record, so the
ladder collapses to step 1 repeated. If a tie persists after **three** revotes,
resolve uniformly at random and log
`REF_ADJUDICATION: SMALL_COUNT_TIE_FORCED`. This is the only remaining random
elimination in the ruleset and is reachable only at `alive < 5`.

### 5.5 Bloc vote (roped Councils only) — REVISED IN v4
Applies to whichever Council the rope spans — RT_3 normal path, RT_4 drift path.

The nomination round runs normally and produces the 2-finalist slate before blocs
vote. **Blocs choose between the two finalists only.**

- Three blocs, one vote each. Unanimous or nothing — but see the backstop below.
- Up to three rounds of bloc-internal deliberation, each member seeing the others'
  prior-round proposals.
- **Backstop:** if a bloc has not reached unanimity after three rounds, the member
  who named their pick first and never moved off it carries the bloc, per §8.2's
  longest-standing procedure. Ties in standing resolve to the earlier-speaking
  member. Log `REF_ADJUDICATION: BLOC_BACKSTOP_APPLIED`.
- **A bloc can never cast nothing.** `ZERO_VOTE_COUNCIL` is removed from the
  ruleset; assert its count is zero.

**Finalists inside blocs.** A bloc may not cast its vote for a finalist who is a
member of that bloc — that would be a self-vote by the member.
- A bloc containing exactly one finalist must vote for the other finalist. Its
  deliberation is skipped; log `REF_ADJUDICATION: BLOC_FORCED_BY_MEMBERSHIP`.
- A bloc containing **both** finalists cannot legally vote and casts nothing. Log
  `REF_ADJUDICATION: BLOC_ABSTAINS_BOTH_FINALISTS`. With three blocs and two
  finalists, at least one bloc always contains neither, so a banishment still
  results and the count is preserved.
- Any unroped remainder players vote individually under §5.3.4.

Plurality across cast votes. Ties resolve by the §5.4 ladder.

---

## 6. THE ANCHOR

### 6.1 Properties
- Protects against murder only. Banishment ignores it entirely.
- Held by exactly one living player at a time.
- Breaks and exits permanently on its first successful block. At most one block and
  one Anchor make-up murder per game.
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
- No pass at RT_4; the token is rescinded at that Council's conclusion.
- The last protected player is therefore the RT_3 recipient, who covers
  `SAT_DINNER`.

### 6.4 Secrecy of meaning — soft secret
The Anchor's *function* is disclosed only to each holder, who is instructed to keep
it secret. **Disclosure is legal and unpunished.** False claims of holding it, or of
knowing its meaning, are legal.

Knowledge model:
- `knows_anchor_meaning: set[player_id]`, initially `{initial_holder}`.
- Every player who holds the Anchor is added on receipt. Knowledge is monotonic.
- A knowing player may disclose to any player they choose (agent decision).
- Strategy directive to Traitor agents (not a rule): a Traitor who learns the
  meaning informs all living Traitors immediately, and no one else.

Report `anchor_live_councils`. v3 baseline: a Traitor knows by council 2.04 on
average, in 70.7% of games.

### 6.5 Traitor pass behaviour
Traitors holding the Anchor preference passing to a living fellow Traitor. Strategy
directive, not a rule. Log `ANCHOR_PASS` with roles of both parties.

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

### 6.8 Holder banished while holding
**Default:** the banished holder makes the pass as their final act, before leaving
play. The token continues to circulate. Log
`REF_ADJUDICATION: ANCHOR_HOLDER_BANISHED`. Observed 0.38×/game. Still open (§15).

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
When the rope spans a murder window (drift path only), all living Traitors are
assigned to the same bloc, padded with Faithful to size three. The override
supersedes §7.2.

Rationale: information is bloc-constrained and enforced (§7.4). Without the
override, Traitors split across blocs cannot satisfy the unanimity requirement for
Murder #2.

With 3 Traitors alive, the Traitor bloc contains zero Faithful. This is legal —
plate placement is global (§8.3), so target reach is unaffected.

### 7.4 Information constraint
While roped, a player may exchange private information **only** with their two bloc
partners. Any private channel to a non-partner is
`ILLEGAL_ACTION: ROPE_INFO_BREACH`. Enforced by the referee — filtered from the
agent's visible transcript.

Public speech (Council discussion, **the nomination round**, defense, table talk) is
unaffected.

### 7.5 Voting while roped
See §5.5.

### 7.6 Unrope
At the conclusion of the spanned Council, regardless of whether a banishment
occurred.

---

## 8. MURDERS

### 8.1 General
- Exactly three windows: `NIGHT_1`, `SAT_DINNER`, `NIGHT_3`. Plus make-up murders
  at `NIGHT_3` if owed (§3.3).
- Murder is mandatory. Traitors may not decline.
- Target selection must be unanimous among **living** Traitors. At 2, both must
  agree. At 1, that Traitor decides alone. **At 0, the window produces no victim
  (§9.7).**
- Traitors may not target Traitors. `ILLEGAL_ACTION: TRAITOR_TARGETS_TRAITOR`.
- The Anchor holder is a legal target. Targeting them triggers §6.6.

### 8.2 Deadlock procedure
Three rounds of Traitor discussion. If no unanimous target emerges:

**Longest-standing unbroken proposal wins.**

- A Traitor's standing begins at the round they first named a target and **breaks
  the moment they switch.** Switching and switching back restarts the clock at the
  later round.
- Tie in standing: uniform random between them. Log.
- No Traitor has standing: uniform random from all names proposed across the three
  rounds. Log.
- At 1 living Traitor, unanimity is trivially satisfied; the procedure never runs.

Log `REF_ADJUDICATION: TRAITOR_DEADLOCK_FORCED` on any forced resolution.

**Metric:** log per-Traitor `standing_wins`. This mechanic rewards naming first and
refusing to move; if one seat wins a large majority of contested targets, the
mechanic contains a dominant strategy and should be reported prominently.

This procedure is also the backstop for bloc votes (§5.5).

### 8.3 Murder #2 — Murder in Plain Sight
Saturday dinner plate mechanic.

Plate set: crossed ice axes ×3, knotted rope ×3, signal flags ×3, storm lantern ×2,
**cairn ×1**. The cairn is the Murder Plate.

The tell is the **motif on the face**. No underside mark, no foot ring, no hairline
variation. Any such reference is a defect.

Sequence:
1. **Placement (pre-meal, global reach).** Traitors set the table together and may
   place the cairn at any seat. Placement is the murder decision, executed publicly.
2. **Seating.** Normal path: unconstrained. Drift path (roped): seating is by bloc.
3. **Swaps (during meal, local reach).** A player may move plates only within
   physical reach. Normal path: global. Drift path (roped): bloc-local.
   Out-of-reach attempts are `ILLEGAL_ACTION: PLATE_OUT_OF_REACH`.
4. **Resolution.** Whoever holds the cairn at the end of dinner is the victim.

**THE MURDER FOLLOWS THE PLATE.** Intent is irrelevant.

- A swap may kill a Traitor. Legal outcome.
- A swap onto the Anchor holder voids the murder and breaks the token (§6.6).
- **Chain swaps: resolve final table state only.** No intent tracking, no ordering.

Faithful knowledge: the Faithful do **not** know this mechanic exists. Victim learns
after dinner, simultaneously with everyone else.

**Detection model.** Counterplay is gated on reasoning, not a die roll. An agent
receives a detection opportunity only if it independently raises the plates, the
china, or the motifs in its own reasoning during `SAT_DINNER`. Do not implement a
flat probability.

Correct identification requires reasoning that the cairn specifically is the mark.
Every other motif is a tool of the living; the cairn is a marker of the dead.

**Known defect carried from v3:** measured detection concentrates in A03 rather than
A06, and A06's reasoning routes to the vote record rather than to physical objects.
The gate may be measuring vocabulary rather than noticing. Not fixed in v4 —
flagged for a dedicated pass.

### 8.4 NIGHT_3 with make-up owed
Sequential kills, resolved in this order:
1. Anchor make-up murder (if owed): full selection procedure, full negotiation.
2. Succession make-up murder (if owed, new in v4): full selection procedure, full
   negotiation.
3. Murder #3: fresh selection procedure, fresh negotiation.

A target may not be selected twice within the night. Each victim writes a Will,
delivered separately (§11.1). The exclusion set must drop null entries before
filtering.

If all three fire, log `REF_ADJUDICATION: TRIPLE_NIGHT_3` (§3.3).

### 8.5 Murder #3
Standard overnight murder. Anchor has left play; cannot be blocked.

---

## 9. SUCCESSION

Supersedes the auto-win on Reference Card 3.

### 9.1 Trigger conditions
All must hold:
- Exactly **1** living Traitor.
- A murder window is opening.

Available windows: `SAT_DINNER`, `NIGHT_3`, and the `NIGHT_3` make-up windows.
`NIGHT_1` is impossible (3 Traitors alive).

### 9.2 Election
**Succession is optional.** The lone Traitor elects whether to use the window for
recruitment or for a normal murder. Log the election.
Defaulted to optional; confirm (§15).

### 9.3 Offer
- The lone Traitor selects the recruit.
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
every rule in §8.3. The resulting elimination is logged under phase `SAT_DINNER`.

At `NIGHT_3`, a decline is an ordinary overnight murder.

### 9.6 Acceptance and drift — REVISED IN v4
Acceptance produces zero eliminations in a window that owed one.

**A Succession make-up murder is owed, resolved at `NIGHT_3` (§8.4).** The drift is
repaired, not absorbed. The game returns to the standard count and ends at Final 3.

Log `FLOAT_EVENT: SUCCESSION_ACCEPT`.

The successor enters with a clean voting record, no Traitor history, and sincere
prior play. The successor participates in the make-up murder selection as a living
Traitor.

**v3 behaviour (absorbed, game ran to Final 4) is superseded.** This change exists
to bring `FINALE_OVERSIZED` under 0.10/game.

### 9.7 Zero living Traitors — REVISED IN v4
A sweep to 0 living Traitors no longer ends the game.

**On the sweep:**
1. Set `sweep_active = true`. Log `FLOAT_EVENT: TRAITOR_SWEEP` with the phase.
2. **Play continues normally.** All remaining Councils run in full — nomination,
   defense, vote, banishment.
3. Every subsequent murder window produces **no victim**; no selection occurs
   because no Traitor exists to select. Log `FLOAT_EVENT: SWEEP_NO_MURDER` per
   voided window. No Will is written for a voided window.
4. Succession cannot trigger (§9.1 requires exactly 1).
5. The game runs to `RT_6` and resolves normally.
6. **Faithful win is declared at the finale reveal**, not at the moment of the
   sweep.

**Count consequence:** the game ends above Final 3, by one per voided murder window.
This is **expected, not drift to be repaired.** Invariant checks must treat
`sweep_active` games as explained. Do not log `FINALE_OVERSIZED` when
`sweep_active` is true — the oversized finale is the intended outcome of this
branch.

**Runner discipline (live play, not simulation):** the Recorder gives no indication
that the murders have stopped. The absence is the only signal, and the players must
draw their own conclusion. No confirmation, no hint, no change in delivery.

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
Dead Traitors are numerically outnumbered in the Court by Sunday (typically
5F:1–2T). Under forced plurality they can influence but not carry an answer. This
makes the Transmission a structurally pro-Faithful mechanic and one of the few
reliable information injections the Faithful receive.

**Metric:** report Faithful win rate with the Transmission enabled vs. neutralized.

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
- The `SAT_DINNER` plate victim writes one. Each make-up murder victim writes one.
- At `NIGHT_3` with multiple victims, each writes one, delivered separately.
- **No Will is produced for a window voided by a sweep (§9.7) or by the Anchor
  (§6.6)** — there is no victim.

### 11.2 Recipient selection
- **First successful murder:** the writer chooses the recipient.
- **Every murder after:** the Court chooses as a group.

"First" means first murder that **produces a victim.**

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

### 12.1 RT_6 Finale

RT_6 opens with 4 living players on the normal path (more under sweep or drift).
**No nomination round runs at RT_6** (§5.3.5). It runs in three steps.

**Step 1 — mandatory banishment.** Prompt, one discussion round, direct vote across
all living players (§5.3.4 rules, full legal target set), §5.4 ladder collapsed to
the small-count procedure. This is the ninth elimination and brings the count to
Final 3.

**Step 2 — Ballot 1: End The Game or Banish Again.** Binary. All remaining players
vote. Plurality. With 3 voters this always resolves 2–1 or 3–0. With 4+ voters a
tie is possible; **tie defaults to ending the game.** Log
`REF_ADJUDICATION: FINALE_OVERSIZED` when more than 3 players reach this ballot,
**except when `sweep_active` is true** (§9.7).

**Step 3 — Ballot 2: banishment.** Only if Ballot 1 returns Banish Again. Direct
vote, no self-votes.
- At 3 voters: a 1–1–1 tie → **game ends immediately at Final 3.**
- At 3 voters: 2–1 → that player is banished; game ends at **Final 2.**
- At 4+ voters: §5.4 small-count procedure applies; game ends one lower after the
  banishment.

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

Public and durable: all vote ballots, all banishment outcomes, **the full nomination
record including order**, **slate composition and the dropped nominee**, **defense
speeches**, all Anchor passes (location only, not meaning), both Transmission
halves, Council prompts.

Private: role assignments, Traitor deliberation, Court deliberation, Will contents
and recipients, initial Anchor assignment, Anchor meaning, Succession offers,
bloc-internal speech while roped.

### 13.2 Illegal action catalogue
`SELF_VOTE`, `SELF_NOMINATE`, `VOTE_OFF_SLATE`, `ABSTENTION`, `DEAD_VOTE`,
`DEAD_NOMINATE`, `TRAITOR_TARGETS_TRAITOR`, `MURDER_OUT_OF_WINDOW`,
`ANCHOR_SELF_RETAIN`, `WILL_REVEALS_ROLE`, `WILL_OVER_LENGTH`, `ROPE_INFO_BREACH`,
`MALFORMED_OUTPUT`, `BLOC_VOTE_NON_UNANIMOUS`, `PLATE_OUT_OF_REACH`.

`BLOC_VOTE_NON_UNANIMOUS` is retained as a **diagnostic** — it now logs when the
§5.5 backstop is invoked rather than when a bloc fails to vote. It no longer
implies a lost vote.

The frequency table of these across all runs is the **rulebook ambiguity list.**

### 13.3 Coercion defaults (second invalid response)
| Action | Default |
|---|---|
| nomination | uniform random legal target |
| vote | uniform random legal finalist |
| defense | silence |
| murder selection | §8.2 deadlock procedure |
| anchor pass | uniform random living player |
| will | empty string |
| speech | silence |
| plate placement | uniform random legal seat |
| succession election | murder (not recruit) |
| transmission question/answer | §10.2 plurality |

---

## 14. DIVERGENCE FROM `lodge_rules_narrative_TEANAWAY`

This canon governs. The player-facing document must be amended before February.

| # | Document | Canon |
|---|---|---|
| 1 | Anchor holder protects self or another; self-protection notifies Traitors | Mandatory pass to another player |
| 2 | Anchor passes Councils 1–3; rescinded Sunday morning | Passes RT_0–RT_3; rescinded at conclusion of RT_4 |
| 3 | Targeted holder simply saved, no consequence | Breaks, exits, count drifts, make-up murder |
| 4 | Votes written; Runner calls each player by name with explanation | Simultaneous commitment, public reveal |
| 5 | Tie → unspecified "secret mechanism" | Deterministic ladder; no random resolution above 4 alive |
| 6 | Traitors *may* murder; Plain Sight at Runner's discretion | Three mandatory murders, fixed windows |
| 7 | No mention of bloc voting during Roping Up | Blocs vote from the slate, with backstop |
| 8 | **No nomination or accusation step** | **Nomination round, slate of 3, drop to 2, defense round** |

Absent from the document entirely: RT_0, Cocktail Hour Anchor assignment,
soft-secret Anchor meaning, trigger-based roping, Succession, the RT_6 three-step
finale, sweep continuation.

**Item 8 is new in v4 and is the largest player-facing change in the ruleset.** The
Council procedure the players will read is now materially different from every prior
draft. This amendment is no longer deferrable to after the simulation — a player
cannot be handed a rules sheet that omits the nomination round.

---

## 15. OPEN — REQUIRES RULING

| # | Item | § | Default taken | Observed |
|---|---|---|---|---|
| 1 | Anchor holder banished while holding — pass or exit? | 6.8 | Passes as final act | 0.38×/game |
| 2 | Succession optional vs. mandatory when triggered | 9.2 | Optional | 28.3% trigger |
| 3 | Anchor pass at RT_4 — rescinded outright, or passed then rescinded? | 6.3 | Rescinded, no pass | every game |
| 4 | Rope never triggering — confirm fallback is "no roping" | 4 | No roping | 0.1% |
| 5 | **Traitor/Faithful win split** — measured 9:1, target 6:4 | 12 | unchanged in v4 | — |

**Item 5 is deliberately unaddressed in this version.** Changes 1–3 remove
mechanical noise that suppressed Faithful performance. Re-measure the split against
v4 before selecting a balance lever. Candidate levers, in order of expected effect:
Traitors 3→2; mandatory Final 2; narrowing Succession; adding Faithful information
injections.

**Resolved in v4:** zero living Traitors (v3 §15 item 2) — now ruled, see §9.7.

---

## 16. BUILD STAGES

1. **Skeleton — COMPLETE.** Referee + uniform-random bots. 17,000 games, zero
   invariant violations under v3.
2. **Heuristic bots — RUNNING.** Archetype-parameterized decisions, free, thousands
   of games. Produces the structural/distributional report.
3. **LLM agents — RUNNING.** Sonnet, N=2, case studies. Produces the
   reasoning/interpretive report.
4. **Iterate.** **One rule change per version. Same seeds. Diff reports.**
   `CHANGELOG.md`, one line per version: what changed, why, what moved.

**v4 violates the one-change rule deliberately** — changes 1–3 are a single
coupled fix to one problem (the machine discarding Faithful decisions), and
changes 4–5 have no effect on the win split. Do not add a balance change to this
version.

---

## 17. REPORT METRICS

Required in every aggregate report. New in v4 marked ▲.

- Traitor win rate, ±95% CI.
- Ending council distribution; frequency of Final 4 / Final 3 / Final 2.
- Elimination timing histogram by seat and by role.
- `REF_ADJUDICATION` frequency table — **the bug list.**
- `ILLEGAL_ACTION` frequency table — **the ambiguity list.**
- `FLOAT_EVENT` frequency by type.
- Archetype survival rate, annotated with the §5.2 bias warning.
- **Banishment accuracy as Faithful, per archetype.** Base rate ~25–33%. Any
  archetype below base rate indicates a defective parameter mapping rather than a
  game property. **Run this diagnostic before acting on §15 item 5.**
- ▲ **Nomination accuracy per archetype** — share of nominations landing on an
  actual Traitor.
- ▲ **Nomination-to-banishment conversion** — how often the top nominee is banished.
- ▲ **Dropped-nominee analysis** — how often the dropped third was a Traitor.
- ▲ **Tie ladder step distribution** — how often each step resolves.
- ▲ `SLATE_TIE_EARLIEST` and `SLATE_SOLE_NOMINEE` frequency.
- ▲ `BLOC_BACKSTOP_APPLIED` frequency.
- ▲ Sweep frequency and mean councils played after the sweep.
- Anchor: block rate, `anchor_live_councils`, holder-targeting rate, pass-chain
  leakage.
- Plate: detection rate by archetype, swap rate, swap-kills-Traitor rate.
- Traitor deadlock: forced-resolution rate, per-seat `standing_wins`.
- Succession: trigger rate, accept/decline split.
- Transmission: Faithful win rate enabled vs. neutralized.
- RT_6 Ballot 1 split by role.

**Assert zero:** `RPS_RESOLUTION`, `ZERO_VOTE_COUNCIL`, `THREE_WAY_TIE`. All three
are removed from the ruleset; any occurrence is an implementation defect.

---

## 18. STANDING PRINCIPLE

The rulebook prose is the deliverable, not the code. The simulation is an
instrument, not an authority. Where the data and the intended experience conflict,
the experience governs and the finding is recorded.

*Canon v4.*
