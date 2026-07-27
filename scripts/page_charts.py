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
.paramtable { font-size: 0.82rem; }
.paramtable td, .paramtable th { padding: 0.3rem 0.5rem; }
.meta-line { color: var(--ink-soft); font-size: 0.9rem; margin: 0.2rem 0 1rem 0; }
.meta-line strong { color: var(--ink); }
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
          backgroundColor: PALETTE[1] },
        { label: 'Traitor survival %', data: d.survival.map(function (s) { return pct(s.traitor_pct); }),
          backgroundColor: PALETTE[3] }
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
        x: { ticks: { color: themeInk() }, grid: { display: false } },
        y: { ticks: { color: themeInk() }, grid: { color: gridColor() },
             beginAtZero: true, max: 100, title: { display: true, text: '% surviving',
             color: themeInk() } }
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
          backgroundColor: PALETTE[3] },
        { label: 'Banished', data: rows.map(function (r) { return r.banished / d.games; }),
          backgroundColor: PALETTE[2] }
      ]
    },
    options: baseOptions({
      scales: {
        x: { stacked: true, ticks: { color: themeInk(), maxRotation: 60, minRotation: 45 },
             grid: { display: false } },
        y: { stacked: true, ticks: { color: themeInk() }, grid: { color: gridColor() },
             beginAtZero: true,
             title: { display: true, text: 'eliminations per game', color: themeInk() } }
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
                   backgroundColor: PALETTE[5] }]
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
        x: { ticks: { color: themeInk() }, grid: { display: false } },
        y: { ticks: { color: themeInk() }, grid: { color: gridColor() }, beginAtZero: true }
      }
    })
  });
}

function drawFloats(d) {
  const rows = d.float_events || [];
  charts.floats = new Chart(document.getElementById('c-floats'), {
    type: 'bar',
    data: {
      labels: rows.map(function (r) { return r.tag; }),
      datasets: [{ label: '% of games',
                   data: rows.map(function (r) { return pct(r.pct); }),
                   backgroundColor: PALETTE.slice(0, rows.length) }]
    },
    options: baseOptions({
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: themeInk() }, grid: { color: gridColor() },
             beginAtZero: true, max: 100 },
        y: { ticks: { color: themeInk(), font: { size: 11 } }, grid: { display: false } }
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
