"""Builds reports/trace.html — the per-game decision timeline.

A reasoning report is a close read of two or three games; this is the
material it was read from. Every entry is one agent's private reasoning at
one decision point, in the order the referee asked for it, filterable by
player, phase and tag.

Traces are fetched per game from reports/data/traces/<batch>/game_NNNN.json.
A single game is 40–60 KB of reasoning text and a batch holds several, so
nothing here is inlined; the batch/game index is, because it is small and
the page needs it before it can fetch anything.

The reasoning text is exactly what the agent produced, presented as text —
never rendered as markup. It is model output, and model output that lands in
a page is a place to be careful.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dashboard as dash

EXTRA_CSS = """
/* Reasoning is prose. Cap the column at a readable measure rather than
   letting entries run the full width of a 1180px page. */
.timeline { margin-top: var(--s8); max-width: 940px; }
.phase-head {
  position: sticky; top: 3rem; background: var(--bg); z-index: 3;
  border-bottom: 1px solid var(--rule); padding: var(--s8) 0 var(--s4) 0;
  margin: var(--s24) 0 var(--s8) 0;
  font-family: var(--mono); font-size: var(--t-micro); font-weight: 500;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted);
}
.entry {
  border: 1px solid var(--rule); border-left: 4px solid var(--rule-strong);
  background: var(--surface); border-radius: 0 var(--radius) var(--radius) 0;
  padding: var(--s12) var(--s16); margin-bottom: var(--s8);
}
/* Role is stated in words on every entry, so the edge colour is a second cue,
   not the carrier (§7.9). Vermilion marks the Traitor — a punctuation of a
   few pixels per card, inside a view that already carries Cobalt in the nav,
   which is what §2's dependency law requires. Faithful takes a plain rule. */
.entry.traitor { border-left-color: var(--vermilion); }
.entry.faithful { border-left-color: var(--rule-strong); }
.entry .head { display: flex; gap: var(--s8); align-items: baseline;
               flex-wrap: wrap; margin-bottom: var(--s4); }
.entry .pid { font-weight: 500; font-family: var(--mono); }
.entry .arch { color: var(--text-muted); font-size: var(--t-small); }
.entry .tag {
  font-family: var(--mono); font-size: var(--t-micro); font-weight: 500;
  letter-spacing: 0.04em; text-transform: uppercase;
  padding: 0 var(--s8); border-radius: var(--radius);
  border: 1px solid var(--rule); background: var(--surface-2); color: var(--text-muted);
}
.entry .role {
  display: inline-flex; align-items: baseline; gap: var(--s4);
  font-family: var(--mono); font-size: var(--t-micro); font-weight: 500;
  letter-spacing: 0.04em; color: var(--text);
}
.entry .role::before {
  content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: var(--n500);
}
.entry .role.TRAITOR::before { background: var(--vermilion); }
.entry .seq { margin-left: auto; color: var(--text-muted); font-family: var(--mono);
              font-size: var(--t-micro); font-variant-numeric: tabular-nums; }
.entry p { margin: 0; white-space: pre-wrap; font-size: var(--t-body); line-height: 1.5; }
/* Search hits are magnitude-free — a flat Cobalt tint, text left at Ink so the
   contrast floor holds. */
.entry mark { background: var(--mark); color: var(--text);
              padding: 0 0.1em; border-radius: 2px; }
.counts { color: var(--text-muted); font-size: var(--t-small); margin: var(--s8) 0;
          font-variant-numeric: tabular-nums; }
.legend { color: var(--text-muted); font-size: var(--t-caption); margin: var(--s4) 0 0 0; }
"""

SCRIPT = r"""
__FETCH__

const INDEX = __INDEX__;
let entries = [];

function esc(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
  });
}

// Reasoning text is model output. It is escaped first and only then does the
// search highlight wrap matches, so nothing in a trace can inject markup.
function withHighlight(text, needle) {
  const safe = esc(text);
  if (!needle) return safe;
  const pattern = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return safe.replace(new RegExp('(' + pattern + ')', 'gi'), '<mark>$1</mark>');
}

