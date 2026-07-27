"""Builds the whole dashboard under reports/ — the directory GitHub Pages serves.

    python3 scripts/make_index.py

Four pages, each a single self-contained file:

  index.html   every report by date, the history table, and a line chart of
               metrics across batches
  charts.html  per-batch charts (scripts/page_charts.py)
  params.html  the archetype parameter sliders (scripts/page_params.py)
  trace.html   the per-game decision timeline (scripts/page_trace.py)

Everything is derived from what is on disk: the .html files in reports/, the
rows in reports/history.json, the per-batch exports in reports/data/, and the
trace manifests in reports/data/traces/. Nothing is inferred or backfilled —
a report produced before a given feature existed simply has no data for it
and says so.
"""

import datetime
import html
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dashboard as dash
import page_charts
import page_params
import page_trace
from report_history import COLUMNS, DATA_DIR, REPORTS_DIR, load, parse_report_name

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)

KIND_LABEL = {"structural": "Structural", "reasoning": "Reasoning", "other": "Other"}

# Which history columns can go on the cross-batch line chart, and which axis
# they belong on. Percentages share a 0–100 axis; everything else gets the
# right-hand one, because plotting "2.09 illegal votes per game" against
# "88% traitor wins" on one scale makes the first invisible.
LINE_METRICS = [
    ("traitor_win_pct", "Traitor win %", "pct"),
    ("final_2_pct", "Final 2 %", "pct"),
    ("rope_pct", "Rope raised %", "pct"),
    ("anchor_break_pct", "Anchor break %", "pct"),
    ("zero_vote_council_pct", "Zero-vote council %", "pct"),
    ("succession_accept_pct", "Succession accepted %", "pct"),
    ("bloc_non_unanimous_per_game", "Bloc non-unanimous /game", "count"),
    ("plate_detect_per_game", "Plate detect /game", "count"),
    ("invariant_violations", "Invariant violations", "count"),
    ("cost_usd", "Cost (USD)", "count"),
]
DEFAULT_LINE_METRICS = ["traitor_win_pct", "final_2_pct", "bloc_non_unanimous_per_game"]

EXTRA_CSS = """
ul.reports { list-style: none; padding: 0; margin: 0.4rem 0 1.8rem 0; }
ul.reports li {
  border: 1px solid var(--line); background: var(--panel); border-radius: 6px;
  padding: 0.7rem 0.95rem; margin-bottom: 0.5rem;
  display: flex; gap: 0.7rem; align-items: baseline; flex-wrap: wrap;
}
ul.reports a { color: var(--accent); font-weight: 600; text-decoration: none; }
ul.reports a:hover { text-decoration: underline; }
ul.reports .sub { color: var(--ink-soft); font-size: 0.86rem; }
ul.reports .links { margin-left: auto; display: flex; gap: 0.6rem; font-size: 0.84rem; }
h3.datehead { color: var(--ink-soft); font-size: 0.92rem; margin: 1.4rem 0 0.3rem 0; }
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable::after { content: " \\2195"; opacity: 0.35; font-size: 0.8em; }
th.sortable[data-dir="asc"]::after { content: " \\2191"; opacity: 1; }
th.sortable[data-dir="desc"]::after { content: " \\2193"; opacity: 1; }
td.nowrap { white-space: nowrap; }
.metricpick { display: flex; flex-wrap: wrap; gap: 0.3rem 0.9rem; margin: 0.3rem 0 0.9rem 0; }
.metricpick label { font-size: 0.85rem; color: var(--ink-soft); display: flex;
                    gap: 0.3rem; align-items: center; cursor: pointer; }
"""

