"""Builds reports/charts.html — per-batch charts, drawn client-side.

The batch picker is inlined at build time (it is a short list). The series
themselves are fetched from reports/data/<batch>.json on selection, so this
page does not grow as batches accumulate and a reader who wants one batch
downloads one batch.

Every chart here is a view of a table that already exists in the batch's own
report — nothing is computed in the browser beyond turning counts into
percentages. If a chart and a report table ever disagree, the report is
right: it comes from the same run() call, whereas this reads the exported
copy.
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
.paramtable { font-size: var(--t-caption); }
.paramtable td, .paramtable th { padding: var(--s4) var(--s8); }
.meta-line { color: var(--text-muted); font-size: var(--t-small); margin: var(--s4) 0 var(--s16) 0; }
.meta-line strong { color: var(--text); font-family: var(--mono); font-weight: 500; }
"""

CHARTS = [
    ("survival", "Archetype survival to end, by role",
     "Share of games in which an archetype was still alive at the end, split by the role "
     "it drew. The §5.2 bias applies: this speech model discards volume and interruption, "
     "so loud archetypes are under-modelled and quiet ones over-modelled."),
    ("elimination", "Elimination timing by phase",
     "Where in the weekend players leave, and how. Murder and banishment are stacked "
     "because they are the only two ways out; the referee records both directly, so "
     "unlike the reasoning report's timeline nothing here is inferred."),
    ("nomination", "Nomination accuracy by archetype (§17)",
     "Share of a Faithful player's nominations that named an actual Traitor. Base rate is "
     "25–33%: three Traitors among the rest of the table. An archetype below the base "
     "rate is evidence of a defective parameter mapping in heuristic_bots.py, not of a "
     "game property — canon §17 requires this to come back clean before the win split is "
     "treated as a balance problem. Archetypes under the base rate are marked ▼ on the "
     "axis as well as drawn in the strongest tint."),
    ("ladder", "Tie ladder step distribution (§5.4)",
     "Which step of the deterministic ladder resolved each tied ballot. RPS is gone; step "
     "3 always resolves because nomination order is a strict total ordering. "
     "SMALL_COUNT_TIE_FORCED — marked ▼ and drawn in the strongest tint — is the only "
     "random elimination left, and is reachable only below 5 alive, where there is no "
     "nomination record to read."),
    ("plate", "Plate detection by archetype (§8.3)",
     "Detections per game. At this tier detection is a gated roll on the archetype's "
     "`object` parameter, not a reasoning trace — a deliberately different mechanism "
     "from the Claude tier's reasoning-gated detection. Expect A06 and A12 to dominate."),
    ("floats", "Float event and mechanic rates",
     "Share of games in which each event fired at least once."),
]