function currentBatch() {
  return INDEX.batches[parseInt(document.getElementById('batch').value, 10)];
}

function fillGames(batch) {
  const sel = document.getElementById('game');
  sel.innerHTML = batch.games.map(function (g, i) {
    return '<option value="' + i + '">Game ' + g.game_id
      + (g.winner ? ' — ' + g.winner + ' win' : '')
      + (g.decisions ? ' (' + g.decisions + ' decisions)' : '') + '</option>';
  }).join('');
}

function fillFilters() {
  function opts(values, label) {
    return ['<option value="">' + label + '</option>']
      .concat(values.map(function (v) { return '<option value="' + esc(v) + '">' + esc(v) + '</option>'; }))
      .join('');
  }
  const pids = Array.from(new Set(entries.map(function (e) { return e.pid; }))).sort();
  const phases = entries.map(function (e) { return e.phase; })
    .filter(function (v, i, a) { return a.indexOf(v) === i; });   // keep referee order
  const tags = Array.from(new Set(entries.map(function (e) { return e.tag; }))).sort();
  const players = pids.map(function (p) {
    const e = entries.find(function (x) { return x.pid === p; });
    return { value: p, label: p + ' (' + e.archetype + ', ' + e.role + ')' };
  });
  document.getElementById('f-player').innerHTML =
    ['<option value="">All players</option>'].concat(players.map(function (p) {
      return '<option value="' + esc(p.value) + '">' + esc(p.label) + '</option>';
    })).join('');
  document.getElementById('f-phase').innerHTML = opts(phases, 'All phases');
  document.getElementById('f-tag').innerHTML = opts(tags, 'All tags');
}

function render() {
  const player = document.getElementById('f-player').value;
  const phase = document.getElementById('f-phase').value;
  const tag = document.getElementById('f-tag').value;
  const q = document.getElementById('f-text').value.trim();
  const ql = q.toLowerCase();

  const shown = entries.filter(function (e) {
    if (player && e.pid !== player) return false;
    if (phase && e.phase !== phase) return false;
    if (tag && e.tag !== tag) return false;
    if (ql && e.reasoning.toLowerCase().indexOf(ql) === -1) return false;
    return true;
  });

  document.getElementById('counts').textContent =
    shown.length === entries.length
      ? entries.length + ' decisions'
      : shown.length + ' of ' + entries.length + ' decisions';

  const out = [];
  let lastPhase = null;
  shown.forEach(function (e) {
    if (e.phase !== lastPhase) {
      out.push('<div class="phase-head">' + esc(e.phase) + '</div>');
      lastPhase = e.phase;
    }
    out.push(
      '<article class="entry ' + (e.role === 'TRAITOR' ? 'traitor' : 'faithful') + '">'
      + '<div class="head">'
      + '<span class="pid">' + esc(e.pid) + '</span>'
      + '<span class="arch">' + esc(e.archetype) + '</span>'
      + '<span class="role ' + esc(e.role) + '">' + esc(e.role) + '</span>'
      + '<span class="tag">' + esc(e.tag) + '</span>'
      + '<span class="seq">#' + (e.i + 1) + '</span>'
      + '</div><p>' + withHighlight(e.reasoning, q) + '</p></article>'
    );
  });
  document.getElementById('timeline').innerHTML = out.length
    ? out.join('')
    : '<p class="empty">Nothing matches these filters.</p>';
}

