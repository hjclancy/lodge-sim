# The Lodge — Simulation

Implements REFEREE CANON v3 and ARCHETYPES v1.

## Stage 1 — skeleton (complete)
    python3 run_skeleton.py [N] [swap_prob] [coord]

Random bots, zero API calls. 17,000 games run, zero invariant violations.
`coord=1.0` models agents that can reach agreement; `coord=0` is the torture test.
Exit 0 = all invariants held.

## Stage 1.5 — structural / distributional (heuristic bots, complete)
    python3 run_structural.py                 # 5000 games, $0, ~8s
    python3 run_structural.py --games 20000

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
| **Structural report (heuristic bots)** | `games` (default 5000) | no | $0 | ~1 min |
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
on the *github-pages* deployment in the Actions sidebar. It serves
`reports/index.html`: every report listed by date with links, plus
`history.json` rendered as a sortable table so metrics can be compared across
batches. The two kinds of row are not the same measurement and the page says
so at length — see the caveat on it.

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
| `bots.py` | uniform-random agents (stage 1). |
| `run_skeleton.py` | stage-1 harness + invariant assertions. |
| `heuristic_bots.py` | archetype-parameter-driven agents (stage 1.5) — a modeling choice, not ground truth. |
| `run_structural.py` | stage-1.5 harness + HTML report generator. |
| `report_common.py` | shared HTML shell/CSS for the structural and reasoning reports. |
| `archetypes.py` | the twelve personas as data. |
| `agents_claude.py` | Claude-backed agents implementing the protocol. |
| `llm.py` | API client, JSON contract, retry, cost accounting, MockLLM. |
| `run_agents.py` | stage-2 harness + archetype reporting. |
| `run_reasoning_report.py` | stage-3 harness — fact extraction (Python) + narrative generation (Claude) + HTML report. |
| `rules/` | what the agents read. Canon-derived, not verbatim — see `rules/README.md`. |
| `traces/` | per-game reasoning traces, one JSONL per game. |
| `traces_mock/` | default output for `--mock` runs — kept separate so plumbing tests never overwrite real trace data. |
| `traces_ci/` | traces from Actions runs of the reasoning workflow, one directory per batch. |
| `reports/` | standalone HTML reports — `structural_<date>.html` (heuristic bots) and `reasoning_<date>.html` (Claude narrative reads of real games). Published as the Pages site. |
| `reports/index.html` | generated landing page: every report by date, plus the history table. |
| `reports/history.json` | one row per batch — the metrics the index table compares. |
| `scripts/run_structural_ci.py` | CI wrapper: imports run_structural's own run/render, adds a collision-free filename, a history row, and a `--games` clamp. |
| `scripts/run_reasoning_ci.py` | CI wrapper: stages 2 and 3 in one process under one USD ceiling, plus `--mock`. |
| `scripts/make_index.py` | builds `reports/index.html` from the directory and `history.json`. |
| `scripts/report_history.py` | the `history.json` schema, and which of its fields get a column. |
| `.github/workflows/` | `structural.yml`, `reasoning.yml`, and the `pages.yml` they call to publish. |

## Cost
~220 API calls per game. At 200 games that is ~44,000 calls.
Rough estimate: Haiku $120–220, Sonnet $400–700 (transcripts grow through the
game, so later calls cost more). Run 5 first and read the traces.

## The two things to check on the first real run
1. **`BLOC_VOTE_NON_UNANIMOUS` should collapse.** Blocs now deliberate for up to
   three rounds, each seeing the others' prior proposals (canon §20.1). If this
   stays near the random-bot rate, the negotiation channel is not working and
   every game will take the drift path.
2. **`PLATE DETECTION` should be non-zero and concentrated in A06/A12.** Zero
   means the reasoning gate never fires and §8.3 is untested. Detection is parsed
   from the agent's own unprompted reasoning — never convert it to a probability.

## Agent protocol
council_prompt, speak, vote, bloc_propose, anchor_pass, murder_propose,
plate_detect, plate_swap, write_will, will_recipient_self, will_recipient_court,
succession_elect, succession_offer, succession_respond, transmission_questions,
transmission_answers, finale_continue.

The referee validates every return value. An agent cannot break a rule; it can
only be logged as having tried.