SCRIPT = r"""
__BOOT__

(function () {
  var buttons = document.querySelectorAll('button.filter');
  function apply(kind) {
    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.kind === kind));
    });
    document.querySelectorAll('[data-kind]').forEach(function (el) {
      if (el.tagName === 'BUTTON') return;
      el.style.display = (kind === 'all' || el.dataset.kind === kind) ? '' : 'none';
    });
    document.querySelectorAll('h3.datehead').forEach(function (h) {
      var list = h.nextElementSibling, any = false;
      if (!list) return;
      list.querySelectorAll('li').forEach(function (li) { if (li.style.display !== 'none') any = true; });
      h.style.display = any ? '' : 'none';
      list.style.display = any ? '' : 'none';
    });
  }
  buttons.forEach(function (b) { b.addEventListener('click', function () { apply(b.dataset.kind); }); });

  var table = document.getElementById('history-table');
  if (table) {
    table.querySelectorAll('th.sortable').forEach(function (th, idx) {
      th.addEventListener('click', function () {
        var dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
        table.querySelectorAll('th.sortable').forEach(function (o) { delete o.dataset.dir; });
        th.dataset.dir = dir;
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = a.cells[idx].dataset.sort, y = b.cells[idx].dataset.sort;
          var nx = parseFloat(x), ny = parseFloat(y);
          var both = !isNaN(nx) && !isNaN(ny);
          var cmp = both ? (nx - ny) : String(x).localeCompare(String(y));
          return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  }
})();

var RUNS = __RUNS__;
var METRICS = __METRICS__;
var trend = null;

function seriesFor(keys) {
  return keys.map(function (key, i) {
    var m = METRICS.find(function (x) { return x.key === key; });
    return {
      label: m.label,
      data: RUNS.map(function (r) {
        var v = r[key];
        return (v === null || v === undefined) ? null : v;
      }),
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: PALETTE[i % PALETTE.length],
      yAxisID: m.axis === 'pct' ? 'y' : 'y1',
      spanGaps: true,
      tension: 0.25,
      pointRadius: 4,
      pointHoverRadius: 6
    };
  });
}

function drawTrend() {
  var keys = Array.prototype.slice
    .call(document.querySelectorAll('.metricpick input:checked'))
    .map(function (el) { return el.value; });
  if (trend) { trend.destroy(); trend = null; }
  if (!keys.length) return;
  var usesPct = keys.some(function (k) {
    return METRICS.find(function (m) { return m.key === k; }).axis === 'pct';
  });
  var usesCount = keys.some(function (k) {
    return METRICS.find(function (m) { return m.key === k; }).axis !== 'pct';
  });
  trend = new Chart(document.getElementById('c-trend'), {
    type: 'line',
    data: {
      labels: RUNS.map(function (r) { return r.label; }),
      datasets: seriesFor(keys)
    },
    options: baseOptions({
      plugins: {
        legend: { labels: { color: themeInk(), boxWidth: 12, usePointStyle: true } },
        tooltip: {
          callbacks: {
            afterTitle: function (items) {
              var r = RUNS[items[0].dataIndex];
              return r.kind + ' · ' + r.games.toLocaleString() + ' games · params '
                   + (r.params_summary || 'not recorded');
            }
          }
        }
      },
      scales: {
        x: { ticks: { color: themeInk(), maxRotation: 45, minRotation: 0 },
             grid: { display: false } },
        y: { display: usesPct, position: 'left', beginAtZero: true, max: 100,
             ticks: { color: themeInk() }, grid: { color: gridColor() },
             title: { display: true, text: 'percent', color: themeInk() } },
        y1: { display: usesCount, position: 'right', beginAtZero: true,
              ticks: { color: themeInk() }, grid: { drawOnChartArea: false },
              title: { display: true, text: 'count', color: themeInk() } }
      }
    })
  });
}

document.addEventListener('DOMContentLoaded', function () {
  if (!RUNS.length) return;
  if (!chartsAvailable('trend-err')) return;
  document.querySelectorAll('.metricpick input').forEach(function (el) {
    el.addEventListener('change', drawTrend);
  });
  drawTrend();
});
"""


def esc(x):
    return html.escape(str(x))


def fmt(value, kind):
    if value is None or value == "":
        return "&mdash;", ""
    if kind == "int":
        return f"{int(value):,}", str(value)
    if kind == "pct":
        return f"{float(value):.1f}%", str(value)
    if kind == "num2":
        return f"{float(value):.2f}", str(value)
    if kind == "usd":
        v = float(value)
        return ("$0" if v == 0 else f"${v:,.2f}"), str(v)
    if kind == "secs":
        v = float(value)
        text = f"{v:.1f}s" if v < 60 else f"{int(v // 60)}m {int(v % 60):02d}s"
        return text, str(v)
    return esc(value), str(value)


def report_title(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4000)
    except OSError:
        return None
    m = TITLE_RE.search(head)
    return " ".join(m.group(1).split()) if m else None