SCRIPT = r"""
__BOOT__
__FETCH__

const BATCHES = __BATCHES__;
const charts = {};

// HOUSE STYLE §3: every chart on this page is Mode A — one family, Cobalt
// tints. Two-category charts take well-separated steps of the ramp rather
// than two hues, and each keeps its legend so the split is never read from
// tint alone. Reference lines are neutral, because an annotation is not data.
// PALETTE is ordered by emphasis for the active scheme, so these names hold in
// both: C_STRONG is whichever end carries hardest against the page. Pairs take
// steps 0 and 2 rather than adjacent ones — that keeps both series clear of the
// 3:1 mark floor against the page in either scheme, and 3:1 from each other.
const C_STRONG = PALETTE[0];   // exceptions, and the first series of a pair
const C_MAIN   = PALETTE[1];   // the only series, where a chart has one
const C_MID    = PALETTE[2];   // ordinary bars, and the second series of a pair
const MARK = '▼ ';        // prefixes an exception's axis label

function destroyAll() {
  Object.keys(charts).forEach(function (k) { charts[k].destroy(); delete charts[k]; });
}

function pct(v) { return v === null || v === undefined ? null : Math.round(v * 10) / 10; }

function drawSurvival(d) {
  const labels = d.survival.map(function (s) { return s.id; });
  charts.survival = new Chart(document.getElementById('c-survival'), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Faithful survival %', data: d.survival.map(function (s) { return pct(s.faithful_pct); }),
          backgroundColor: C_STRONG },
        { label: 'Traitor survival %', data: d.survival.map(function (s) { return pct(s.traitor_pct); }),
          backgroundColor: C_MID }
      ]
    },
    options: baseOptions({
      plugins: {
        legend: { labels: { color: themeInk(), boxWidth: 12 } },
        tooltip: { callbacks: { title: function (items) {
          const i = items[0].dataIndex;
          return d.archetypes[i].id + ' ' + d.archetypes[i].name;
        } } }
      },
      scales: {
        x: { ticks: { color: themeMuted() }, grid: { display: false } },
        y: { ticks: { color: themeMuted() }, grid: { color: gridColor() },
             beginAtZero: true, max: 100, title: { display: true, text: '% surviving',
             color: themeMuted() } }
      }
    })
  });
}

function drawElimination(d) {
  const rows = d.elimination_timing || [];
  charts.elimination = new Chart(document.getElementById('c-elimination'), {
    type: 'bar',
    data: {
      labels: rows.map(function (r) { return r.phase; }),
      datasets: [
        { label: 'Murdered', data: rows.map(function (r) { return r.murdered / d.games; }),
          backgroundColor: C_STRONG },
        { label: 'Banished', data: rows.map(function (r) { return r.banished / d.games; }),
          backgroundColor: C_MID }
      ]
    },
    options: baseOptions({
      scales: {
        x: { stacked: true, ticks: { color: themeMuted(), maxRotation: 60, minRotation: 45 },
             grid: { display: false } },
        y: { stacked: true, ticks: { color: themeMuted() }, grid: { color: gridColor() },
             beginAtZero: true,
             title: { display: true, text: 'eliminations per game', color: themeMuted() } }
      }
    })
  });
}

function drawNomination(d) {
  const rows = d.nomination_accuracy || [];
  // The 25–33% base-rate band is what makes this chart readable: a bar below
  // it is a defective parameter mapping, not a finding about the game. That
  // exception is marked on the axis label as well as by tint, so it survives
  // grayscale (§7.9).
  const under = function (r) { return r.pct !== null && r.pct < 25; };
  charts.nomination = new Chart(document.getElementById('c-nomination'), {
    type: 'bar',
    data: {
      labels: rows.map(function (r) { return (under(r) ? MARK : '') + r.id; }),
      datasets: [
        { label: 'Nomination accuracy %',
          data: rows.map(function (r) { return pct(r.pct); }),
          backgroundColor: rows.map(function (r) {
            return under(r) ? C_STRONG : C_MID;
          }), order: 2 },
        { label: 'Base rate (25%)', type: 'line',
          data: rows.map(function () { return 25; }),
          borderColor: themeMuted(), borderDash: [5, 4], borderWidth: 1,
          pointRadius: 0, fill: false, order: 1 },
        { label: 'Base rate (33%)', type: 'line',
          data: rows.map(function () { return 33; }),
          borderColor: themeMuted(), borderDash: [2, 3], borderWidth: 1,
          pointRadius: 0, fill: false, order: 1 }
      ]
    },
    options: baseOptions({
      plugins: {
        legend: { labels: { color: themeInk(), boxWidth: 12 } },
        tooltip: { callbacks: {
          title: function (items) {
            const i = items[0].dataIndex;
            return d.archetypes[i].id + ' ' + d.archetypes[i].name;
          },
          afterBody: function (items) {
            const r = rows[items[0].dataIndex];
            return r && r.n ? r.n.toLocaleString() + ' nominations' : '';
          }
        } }
      },
      scales: {
        x: { ticks: { color: themeMuted() }, grid: { display: false } },
        y: { ticks: { color: themeMuted() }, grid: { color: gridColor() },
             beginAtZero: true, suggestedMax: 60,
             title: { display: true, text: '% naming a Traitor', color: themeMuted() } }
      }
    })
  });
}

function drawLadder(d) {
  const rows = d.tie_ladder || [];
  charts.ladder = new Chart(document.getElementById('c-ladder'), {
    type: 'bar',
    data: {
      // The forced-random step is the one worth spotting, so it is marked on
      // the axis as well as drawn at the dark end of the ramp.
      labels: rows.map(function (r) {
        const name = r.tag.replace('TIE_LADDER_', '');
        return (r.tag === 'SMALL_COUNT_TIE_FORCED' ? MARK : '') + name;
      }),
      datasets: [{ label: 'Ties resolved',
                   data: rows.map(function (r) { return r.count; }),
                   backgroundColor: rows.map(function (r) {
                     return r.tag === 'SMALL_COUNT_TIE_FORCED' ? C_STRONG : C_MID;
                   }) }]
    },
    options: baseOptions({
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { afterBody: function (items) {
          const r = rows[items[0].dataIndex];
          return r && r.pct !== null ? r.pct.toFixed(1) + '% of resolved ties' : '';
        } } }
      },
      scales: {
        x: { ticks: { color: themeMuted() }, grid: { display: false } },
        y: { ticks: { color: themeMuted() }, grid: { color: gridColor() },
             beginAtZero: true }
      }
    })
  });
}

function drawPlate(d) {
  const rows = d.plate_detection || [];
  charts.plate = new Chart(document.getElementById('c-plate'), {
    type: 'bar',
    data: {
      labels: rows.map(function (r) { return r.id; }),
      datasets: [{ label: 'Detections per game',
                   data: rows.map(function (r) { return Math.round(r.per_game * 1000) / 1000; }),
                   backgroundColor: C_MAIN }]
    },
    options: baseOptions({
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { title: function (items) {
          const i = items[0].dataIndex;
          return d.archetypes[i].id + ' ' + d.archetypes[i].name;
        } } }
      },
      scales: {
        x: { ticks: { color: themeMuted() }, grid: { display: false } },
        y: { ticks: { color: themeMuted() }, grid: { color: gridColor() }, beginAtZero: true }
      }
    })
  });
}

function drawFloats(d) {
  const rows = d.float_events || [];
  // Nominal categories, so they are separated by position and direct labels
  // rather than by tint steps — a mono ramp here would imply a ranking the
  // data does not have (§3 caveat).
  charts.floats = new Chart(document.getElementById('c-floats'), {
    type: 'bar',
    data: {
      labels: rows.map(function (r) { return r.tag; }),
      datasets: [{ label: '% of games',
                   data: rows.map(function (r) { return pct(r.pct); }),
                   backgroundColor: C_MAIN }]
    },
    options: baseOptions({
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: themeMuted() }, grid: { color: gridColor() },
             beginAtZero: true, max: 100 },
        y: { ticks: { color: themeMuted(), font: { size: 11 } }, grid: { display: false } }
      }
    })
  });
}

function renderMeta(d, batch) {
  const p = d.params || {};
  const over = (p.overrides || []);
  const bits = [
    '<strong>' + d.games.toLocaleString() + '</strong> games',
    '<strong>' + d.model + '</strong>',
    'params <strong>' + (over.length ? over.length + ' override' + (over.length === 1 ? '' : 's')
                                     : 'defaults') + ' ' + (p.digest || '?') + '</strong>',
    '<a href="' + batch.report + '">open the full report</a>'
  ];
  let html = '<p class="meta-line">' + bits.join(' &middot; ') + '</p>';
  if (over.length) {
    html += '<p class="note">Overridden for this batch: <code>'
         + over.join('</code>, <code>') + '</code></p>';
  }
  document.getElementById('meta').innerHTML = html;
}

async function select(idx) {
  const batch = BATCHES[idx];
  if (!batch) return;
  document.getElementById('err').classList.add('hidden');
  try {
    const d = await loadJSON(batch.data);
    destroyAll();
    renderMeta(d, batch);
    document.getElementById('charts').style.display = '';
    drawSurvival(d);
    drawElimination(d);
    drawNomination(d);
    drawLadder(d);
    drawPlate(d);
    drawFloats(d);
  } catch (e) {
    destroyAll();
    document.getElementById('charts').style.display = 'none';
    document.getElementById('meta').innerHTML = '';
    showError('err', e);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  if (!BATCHES.length) return;
  if (!chartsAvailable('err')) return;
  const sel = document.getElementById('batch');
  sel.addEventListener('change', function () { select(parseInt(sel.value, 10)); });
  const wanted = new URLSearchParams(location.search).get('batch');
  let start = 0;
  if (wanted) {
    const i = BATCHES.findIndex(function (b) { return b.id === wanted; });
    if (i >= 0) start = i;
  }
  sel.value = String(start);
  select(start);
});
"""


