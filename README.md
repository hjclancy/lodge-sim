# The Lodge — Simulation

Implements REFEREE CANON v4 and ARCHETYPES v1.

## Canon v4 — what changed
Councils gained a **nomination round**: every living player names one other
player, out loud and in a logged order, seeing every nomination made before
theirs. The three most-nominated form a provisional slate, the lowest is dropped
by name, the remaining two defend themselves, and **the ballot is restricted to
those two**. Ties resolve on a deterministic ladder — revote after discussion,
then higher nomination count, then earliest nomination — and **RPS is gone**.
Blocs vote from the same slate and can never cast nothing: after three failed
rounds the longest-standing member carries the bloc. Succession acceptance now
owes a make-up elimination at `NIGHT_3`, which can therefore resolve up to three
kills. A zero-Traitor sweep no longer ends the game: play continues to `RT_6`,
later murder windows produce no victim, and the Faithful win is declared at the
finale reveal.

Measured against the v3 baseline at 5,000 heuristic games:

| | v3 | v4 | target |
|---|---|---|---|
| `THREE_WAY_TIE` | 0.79/game | **0** | 0.002 |
| `ZERO_VOTE_COUNCIL` | 0.325/game | **0** (removed from the ruleset) | 0.002 |
| `FINALE_OVERSIZED` | 0.34/game | **0** | 0.10 |
| `RPS_RESOLUTION` | present | **0** (removed from the ruleset) | 0 |
| Traitor win | 88.1% | 87.4% | 60% |

The win split is **deliberately unaddressed** in v4 (canon §15 item 5, §16.4).
It is the input to the next decision, not a problem to fix in this version.

## Stage 1 — skeleton (complete)
    python3 run_skeleton.py [N] [swap_prob] [coord]

Random bots, zero API calls. 17,000 games run, zero invariant violations.
`coord=1.0` models agents that can reach agreement; `coord=0` is the torture test.
Exit 0 = all invariants held.

## Stage 1.5 — structural / distributional (heuristic bots, complete)
    python3 run_structural.py                 # 5000 games, $0, ~8s
    python3 run_structural.py --games 20000

The twelve archetypes' ten parameters live in `archetypes.json`; `archetypes.py`
loads them at import and keeps the prose personas. To run one batch on different
numbers without committing them, set `LODGE_ARCHETYPE_OVERRIDES` to a JSON object
(or a path to one) shaped like `{"A03": {"trust": 0.8}}`. A typo — unknown
archetype, unknown parameter, a value outside [0, 1] — raises rather than being
ignored, because a silently dropped override produces a report that looks like a
finding and isn't. Every report records the exact set it ran on, with a digest.

Deterministic archetype-parameter bots (`heuristic_bots.py`), not random and
not reasoning — a modeling choice, explicitly flagged as such at the top of
that file. Runs through the unmodified referee at volumes the Claude tier
can't afford, and asserts the stage-1 invariants on every game. Emits
`reports/structural_<date>.html`: win rates, survival curves, mechanic
firing rates. Answers "how often," not "why" — see the disclaimer in the
report itself.

## Stage 2 — agents
    python3 run_agents.py --games 5 --mock              # free plumbing test
    python3 run_agents.py --games 5                     # real, ~$3
    python3 run_agents.py --games 200 --budget 150      # full run

Requires `ANTHROPIC_API_KEY`. `--budget` halts the run at a USD ceiling.

### rules/
`rules/public_rules.md` and `rules/traitor_brief.md` are what agents read. As of
2026-07-22 the placeholder headers are gone (deliberate call: run the batch on
clean canon-derived text) but the body is still **canon-derived, not the
verbatim player-facing documents** the twelve guests receive — see
`rules/README.md`. Testing the canon against a restatement of the canon finds
canon-level bugs, not document-level ones; the gap between intent and the
actual Rules Sheet/Traitor Brief text is a separate, not-yet-tested question.

## Stage 3 — reasoning / interpretive report (Claude reads Claude)
    python3 run_reasoning_report.py --games 3 4 --winners TRAITORS TRAITORS \
        --final-alive 3 3 --traces-dir traces