def scan_reports(reports_dir=REPORTS_DIR):
    """Every .html in reports/ except the dashboard's own pages, newest first."""
    own = {p for p, _ in dash.NAV}
    out = []
    for name in sorted(os.listdir(reports_dir)):
        if not name.endswith(".html") or name in own:
            continue
        path = os.path.join(reports_dir, name)
        parsed = parse_report_name(name)
        if parsed:
            kind, date, seq = parsed
        else:
            kind, seq = "other", 1
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
            date = mtime.date().isoformat()
        out.append({
            "file": name, "kind": kind, "date": date, "seq": seq,
            "title": report_title(path) or name,
            "size_kb": max(1, round(os.path.getsize(path) / 1024)),
        })
    out.sort(key=lambda r: (r["date"], r["seq"], r["file"]), reverse=True)
    return out


def scan_batches(reports, by_run, data_dir=DATA_DIR):
    """Reports that exported chart data, newest first."""
    out = []
    for r in reports:
        stem = os.path.splitext(r["file"])[0]
        path = os.path.join(data_dir, stem + ".json")
        if not os.path.exists(path):
            continue
        run = by_run.get(r["file"]) or {}
        games = run.get("games")
        label = f"{r['date']} · {KIND_LABEL.get(r['kind'], r['kind'])}"
        if games:
            label += f" · {games:,} games"
        if run.get("params_summary"):
            label += f" · {run['params_summary']}"
        out.append({"id": stem, "label": label, "kind": r["kind"], "date": r["date"],
                    "data": f"data/{stem}.json", "report": r["file"]})
    return out


def scan_traces(data_dir=DATA_DIR):
    """reports/data/traces/<batch>/manifest.json, newest batch first."""
    root = os.path.join(data_dir, "traces")
    if not os.path.isdir(root):
        return {"batches": []}
    batches = []
    for name in sorted(os.listdir(root), reverse=True):
        manifest = os.path.join(root, name, "manifest.json")
        if not os.path.exists(manifest):
            continue
        with open(manifest) as f:
            batches.append(json.load(f))
    return {"batches": batches}


def render_history_table(runs, by_file):
    if not runs:
        return ('<p class="empty">No batch rows yet. reports/history.json gets its first row '
                'the next time either workflow runs; reports produced before the workflows '
                'existed are listed below but have no metrics recorded.</p>')
    head = ['<div class="scroll"><table id="history-table"><thead><tr>']
    head.append('<th class="sortable">Report</th>')
    for _key, label, kfmt in COLUMNS:
        cls = "sortable" + ("" if kfmt == "text" else " num")
        head.append(f'<th class="{cls}">{esc(label)}</th>')
    head.append("</tr></thead><tbody>")

    body = []
    for run in sorted(runs, key=lambda r: r.get("run_id", ""), reverse=True):
        kind = run.get("kind", "other")
        body.append(f'<tr data-kind="{esc(kind)}">')
        rpt = run.get("report")
        if rpt and rpt in by_file:
            link = f'<a href="{esc(rpt)}">{esc(rpt)}</a>'
        elif rpt:
            link = f'{esc(rpt)} <span class="sub">(file missing)</span>'
        else:
            link = "&mdash;"
        run_url = run.get("run_url")
        if run_url:
            link += f' <a class="sub" href="{esc(run_url)}" title="workflow run">&#8599;</a>'
        body.append(f'<td data-sort="{esc(run.get("run_id", ""))}">{link}</td>')
        for key, _label, kfmt in COLUMNS:
            value = run.get(key)
            if key == "kind":
                cell = f'<span class="kind {esc(kind)}">{esc(KIND_LABEL.get(kind, kind))}</span>'
                body.append(f'<td data-sort="{esc(kind)}">{cell}</td>')
                continue
            if key == "params_summary" and value:
                overrides = run.get("params_overrides") or []
                title = "; ".join(overrides) if overrides else "committed archetypes.json"
                body.append(f'<td class="nowrap" data-sort="{esc(value)}" '
                            f'title="{esc(title)}">{esc(value)}</td>')
                continue
            text, sortv = fmt(value, kfmt)
            cls = ' class="num"' if kfmt != "text" else ""
            body.append(f'<td{cls} data-sort="{esc(sortv)}">{text}</td>')
        body.append("</tr>")

    notes = [r for r in runs if r.get("notes")]
    tail = ["</tbody></table></div>",
            '<p class="note">Click a column to sort; the table scrolls sideways on narrow '
            'screens. Hover a params cell for the exact overrides. Anchor breaks, zero-vote '
            'councils, succession rates, wall-clock time and the full ending distribution '
            'are recorded on every row but have no column &mdash; they are in '
            '<a href="history.json">history.json</a>.</p>']
    if notes:
        tail.append("<p class=\"note\">Run notes: " + " &middot; ".join(
            f'{esc(r.get("report") or r.get("run_id"))}: {esc(r["notes"])}' for r in notes[-6:]
        ) + "</p>")
    return "\n".join(head + body + tail)