def build(out_dir, batches):
    """batches: [{id, label, data, report, kind, date}] newest first."""
    if not batches:
        body = ('<p class="empty">No batch has exported chart data yet. Every run of '
                'either workflow writes one to <code>reports/data/</code>; reports '
                'produced before that existed have none, and are still readable as '
                'HTML from the <a href="index.html">reports list</a>.</p>')
        script = ""
    else:
        options = "".join(
            f'<option value="{i}">{dash.esc(b["label"])}</option>'
            for i, b in enumerate(batches))
        boxes = "".join(
            f'<div class="chartbox"><h3>{dash.esc(title)}</h3>'
            f'<p class="cap">{dash.esc(cap)}</p>'
            f'<div class="chartwrap"><canvas id="c-{key}"></canvas></div></div>'
            for key, title, cap in CHARTS)
        body = "\n".join([
            '<div class="controls">'
            '<span class="label">Batch</span>'
            f'<select class="ctl" id="batch">{options}</select>'
            "</div>",
            '<div class="banner hidden" id="err"></div>',
            '<div id="meta"></div>',
            f'<div id="charts" style="display:none">{boxes}</div>',
        ])
        script = (SCRIPT
                  .replace("__BOOT__", dash.CHART_BOOT)
                  .replace("__FETCH__", dash.FETCH_HELPER)
                  .replace("__BATCHES__", json.dumps(batches)))

    doc = dash.page(
        title="The Lodge — Charts",
        header_title="The Lodge — Charts",
        header_meta=(f"{len(batches)} batch{'' if len(batches) == 1 else 'es'} with "
                     "exported data &middot; drawn in the browser from reports/data/"),
        body=body,
        active="charts.html",
        extra_css=EXTRA_CSS,
        extra_js=script,
        chart_js=bool(batches),
    )
    path = os.path.join(out_dir, "charts.html")
    with open(path, "w") as f:
        f.write(doc)
    return path
