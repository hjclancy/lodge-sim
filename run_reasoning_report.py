"""
Reasoning / interpretive report — reads real Sonnet-5 game traces, produces a
narrative case-study report.

Two-stage pipeline, deliberately kept separate:
  1. extract_facts() — plain Python, deterministic, zero API calls. Pulls
     verified structural facts (role layout, elimination order and cause)
     out of the persisted per-decision trace. This is the only source of
     "ground truth" fed to stage 2; it never guesses.
  2. narrate_game() — one Claude call per game. Given the verified facts as
     an anchor plus the full raw trace (every agent's actual reasoning text)
     as source material, writes the interpretive prose. The model is asked
     to treat stage 1's facts as authoritative and never contradict them,
     and to draw every reasoning claim from the trace, not invent one.

Why the extraction step exists at all: run_agents.py's trace_sink persists
only per-decision reasoning (pid, archetype, role, phase, tag, reasoning) —
not the referee's full event transcript (votes, exact eliminations,
mechanic resolutions). That transcript exists only in memory during a run
and is discarded once the console summary prints. Elimination phase and
cause here are therefore *inferred* from trace continuity — see the `note`
field in extract_facts()'s output, which is also surfaced in the rendered
report so no reader mistakes an inference for a verified fact.

    python3 run_reasoning_report.py --games 3 4 --winners FAITHFUL TRAITORS \\
        --final-alive 7 2 --traces-dir traces

--winners/--final-alive come from the run_agents.py console output line
("game N WINNER final K") for each game, since that line is the only
persisted record of the authoritative outcome.
"""

import argparse
import datetime
import html
import json
import os

from referee import PHASES
from report_common import html_shell, table, esc

MODEL = "claude-sonnet-5"

# Tags an eliminated player can still generate *after* death: the Court
# (all dead players) keeps deciding will-recipients and Transmission answers
# for the rest of the game, so a pid's *overall* last trace appearance is not
# a safe proxy for when they died — only these "still alive" tags are.
LIVING_TAGS = {"speak", "vote", "bloc", "murder", "anchor_pass", "dinner",
               "succession_elect", "succession_offer", "succession_respond",
               "transmission_q", "finale"}


