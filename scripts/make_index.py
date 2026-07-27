"""Generates reports/index.html — the landing page GitHub Pages serves.

Two things live on it:

  1. Every report file in reports/, grouped by date, newest first. This is a
     directory listing of what is actually on disk, so a report produced
     before the CI wrappers existed still appears — it just has no metrics
     next to it.
  2. reports/history.json rendered as one row per batch, so metrics can be
     compared across batches and across tiers.

Self-contained by the same rule as the reports themselves: one file, no
external assets, no build step. The inline JS only adds sorting and
filtering — with scripting off, the page still lists and tabulates
everything.

    python3 scripts/make_index.py
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

from report_common import CSS
from report_history import COLUMNS, REPORTS_DIR, load, parse_report_name

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)

KIND_LABEL = {"structural": "Structural", "reasoning": "Reasoning", "other": "Other"}

EXTRA_CSS = """
/* The report shell is sized for prose; this page is mostly table. Widen the
   column and re-narrow the prose blocks inside it. */
.wrap { max-width: 1180px; }
.summary, .disclaimer, footer.page { max-width: 80ch; }
.controls { margin: 1.2rem 0 0.6rem 0; display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
.controls .label { font-size: 0.85rem; color: var(--ink-soft); margin-right: 0.2rem; }
button.filter {
  font: inherit; font-size: 0.85rem; cursor: pointer;
  padding: 0.25rem 0.8rem; border-radius: 999px;
  border: 1px solid var(--line); background: var(--panel); color: var(--ink-soft);
}
button.filter[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fbf3e6; }
a { color: var(--accent); }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 1rem; }
.scroll table { min-width: 1020px; margin: 0; font-size: 0.88rem; }
.scroll th, .scroll td { padding: 0.42rem 0.6rem; }
.scroll + p.note { margin-top: 0.3rem; }
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable::after { content: " \\2195"; opacity: 0.35; font-size: 0.8em; }
th.sortable[data-dir="asc"]::after { content: " \\2191"; opacity: 1; }
th.sortable[data-dir="desc"]::after { content: " \\2193"; opacity: 1; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.kind { display: inline-block; padding: 0.05rem 0.5rem; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; border: 1px solid var(--line); }
.kind.structural { background: #e6edf5; color: #2f4a6b; }
.kind.reasoning  { background: #f0e8f5; color: #573b6b; }
.kind.other      { background: #ece9e2; color: var(--ink-soft); }
ul.reports { list-style: none; padding: 0; margin: 0.4rem 0 1.8rem 0; }
ul.reports li {
  border: 1px solid var(--line); background: var(--panel); border-radius: 6px;
  padding: 0.7rem 0.95rem; margin-bottom: 0.5rem;
  display: flex; gap: 0.7rem; align-items: baseline; flex-wrap: wrap;
}
ul.reports a { color: var(--accent); font-weight: 600; text-decoration: none; }
ul.reports a:hover { text-decoration: underline; }
ul.reports .sub { color: var(--ink-soft); font-size: 0.86rem; }
h3.datehead { color: var(--ink-soft); font-size: 0.92rem; margin: 1.4rem 0 0.3rem 0;
              text-transform: none; letter-spacing: 0.02em; }
.empty { color: var(--ink-soft); font-style: italic; }
@media (prefers-color-scheme: dark) {
  .kind.structural { background: #24313f; color: #a8c6e6; }
  .kind.reasoning  { background: #332a3d; color: #d0b3e6; }
  .kind.other      { background: #322d25; color: var(--ink-soft); }
}
"""

SCRIPT = """
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
  if (!table) return;
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
})();
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
    """Every .html in reports/ except the index itself, newest date first."""
    out = []
    for name in sorted(os.listdir(reports_dir)):
        if not name.endswith(".html") or name == "index.html":
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
                text, sortv = f'<span class="kind {esc(kind)}">{esc(KIND_LABEL.get(kind, kind))}</span>', kind
                body.append(f'<td data-sort="{esc(sortv)}">{text}</td>')
                continue
            text, sortv = fmt(value, kfmt)
            cls = ' class="num"' if kfmt != "text" else ""
            body.append(f'<td{cls} data-sort="{esc(sortv)}">{text}</td>')
        body.append("</tr>")

    notes = [r for r in runs if r.get("notes")]
    tail = ["</tbody></table></div>",
            '<p class="note">Click a column to sort; the table scrolls sideways on narrow '
            'screens. Anchor breaks, zero-vote councils, succession rates, wall-clock time '
            'and the full ending distribution are recorded on every row but have no column '
            '&mdash; '
            'they are in <a href="history.json">history.json</a>.</p>']
    if notes:
        tail.append("<p class=\"note\">Run notes: " + " &middot; ".join(
            f'{esc(r.get("report") or r.get("run_id"))}: {esc(r["notes"])}' for r in notes[-6:]
        ) + "</p>")
    return "\n".join(head + body + tail)


def render_report_list(reports, by_run):
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
        run = by_run.get(r["file"]) or {}
        sub = []
        if run.get("games") is not None:
            sub.append(f'{run["games"]:,} games')
        if run.get("model"):
            sub.append(esc(run["model"]))
        if run.get("cost_usd"):
            sub.append(f'${run["cost_usd"]:.2f}')
        sub.append(f'{r["size_kb"]} KB')
        out.append(
            f'<li data-kind="{esc(r["kind"])}">'
            f'<span class="kind {esc(r["kind"])}">{esc(KIND_LABEL.get(r["kind"], r["kind"]))}</span>'
            f'<a href="{esc(r["file"])}">{esc(r["title"])}</a>'
            f'<span class="sub">{esc(r["file"])} &middot; {" &middot; ".join(sub)}</span>'
            f"</li>"
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
        '<button class="filter" data-kind="all" aria-pressed="true">All</button>'
        '<button class="filter" data-kind="structural" aria-pressed="false">Structural</button>'
        '<button class="filter" data-kind="reasoning" aria-pressed="false">Reasoning</button>'
        "</div>"
    )

    body = "\n".join([
        summary,
        caveat,
        controls,
        "<h2>Batch history</h2>",
        render_history_table(runs, by_file),
        "<h2>All reports</h2>",
        render_report_list(reports, by_run),
    ])

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Lodge — Reports</title>
<style>{CSS}{EXTRA_CSS}</style>
</head>
<body>
<header class="page"><div class="wrap">
  <h1>The Lodge — Reports</h1>
  <div class="meta">Every batch the simulation has produced &middot; generated {generated}</div>
</div></header>
<div class="wrap">
{body}
<footer class="page">Generated by scripts/make_index.py. Self-contained — no external assets.
Reports are immutable once written; re-running a workflow adds a new one rather than replacing it.</footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>"""

    out_path = os.path.join(reports_dir, "index.html")
    with open(out_path, "w") as f:
        f.write(doc)
    return out_path, len(reports), len(runs)


def main():
    path, n_reports, n_runs = build()
    print(f"index written to {os.path.relpath(path, _REPO)} "
          f"({n_reports} report(s), {n_runs} history row(s))")


if __name__ == "__main__":
    main()