async function loadGame() {
  const batch = currentBatch();
  const game = batch.games[parseInt(document.getElementById('game').value, 10)];
  document.getElementById('err').classList.add('hidden');
  document.getElementById('timeline').innerHTML = '';
  try {
    const raw = await loadJSON(game.file);
    entries = raw.map(function (e, i) { return Object.assign({ i: i }, e); });
    fillFilters();
    render();
    const url = new URL(location);
    url.searchParams.set('batch', batch.id);
    url.searchParams.set('game', game.game_id);
    history.replaceState(null, '', url);
  } catch (e) {
    entries = [];
    document.getElementById('counts').textContent = '';
    showError('err', e);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  if (!INDEX.batches.length) return;
  const params = new URLSearchParams(location.search);
  let bi = 0;
  const wantBatch = params.get('batch');
  if (wantBatch) {
    const i = INDEX.batches.findIndex(function (b) { return b.id === wantBatch; });
    if (i >= 0) bi = i;
  }
  const batchSel = document.getElementById('batch');
  batchSel.value = String(bi);
  fillGames(INDEX.batches[bi]);

  const wantGame = params.get('game');
  if (wantGame !== null) {
    const gi = INDEX.batches[bi].games.findIndex(function (g) {
      return String(g.game_id) === wantGame;
    });
    if (gi >= 0) document.getElementById('game').value = String(gi);
  }

  batchSel.addEventListener('change', function () {
    fillGames(currentBatch());
    loadGame();
  });
  document.getElementById('game').addEventListener('change', loadGame);
  ['f-player', 'f-phase', 'f-tag'].forEach(function (id) {
    document.getElementById(id).addEventListener('change', render);
  });
  document.getElementById('f-text').addEventListener('input', render);
  document.getElementById('f-clear').addEventListener('click', function () {
    ['f-player', 'f-phase', 'f-tag', 'f-text'].forEach(function (id) {
      document.getElementById(id).value = '';
    });
    render();
  });

  loadGame();
});
"""

INTRO = """
<div class="prose">
<p>One row per decision, in the order the referee asked for it. The text is the
agent's own private reasoning at that moment — the same material the reasoning
report was written from, unedited. Filter it by player, phase or tag, or search
the reasoning text.</p>
<p>What is <em>not</em> here: votes, tallies, and the referee's resolution of each
mechanic. The trace persists reasoning only; the event transcript exists in memory
during a run and is gone when the console summary prints. An agent saying it will
vote for someone is evidence it intended to, not proof it did.</p>
</div>
"""


def build(out_dir, index):
    """index: {"batches": [{id, label, report, games: [{game_id, winner, decisions, file}]}]}"""
    batches = index.get("batches", [])
    if not batches:
        body = ('<p class="empty">No traces have been published yet. The reasoning '
                'workflow copies each batch\'s traces into <code>reports/data/traces/</code> '
                'when it runs.</p>')
        script = ""
    else:
        options = "".join(f'<option value="{i}">{dash.esc(b["label"])}</option>'
                          for i, b in enumerate(batches))
        body = "\n".join([
            INTRO,
            '<div class="controls">'
            '<span class="label">Batch</span>'
            f'<select class="ctl" id="batch">{options}</select>'
            '<span class="label">Game</span>'
            '<select class="ctl" id="game"></select>'
            "</div>",
            '<div class="controls">'
            '<select class="ctl" id="f-player"></select>'
            '<select class="ctl" id="f-phase"></select>'
            '<select class="ctl" id="f-tag"></select>'
            '<input class="ctl" id="f-text" type="search" placeholder="search reasoning…" '
            'style="min-width:16rem">'
            '<button class="btn" id="f-clear">Clear filters</button>'
            "</div>",
            '<div class="banner hidden" id="err"></div>',
            '<p class="counts" id="counts"></p>',
            '<p class="legend">Every entry names its role in words; the marked left '
            'edge and the dot beside the role are the same fact repeated for scanning. '
            'Roles are shown because the trace records them — the players did not '
            'know them.</p>',
            '<div class="timeline" id="timeline"></div>',
        ])
        script = (SCRIPT
                  .replace("__FETCH__", dash.FETCH_HELPER)
                  .replace("__INDEX__", json.dumps(index)))

    n_games = sum(len(b["games"]) for b in batches)
    doc = dash.page(
        title="The Lodge — Trace viewer",
        header_title="The Lodge — Trace viewer",
        header_meta=(f"{n_games} game{'' if n_games == 1 else 's'} across "
                     f"{len(batches)} batch{'' if len(batches) == 1 else 'es'} "
                     "&middot; every decision, with the reasoning behind it"),
        body=body,
        active="trace.html",
        extra_css=EXTRA_CSS,
        extra_js=script,
    )
    path = os.path.join(out_dir, "trace.html")
    with open(path, "w") as f:
        f.write(doc)
    return path