def render_trend(runs):
    """-> (html, metric descriptors). Empty pair when there is nothing to plot."""
    if not runs:
        return "", []
    metrics = [{"key": k, "label": lbl, "axis": axis} for k, lbl, axis in LINE_METRICS]
    picks = "".join(
        f'<label><input type="checkbox" value="{esc(k)}"'
        f'{" checked" if k in DEFAULT_LINE_METRICS else ""}> {esc(lbl)}</label>'
        for k, lbl, _axis in LINE_METRICS)
    return "\n".join([
        "<h2>Metrics across batches</h2>",
        '<div class="banner hidden" id="trend-err"></div>',
        f'<div class="metricpick">{picks}</div>',
        '<div class="chartbox"><div class="chartwrap"><canvas id="c-trend"></canvas></div>'
        '<p class="cap" style="margin:0.7rem 0 0 0">Every batch in '
        '<a href="history.json">history.json</a>, oldest to newest. Batches are evenly '
        'spaced by run order, not by date or by sample size &mdash; a 2-game Sonnet batch '
        'sits the same distance from its neighbours as a 200,000-game heuristic one, and '
        'carries nothing like the same weight. Hover a point for its kind, game count and '
        'parameter set.</p></div>',
    ]), metrics


def render_report_list(reports, by_run, batch_ids, trace_batches):
    if not reports:
        return '<p class="empty">No reports yet.</p>'
    out = []
    current_date = None
    for r in reports:
        if r["date"] != current_date:
            if current_date is not None:
                out.append("</ul>")
            current_date = r["date"]
            out.append(f'<h3 class="datehead">{esc(current_date)}</h3><ul class="reports">')
        stem = os.path.splitext(r["file"])[0]
        run = by_run.get(r["file"]) or {}
        sub = []
        if run.get("games") is not None:
            sub.append(f'{run["games"]:,} games')
        if run.get("model"):
            sub.append(esc(run["model"]))
        if run.get("params_summary"):
            sub.append(esc(run["params_summary"]))
        if run.get("cost_usd"):
            sub.append(f'${run["cost_usd"]:.2f}')
        sub.append(f'{r["size_kb"]} KB')

        links = []
        if stem in batch_ids:
            links.append(f'<a href="charts.html?batch={esc(stem)}">charts</a>')
        if stem in trace_batches:
            links.append(f'<a href="trace.html?batch={esc(stem)}">traces</a>')
        links_html = f'<span class="links">{"".join(links)}</span>' if links else ""

        out.append(
            f'<li data-kind="{esc(r["kind"])}">'
            f'<span class="kind {esc(r["kind"])}">{esc(KIND_LABEL.get(r["kind"], r["kind"]))}</span>'
            f'<a href="{esc(r["file"])}">{esc(r["title"])}</a>'
            f'<span class="sub">{esc(r["file"])} &middot; {" &middot; ".join(sub)}</span>'
            f"{links_html}</li>"
        )
    out.append("</ul>")
    return "\n".join(out)


