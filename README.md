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

### BEFORE ANY REAL RUN: replace rules/
`rules/public_rules.md` and `rules/traitor_brief.md` are what agents read. They
currently contain PLACEHOLDER text derived from the canon. Replace them with the
**verbatim player-facing documents** — the actual Rules Sheet and Traitor Brief
the twelve guests receive. Testing the canon against a restatement of the canon
finds nothing; the gap between intent and text is the whole point.

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
| `rules/` | what the agents read. REPLACE BEFORE USE. |
| `traces/` | per-game reasoning traces, one JSONL per game. |
| `traces_mock/` | default output for `--mock` runs — kept separate so plumbing tests never overwrite real trace data. |
| `reports/` | standalone HTML reports — `structural_<date>.html` (heuristic bots) and `reasoning_<date>.html` (Claude narrative reads of real games). |

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