def load_trace(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def extract_facts(trace, winner, final_alive):
    phase_idx = {p: i for i, p in enumerate(PHASES)}
    role_by_pid, archetype_by_pid = {}, {}
    last_alive = {}   # pid -> (phase_index, line_index) of their latest LIVING-tag entry
    will_phase = {}   # pid -> phase index of their own "will" entry, if any

    for i, e in enumerate(trace):
        pid = e["pid"]
        role_by_pid[pid] = e["role"]
        archetype_by_pid[pid] = e["archetype"]
        pi = phase_idx.get(e["phase"], -1)
        if e["tag"] in LIVING_TAGS:
            key = (pi, i)
            if pid not in last_alive or key > last_alive[pid]:
                last_alive[pid] = key
        elif e["tag"] == "will" and pid not in will_phase:
            will_phase[pid] = pi

    all_pids = sorted(archetype_by_pid.keys())
    # Rank by last-alive moment; the `final_alive` most-recently-active pids
    # are the survivors (their last living-tag entry is in the final phase
    # reached — RT_6_FINALE for a normal-length game).
    ranked = sorted(all_pids, key=lambda pid: last_alive.get(pid, (-1, -1)), reverse=True)
    survivors = set(ranked[:final_alive])
    def elim_sort_key(pid):
        if pid in will_phase:
            return (will_phase[pid], -1)
        return last_alive.get(pid, (-1, -1))

    eliminated = sorted((pid for pid in all_pids if pid not in survivors), key=elim_sort_key)

    timeline = []
    for pid in eliminated:
        murdered = pid in will_phase
        pi = will_phase[pid] if murdered else last_alive.get(pid, (-1, -1))[0]
        phase = PHASES[pi] if 0 <= pi < len(PHASES) else "?"
        cause = "MURDER" if murdered else "BANISHMENT"
        timeline.append({"order": len(timeline) + 1, "pid": pid,
                          "archetype": archetype_by_pid[pid], "role": role_by_pid[pid],
                          "approx_phase": phase, "cause": cause})

    role_layout = [{"pid": pid, "archetype": archetype_by_pid[pid], "role": role_by_pid[pid]}
                   for pid in sorted(archetype_by_pid)]
    survivor_list = [{"pid": pid, "archetype": archetype_by_pid[pid], "role": role_by_pid[pid]}
                      for pid in sorted(survivors)]

    return {
        "winner": winner,
        "final_alive": final_alive,
        "role_layout": role_layout,
        "elimination_timeline": timeline,
        "survivors": survivor_list,
        "note": (
            "elimination phase and cause (MURDER vs BANISHMENT) are inferred, not read from "
            "an explicit referee event log — the persisted trace holds only per-decision "
            "reasoning. A murdered player's phase comes from their own 'will' entry (only "
            "murder victims write one); a banished player's phase comes from their last "
            "entry tagged with a still-alive action (speak/vote/bloc/etc.), deliberately "
            "excluding 'will_court' and 'transmission_a' — the Court (all dead players) "
            "keeps generating those after death, so counting them would make every dead "
            "player look alive until the game ends. Exact vote tallies and who cast the "
            "deciding vote are not reconstructed this way; treat any such claim in the "
            "narrative as coming from an agent's own reasoning text, not independently "
            "verified."
        ),
    }


PROMPT_TEMPLATE = """You are writing an interpretive case-study narrative about one simulated \
game of a hidden-role social-deduction game called The Lodge, for the game's designer. This \
is a real game played by Claude-backed agents, one archetype persona per seat, through an \
automated referee.

You are given two things:

1. VERIFIED FACTS (JSON) — extracted programmatically from the game's decision log. Treat \
this as ground truth. Never contradict it, and never state a fact about role, elimination \
order, or the winner that isn't consistent with it. Read its "note" field carefully: \
elimination phase/cause are *inferred*, not from an explicit event log — do not present them \
with more certainty than that.

2. THE RAW TRACE — the full per-decision reasoning log, one JSON object per line. Each object \
has pid, archetype, phase, tag, role, and a "reasoning" field: that agent's actual private \
reasoning at that moment. This is your only source for what actually happened in the agents' \
heads. Quote or closely paraphrase specific reasoning where it illustrates something — do not \
invent reasoning, events, or votes that aren't in the material.

Write flowing prose for a human reader, not a stat dump — this report's whole value is \
interpretive, not statistical (a separate structural report already covers rates and \
distributions at volume). Cover, in this order, as plain paragraphs (blank line between \
paragraphs, no markdown headers, no bullet lists):

1. THE ROLE LAYOUT — which archetype drew which role, and anything notable about the mix.
2. THE ARC OF ELIMINATIONS — walk the eliminations in order: who the table (or the night) \
removed, whether they were actually a Traitor, and what the moment looked like from the \
reasoning.
3. NOTABLE REASONING MOMENTS — where an archetype played true to or diverged from its \
persona spec, where a decision visibly shaped the next beat, where an agent found or missed \
something (the plate, an Anchor-pass tell, a contradiction in someone's voting record).
4. THE NOMINATION ROUNDS — new in canon v4 and the largest change to how a Council runs. \
Each Council, every living player named one other player out loud, in a randomized order, \
seeing every nomination made before theirs; the three most-named formed a slate, the lowest \
was dropped by name, and the surviving two defended themselves before a ballot restricted to \
those two. Look at what that structure did: whether early nominations dragged later ones \
along, whether anyone used the order, whether a defense visibly changed the vote, and whether \
being dropped third was survivable. Say plainly if none of it mattered in this game.
5. HOW EACH MECHANIC ACTUALLY PLAYED — the Anchor (who held it, whether/when a Traitor \
learned its meaning, whether it blocked a murder), the rope (if it raised — bloc composition, \
whether blocs reached unanimity or fell to the longest-standing backstop), the plate at \
Saturday dinner (was it noticed, was there a swap), the Sunday Transmission, Succession (if \
triggered — offered to whom, accepted or declined), and the finale.
6. A short closing paragraph: what this specific game illustrates — about an archetype, a \
mechanic, or the ruleset.

VERIFIED FACTS:
{facts_json}

RAW TRACE ({n_entries} decisions):
{trace_text}
"""


def build_prompt(facts, trace):
    trace_text = "\n".join(json.dumps(e, ensure_ascii=False) for e in trace)
    return PROMPT_TEMPLATE.format(
        facts_json=json.dumps(facts, indent=2),
        n_entries=len(trace),
        trace_text=trace_text,
    )


def narrate_game(client, facts, trace):
    prompt = build_prompt(facts, trace)
    # Adaptive thinking is on by default for Sonnet 5; at effort=high on a
    # ~20K-token input, thinking alone can run past a few thousand tokens
    # before any text block starts. max_tokens must cover thinking + prose,
    # or the call truncates with stop_reason=max_tokens and zero text back
    # (this happened at max_tokens=4000 on the first attempt — thinking ate
    # the whole budget). Stream per the SDK's own guidance for large outputs.
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        resp = stream.get_final_message()
    text = "".join(b.text for b in resp.content if b.type == "text")
    if not text:
        raise RuntimeError(f"empty narrative text; stop_reason={resp.stop_reason}, "
                            f"content block types={[b.type for b in resp.content]}")
    cost = (resp.usage.input_tokens / 1e6) * 2.00 + (resp.usage.output_tokens / 1e6) * 10.00
    return text, cost, resp.usage.input_tokens, resp.usage.output_tokens


# ---------------------------------------------------------------- rendering

def prose_to_html(text):
    paras = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    return "\n".join(f"<p>{html.escape(p)}</p>" for p in paras)


def render_game_section(game_id, facts, narrative_html, batch_id=None):
    parts = [f"<h2>Game {game_id}</h2>"]
    meta = (f'Winner: <strong>{esc(facts["winner"])}</strong> &middot; '
            f'ended at Final {facts["final_alive"]}')
    if batch_id:
        # The narrative below is a reading of the trace; this is the trace.
        meta += (f' &middot; <a href="trace.html?batch={esc(batch_id)}&amp;game={game_id}">'
                 "every decision in this game &rarr;</a>")
    parts.append(f'<p class="note">{meta}</p>')

    parts.append("<h3>Role layout</h3>")
    parts.append(table(
        ["Seat", "Archetype", "Role"],
        [[r["pid"], r["archetype"], r["role"]] for r in facts["role_layout"]],
    ))

    parts.append("<h3>Elimination timeline</h3>")
    if facts["elimination_timeline"]:
        rows = [[e["order"], f'{e["pid"]} ({e["archetype"]})', e["role"], e["cause"],
                 e["approx_phase"]] for e in facts["elimination_timeline"]]
        parts.append(table(["#", "Player", "Actual role", "Cause", "~Phase"], rows,
                            note=facts["note"]))
    else:
        parts.append("<p>No eliminations recorded before the trace ends.</p>")

    parts.append("<h3>Survivors</h3>")
    parts.append(table(
        ["Seat", "Archetype", "Role"],
        [[r["pid"], r["archetype"], r["role"]] for r in facts["survivors"]],
    ))

    parts.append("<h3>Narrative</h3>")
    parts.append(narrative_html)
    return "\n".join(parts)


def render_report(games, out_path, model_meta, batch_id=None):
    """batch_id: the published trace batch these games belong to (the report's
    own basename). Passing it adds a per-game link to the trace viewer; omit
    it when the traces have not been published under reports/, so the report
    never links somewhere that isn't there."""
    disclaimer = (
        '<div class="disclaimer">'
        f'<strong>N = {len(games)}.</strong> These are case studies, not a sample. '
        'No "how often" or "how distributed" claim should be drawn from two games — that '
        'question belongs to the structural report (reports/structural_*.html), which runs '
        'thousands of heuristic-bot games for exactly that purpose. What follows is a close '
        'read of what happened and why, in two real Claude-agent games, nothing more.'
        '</div>'
    )
    body = [disclaimer]
    for g in games:
        body.append(render_game_section(g["game_id"], g["facts"], g["narrative_html"],
                                        batch_id=batch_id))

    header_meta = model_meta
    doc = html_shell(
        title=f"Lodge reasoning report (N={len(games)})",
        favicon_emoji="\U0001F9E9",
        header_title="The Lodge — Reasoning / Interpretive Report",
        header_meta=header_meta,
        body_html="\n".join(body),
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(doc)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, nargs="+", required=True,
                     help="game indices, e.g. 3 4 (matches traces/game_0003.jsonl etc.)")
    ap.add_argument("--winners", nargs="+", required=True, help="TRAITORS|FAITHFUL per game")
    ap.add_argument("--final-alive", type=int, nargs="+", required=True)
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    assert len(args.games) == len(args.winners) == len(args.final_alive)

    import anthropic
    client = anthropic.Anthropic()

    total_cost = 0.0
    games = []
    for gid, winner, final_alive in zip(args.games, args.winners, args.final_alive):
        path = os.path.join(args.traces_dir, f"game_{gid:04d}.jsonl")
        trace = load_trace(path)
        facts = extract_facts(trace, winner, final_alive)
        print(f"game {gid}: {len(trace)} decisions, winner={winner}, "
              f"final={final_alive} -> calling {MODEL} for narrative...")
        narrative, cost, in_tok, out_tok = narrate_game(client, facts, trace)
        total_cost += cost
        print(f"  done. in={in_tok} out={out_tok} cost=${cost:.2f}")
        games.append({"game_id": gid, "facts": facts,
                       "narrative_html": prose_to_html(narrative)})

    date = datetime.date.today().isoformat()
    out_path = args.out or f"reports/reasoning_{date}.html"
    model_meta = (f"N = {len(games)} games &middot; {MODEL}, effort=high &middot; "
                  f"summarization cost ${total_cost:.2f} &middot; generated {date}")
    # Link to the trace viewer only if these traces have actually been
    # published under reports/ — see scripts/publish_traces.py.
    stem = os.path.splitext(os.path.basename(out_path))[0]
    published = os.path.join(os.path.dirname(out_path) or ".",
                             "data", "traces", stem, "manifest.json")
    render_report(games, out_path, model_meta,
                  batch_id=stem if os.path.exists(published) else None)
    print(f"\nreport written to {out_path}")
    print(f"total summarization cost: ${total_cost:.2f}")


if __name__ == "__main__":
    main()