Takes real stage-2 trace files and produces prose case studies, not stats — a
separate Claude pass per game, reading (1) a small set of facts extracted
deterministically in Python (role layout, elimination order/cause — see the
`note` field it emits for exactly what's inferred vs. verified) and (2) the
full raw reasoning trace, then writing the role layout, the elimination arc,
notable reasoning moments, how each mechanic played, and a closer. Emits
`reports/reasoning_<date>.html`. N is always small (these are case studies);
no "how often" claim belongs here — that's `run_structural.py`'s job.
`--winners`/`--final-alive` come from the run_agents.py console output line,
since that's the only persisted record of the authoritative outcome.

## Running it from GitHub (no terminal)

Both reports can be produced and read entirely from the browser. Actions runs
the harness; the results are committed back to `main` and published to GitHub
Pages.

### Trigger a run
**Actions** tab → pick the workflow in the left sidebar → **Run workflow** →
fill the inputs → **Run workflow**.

| workflow | inputs | needs a key | cost | takes |
|---|---|---|---|---|
| **Structural report (heuristic bots)** | `games` (default 5000), `archetype_overrides` (optional JSON) | no | $0 | ~1 min |
| **Reasoning report (Sonnet batch)** | `games` (default 2), `budget` (default 10), `mock` (default false) | yes | up to `budget` | ~15 min/game |

Each run appends a report to `reports/`, appends a row to
`reports/history.json`, rebuilds `reports/index.html`, commits all of it to
`main`, and redeploys Pages. Nothing is ever overwritten: a second report on
the same day lands as `structural_2026-07-27-2.html`, so every batch stays
readable. The Sonnet workflow also commits its per-game traces to
`traces_ci/<timestamp>/`. Live output is in the run's log, and a copy is on
the run summary page along with the Pages link.

Set `mock: true` on the reasoning workflow to test the plumbing with
`llm.MockLLM` — zero API calls, zero dollars, no key required. It commits
nothing and publishes nothing; its output comes back as a run artifact.

### Re-parameterising a run
The structural workflow's `archetype_overrides` box takes JSON that replaces
archetype parameters **for that run only**. Nothing is written back to
`archetypes.json`, no commit is made, and the next run without an override is on
the committed defaults again. The value is staged to the runner's temp directory,
outside the checkout, so it cannot reach a commit even by accident.

Build the JSON on the dashboard's **Parameters** page — move sliders, press *Copy
config JSON*, paste. It copies only what you moved, which is what the input wants
and what keeps the report's override list readable. The report for that run names
every replaced parameter and records a digest of the whole set; the history table
carries the digest in its **Params** column, so two batches that differ only in
parameters can be told apart later.

Overrides bite hard on the structural tier and barely at all on the reasoning
tier: heuristic bots *are* these numbers, whereas the Claude agents read the prose
persona plus a one-line rendering of them. There is deliberately no override input
on the reasoning workflow — it would cost $10 to move a number that changes one
line of a prompt.

### The budget cap
`budget` is a ceiling on the whole run, both the agent games and the
narrative pass. It is enforced in three places, because the input box is the
part a typo can reach:

1. The workflow clamps the input to **$0.50–$25.00** and `games` to **1–10**
   before the harness starts, and rejects anything that isn't a number.
2. `scripts/run_reasoning_ci.py` clamps again, so a run started any other way
   is bounded too.
3. `BudgetedLLM` refuses individual API calls once the agent share of the
   ceiling is spent. `run_agents.py` checks its budget only *between* games,
   which lets one game overshoot by a whole game's worth of calls; this check
   is per call. Calls already made are still paid for — nothing can undo
   those — but the ceiling can only be exceeded by the handful of ~400-token
   calls in flight when it trips.

The ceiling is split: the agent stage gets everything except a reserve for
narration, and whatever the agents leave unspent flows back to it. If the
money runs out mid-batch, the games that did finish are still reported and
the shortfall is stated in the report header and the history row. For
calibration: the 2026-07-22 Sonnet 5 batch cost **$2.50–$3.20 per game** at
`effort=high`, so the $10 default buys about three.

### Reading the results — the Pages URL
`https://<owner>.github.io/lodge-sim/`

The exact URL is on **Settings → Pages**, on every workflow run summary, and
on the *github-pages* deployment in the Actions sidebar.

Four pages, each a single self-contained file:

| page | what's on it |
|---|---|
| **Reports** (`index.html`) | every report by date with links, the history table, and a line chart of any metrics you tick across every batch |
| **Charts** (`charts.html`) | pick a batch: archetype survival by role, elimination timing by phase, plate detection by archetype, float event rates |
| **Parameters** (`params.html`) | 12 × 10 sliders, *Copy config JSON*, *Reset to defaults* |
| **Traces** (`trace.html`) | any published game's decision timeline, filtered by player, phase or tag, with the full reasoning text |

Each reasoning report links per game straight into the trace viewer, and each
report with exported data links to its charts from the reports list.

Two notes on how this is built. Charts use Chart.js from a CDN — the only
external request the site makes; if it is blocked, the pages say so rather than
showing empty boxes, and the same numbers are in the report tables. And
`charts.html` and `trace.html` read their data with `fetch`, which browsers
refuse on `file://` URLs, so opening those two from disk shows an explanatory
message: to preview locally, run `python3 -m http.server` inside `reports/`.
`index.html` and `params.html` inline everything and work from disk.

### How it looks — HOUSE STYLE v3
Every page on the site, dashboard and standalone report alike, is styled from
one place: `report_common.CSS`, which carries the design system's tokens
verbatim and maps them onto role variables (`--bg`, `--surface`, `--text`,
`--rule`, `--accent`). Change a token there and the whole site moves.

The rules that actually constrain what gets built here:

* **Colour is information, never decoration.** A view is ~89% neutral. Cobalt
  marks one thing — the active nav tab, a slider you moved, a link. Vermilion
  appears in exactly one place on the site, the Traitor edge in the trace, and
  only ever alongside Cobalt.
* **Every chart is one family of tints** — Mode A, the Cobalt ramp. No chart
  mixes families or introduces a foreign hue. Mono ramps imply ordering, so
  nominal categories are separated by position, direct label, dash and point
  shape instead.
* **Nothing is encoded by colour alone.** Exceptional bars are marked ▼ on the
  axis, roles are spelled out in words, status pills carry their state as text.
  Every page reads in grayscale, and all text clears 4.5:1 (3:1 for large) in
  both the light and dark schemes.
* **Flat.** Hairlines and fills, no shadows; 8pt spacing; 4px radius on cards
  and controls, 0 on tables and rules.

Roboto and Roboto Mono are named first in the font stacks but no webfont is
fetched — the reports are self-contained by design, and the system sanctions
the system-ui/Arial fallback. The dark scheme is an extension: the spec is
light-only, so dark reverses the neutrals and moves the accent up the Cobalt
ramp to `#84A2FA`, which Cobalt itself cannot reach on an Ink ground.

Reports already committed are one-shot outputs — re-running the simulation to
restyle one would change its numbers. `scripts/restyle_reports.py` swaps their
embedded `<style>` block for the current CSS and touches nothing else; both
workflows run it before rebuilding, and `--check` fails if any report is stale.

### One-time setup
**Pages.** Settings → Pages → **Source: GitHub Actions**. Branch-based Pages
can only serve `/` or `/docs`, so `reports/` is published by
`.github/workflows/pages.yml`, which uploads that directory and nothing else.
The two report workflows call it directly after committing rather than
letting the push trigger it — a push made with `GITHUB_TOKEN` does not start
another workflow, so a push-triggered deploy would silently never run.

**API key.** Settings → Secrets and variables → Actions → **New repository
secret**, named exactly `ANTHROPIC_API_KEY`, value your key from
console.anthropic.com. Only the reasoning workflow reads it; the structural
workflow never sees it. Without it that workflow fails on its first step with
a message saying so, before spending anything. Rotate it by updating the same
secret — nothing else refers to the key.

## Files
| file | role |
|---|---|
| `referee.py` | the engine. Owns all state, enforces all rules. |
| `referee_canon_v4.md` | the rules this implements. `referee_canon_v3.md` is kept for the diff. |
| `council_metrics.py` | the §17 v4 metrics — nomination accuracy, conversion, drops, tie ladder, sweep. Shared by both aggregate harnesses so they cannot define them differently. |
| `bots.py` | uniform-random agents (stage 1). |
| `run_skeleton.py` | stage-1 harness + invariant assertions. |
| `heuristic_bots.py` | archetype-parameter-driven agents (stage 1.5) — a modeling choice, not ground truth. |
| `run_structural.py` | stage-1.5 harness + HTML report generator. |
| `report_common.py` | shared HTML shell/CSS for the structural and reasoning reports. |
| `archetypes.py` | the twelve personas — prose here, numbers loaded from `archetypes.json`, plus override parsing and the parameter-set digest. |
| `archetypes.json` | the ten parameters for each of the twelve archetypes. The only file to edit to change them for good. |
| `agents_claude.py` | Claude-backed agents implementing the protocol. |
| `llm.py` | API client, JSON contract, retry, cost accounting, MockLLM. |
| `run_agents.py` | stage-2 harness + archetype reporting. |
| `run_reasoning_report.py` | stage-3 harness — fact extraction (Python) + narrative generation (Claude) + HTML report. |
| `rules/` | what the agents read. Canon-derived, not verbatim — see `rules/README.md`. |
| `traces/` | per-game reasoning traces, one JSONL per game. |
| `traces_mock/` | default output for `--mock` runs — kept separate so plumbing tests never overwrite real trace data. |
| `traces_ci/` | traces from Actions runs of the reasoning workflow, one directory per batch. |
| `reports/` | standalone HTML reports — `structural_<date>.html` (heuristic bots) and `reasoning_<date>.html` (Claude narrative reads of real games). Published as the Pages site. |
| `reports/index.html` | generated landing page: reports by date, history table, cross-batch line chart. |
| `reports/charts.html`, `params.html`, `trace.html` | the other three dashboard pages. All four are generated — edit the builders, not the HTML. |
| `reports/history.json` | one row per batch — the metrics the index table compares. |
| `reports/data/` | per-batch chart series (`<report>.json`) and published traces (`traces/<report>/`). Under `reports/` because Pages serves nothing else. |
| `scripts/run_structural_ci.py` | CI wrapper: imports run_structural's own run/render, adds a collision-free filename, a history row, chart data, and a `--games` clamp. |
| `scripts/run_reasoning_ci.py` | CI wrapper: stages 2 and 3 in one process under one USD ceiling, publishes traces, plus `--mock`. |
| `scripts/make_index.py` | builds all four dashboard pages from what is on disk. |
| `scripts/dashboard.py` | shared page shell, nav, chart palette (HOUSE STYLE Mode A), Chart.js loader, fetch helper. |
| `scripts/restyle_reports.py` | re-skins already-generated reports to the current `report_common.CSS`; `--check` fails if any is stale. |
| `scripts/page_charts.py`, `page_params.py`, `page_trace.py` | the three non-index pages. |
| `scripts/publish_traces.py` | copies traces into `reports/data/traces/` for the viewer; also a CLI for importing an older run's traces. |
| `scripts/report_history.py` | the `history.json` schema, and which of its fields get a column. |
| `.github/workflows/` | `structural.yml`, `reasoning.yml`, and the `pages.yml` they call to publish. |

## Cost
~220 API calls per game. At 200 games that is ~44,000 calls.
Rough estimate: Haiku $120–220, Sonnet $400–700 (transcripts grow through the
game, so later calls cost more). Run 5 first and read the traces.

## The three things to check on the first real run
1. **Nomination accuracy should clear the 25–33% base rate**, per archetype. An
   archetype below it is a defective parameter mapping in `heuristic_bots.py`,
   not a finding about the game. Canon §17 requires this diagnostic to come back
   clean before the Traitor/Faithful split is treated as a balance problem.
   Heuristic bots currently sit at 38% pooled.
2. **`BLOC_VOTE_NON_UNANIMOUS` now means the backstop fired**, not that a vote
   was lost — v4 §13.2 keeps the tag as a diagnostic. It should track
   `BLOC_BACKSTOP_APPLIED` exactly. A bloc casting nothing is no longer possible;
   `run_skeleton.check` asserts `ZERO_VOTE_COUNCIL` is zero.
3. **`PLATE DETECTION` should be non-zero and concentrated in A06/A12.** Zero
   means the reasoning gate never fires and §8.3 is untested. Detection is parsed
   from the agent's own unprompted reasoning — never convert it to a probability.
   Canon §8.3 carries a known v3 defect here: detection concentrates in A03
   rather than A06, and is not fixed in v4.

## Agent protocol
council_prompt, speak, **nominate**, **defend**, vote, bloc_propose, anchor_pass, murder_propose,
plate_detect, plate_swap, write_will, will_recipient_self, will_recipient_court,
succession_elect, succession_offer, succession_respond, transmission_questions,
transmission_answers, finale_continue.

The referee validates every return value. An agent cannot break a rule; it can
only be logged as having tried.