def build(reports_dir=REPORTS_DIR):
    reports = scan_reports(reports_dir)
    history = load()
    runs = history.get("runs", [])
    by_file = {r["file"] for r in reports}
    by_run = {}
    for run in runs:                       # last row wins if a name repeats
        if run.get("report"):
            by_run[run["report"]] = run

    batches = scan_batches(reports, by_run)
    trace_index = scan_traces()
    batch_ids = {b["id"] for b in batches}
    trace_batch_ids = {b["id"] for b in trace_index["batches"]}

    n_struct = sum(1 for r in reports if r["kind"] == "structural")
    n_reason = sum(1 for r in reports if r["kind"] == "reasoning")
    latest = reports[0]["date"] if reports else "never"
    total_cost = sum(r.get("cost_usd") or 0.0 for r in runs)

    if runs:
        tail = (f'{len(runs)} batch{"" if len(runs) == 1 else "es"} logged in '
                f'<a href="history.json">history.json</a>, '
                f'${total_cost:,.2f} of API spend recorded.')
    else:
        tail = 'No batches logged in <a href="history.json">history.json</a> yet.'
    summary = (
        f'<div class="summary">'
        f'{len(reports)} report{"" if len(reports) == 1 else "s"} '
        f'({n_struct} structural, {n_reason} reasoning), latest {esc(latest)}. '
        f'{tail}</div>'
    )

    caveat = (
        '<div class="disclaimer">'
        '<strong>The two kinds of row are not the same measurement.</strong> '
        'Structural rows are thousands of heuristic-bot games — deterministic rules built '
        'from the archetypes\' declared parameters, answering "how often" at volume. '
        'Reasoning rows are a handful of real Claude-agent games, kept small because they '
        'cost real money, and they exist to answer "why" in a specific game. Reading a rate '
        'off a two-game reasoning row, or treating a gap between the two kinds as a finding, '
        'is a mistake the reports themselves warn about at more length. The columns line up '
        'so the same mechanic can be located in both, not so the numbers can be subtracted.'
        '</div>'
    )

    controls = (
        '<div class="controls"><span class="label">Show</span>'
        '<button class="btn filter" data-kind="all" aria-pressed="true">All</button>'
        '<button class="btn filter" data-kind="structural" aria-pressed="false">Structural</button>'
        '<button class="btn filter" data-kind="reasoning" aria-pressed="false">Reasoning</button>'
        "</div>"
    )

    trend_html, metrics = render_trend(runs)

    body = "\n".join([
        summary,
        caveat,
        controls,
        "<h2>Batch history</h2>",
        render_history_table(runs, by_file),
        trend_html,
        "<h2>All reports</h2>",
        render_report_list(reports, by_run, batch_ids, trace_batch_ids),
    ])

    # Only what the chart reads, in run order — the full rows are one click
    # away in history.json and don't need to ship twice.
    line_keys = [k for k, _l, _a in LINE_METRICS]
    chart_runs = []
    for run in sorted(runs, key=lambda r: r.get("run_id", "")):
        row = {"label": f"{run.get('date', '?')} {KIND_LABEL.get(run.get('kind'), '?')}",
               "kind": run.get("kind", "?"), "games": run.get("games") or 0,
               "params_summary": run.get("params_summary")}
        for k in line_keys:
            row[k] = run.get(k)
        chart_runs.append(row)

    script = (SCRIPT
              .replace("__BOOT__", dash.CHART_BOOT)
              .replace("__RUNS__", json.dumps(chart_runs))
              .replace("__METRICS__", json.dumps(metrics)))

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = dash.page(
        title="The Lodge — Reports",
        header_title="The Lodge — Reports",
        header_meta=f"Every batch the simulation has produced &middot; generated {generated}",
        body=body,
        active="index.html",
        extra_css=EXTRA_CSS,
        extra_js=script,
        chart_js=bool(runs),
        footer=("Generated by scripts/make_index.py. Reports are immutable once written; "
                "re-running a workflow adds a new one rather than replacing it."),
    )
    out_path = os.path.join(reports_dir, "index.html")
    with open(out_path, "w") as f:
        f.write(doc)

    page_charts.build(reports_dir, batches)
    page_params.build(reports_dir)
    page_trace.build(reports_dir, trace_index)

    return {
        "index": out_path, "reports": len(reports), "runs": len(runs),
        "batches": len(batches),
        "trace_games": sum(len(b["games"]) for b in trace_index["batches"]),
    }


def main():
    r = build()
    print(f"dashboard written to {os.path.relpath(REPORTS_DIR, _REPO)}/ — "
          f"{r['reports']} report(s), {r['runs']} history row(s), "
          f"{r['batches']} batch(es) with charts, {r['trace_games']} trace(s)")


if __name__ == "__main__":
    main()
