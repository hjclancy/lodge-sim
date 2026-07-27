"""Shared shell for the dashboard pages under reports/.

Four pages — index, charts, params, trace — share a header, a nav bar, and
the report palette from report_common. Each is a single .html file with its
CSS and JS inline: no build step, no bundler, nothing to install.

Two things are fetched at runtime rather than inlined:

  * Chart.js, from a CDN. Every page that draws a chart checks that it
    actually loaded and says so plainly if it didn't, rather than rendering
    empty boxes.
  * The per-batch data files under reports/data/. These grow with every run,
    so inlining them into every page would mean rewriting every page on
    every run and shipping the whole history to a reader who wants one
    batch. index.html is the exception: its history rows are small and are
    inlined, so the landing page needs no fetch at all.

The fetch means charts.html and trace.html need to be served over HTTP.
That is what GitHub Pages does. Opening them from a file:// path shows a
message saying to run `python3 -m http.server` in reports/ instead of
failing silently — browsers block file:// fetches as a cross-origin read.
"""

import html
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from report_common import CSS, favicon_link

# One icon for the whole dashboard, so the four pages read as one site in a
# tab strip. The individual reports keep their own (chart, puzzle piece).
FAVICON = "\U0001F3D4️"   # snow-capped mountain

# No integrity attribute: the sandbox this was written in cannot reach the
# CDN, and a guessed hash would silently break every chart on the site. The
# version is pinned, which is the part that matters for reproducibility.
# Worth adding a real sha384 here if you can fetch the file once.
CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"

NAV = [
    ("index.html", "Reports"),
    ("charts.html", "Charts"),
    ("params.html", "Parameters"),
    ("trace.html", "Traces"),
]

SHARED_CSS = """
.wrap { max-width: 1180px; }
.prose, .summary, .disclaimer, footer.page { max-width: 80ch; }
a { color: var(--accent); }
nav.site {
  background: var(--panel); border-bottom: 1px solid var(--line);
  margin-bottom: 2rem; position: sticky; top: 0; z-index: 5;
}
nav.site .wrap { display: flex; gap: 0.3rem; flex-wrap: wrap; padding-top: 0.4rem; padding-bottom: 0.4rem; }
nav.site a {
  padding: 0.35rem 0.85rem; border-radius: 6px; text-decoration: none;
  color: var(--ink-soft); font-size: 0.92rem; font-weight: 600;
}
nav.site a:hover { background: var(--paper); color: var(--accent); }
nav.site a[aria-current="page"] { background: var(--accent); color: #fbf3e6; }
header.page { margin-bottom: 0; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 1rem; }
.scroll table { margin: 0; font-size: 0.88rem; }
.scroll th, .scroll td { padding: 0.42rem 0.6rem; }
.scroll + p.note { margin-top: 0.3rem; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.kind { display: inline-block; padding: 0.05rem 0.5rem; border-radius: 999px;
        font-size: 0.78rem; font-weight: 600; border: 1px solid var(--line); }
.kind.structural { background: #e6edf5; color: #2f4a6b; }
.kind.reasoning  { background: #f0e8f5; color: #573b6b; }
.kind.other      { background: #ece9e2; color: var(--ink-soft); }
.controls { margin: 1.2rem 0 0.8rem 0; display: flex; gap: 0.5rem;
            flex-wrap: wrap; align-items: center; }
.controls .label { font-size: 0.85rem; color: var(--ink-soft); }
button.btn, select.ctl, input.ctl {
  font: inherit; font-size: 0.88rem; padding: 0.3rem 0.8rem;
  border-radius: 6px; border: 1px solid var(--line);
  background: var(--panel); color: var(--ink);
}
button.btn { cursor: pointer; font-weight: 600; }
button.btn:hover { border-color: var(--accent); color: var(--accent); }
button.btn.primary { background: var(--accent); border-color: var(--accent); color: #fbf3e6; }
button.btn.primary:hover { color: #fff; opacity: 0.92; }
button.btn[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fbf3e6; }
.chartbox {
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 1rem 1.1rem 0.8rem 1.1rem; margin: 0.6rem 0 1.6rem 0;
}
.chartbox h3 { margin: 0 0 0.2rem 0; color: var(--accent); font-size: 1rem; }
.chartbox .cap { color: var(--ink-soft); font-size: 0.85rem; margin: 0 0 0.7rem 0; max-width: 78ch; }
.chartwrap { position: relative; height: 340px; }
.banner {
  border-radius: 6px; padding: 0.8rem 1.1rem; margin: 1rem 0;
  border-left: 5px solid var(--disclaimer-border); background: var(--disclaimer-bg);
  font-size: 0.95rem;
}
.banner.hidden { display: none; }
.empty { color: var(--ink-soft); font-style: italic; }
code { font-size: 0.9em; background: rgba(127,127,127,0.13); padding: 0.05rem 0.3rem; border-radius: 3px; }
pre.code {
  background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
  padding: 0.8rem 1rem; overflow-x: auto; font-size: 0.85rem; line-height: 1.45;
}
@media (prefers-color-scheme: dark) {
  .kind.structural { background: #24313f; color: #a8c6e6; }
  .kind.reasoning  { background: #332a3d; color: #d0b3e6; }
  .kind.other      { background: #322d25; color: var(--ink-soft); }
}
"""

# Palette for chart series. Pulled from the report shell's accents so the
# charts read as part of the same document, and checked to stay legible on
# both the light and dark page backgrounds.
SERIES_COLORS = ["#6b3f2a", "#3f6b3f", "#2f4a6b", "#a13b3b",
                 "#8a6b1f", "#573b6b", "#1f6b6b", "#9c6b4c"]

# Chart.js defaults + the two helpers every chart page uses: a theme-aware
# grid/tick colour, and the "did Chart.js actually load" guard.
CHART_BOOT = """
const PALETTE = %s;
function themeInk() {
  return getComputedStyle(document.body).getPropertyValue('color') || '#2a2622';
}
function gridColor() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.10)';
}
function chartsAvailable(bannerId) {
  if (typeof Chart !== 'undefined') return true;
  const b = document.getElementById(bannerId);
  if (b) {
    b.textContent = 'Chart.js could not be loaded from the CDN, so the charts on this '
      + 'page are unavailable. The same numbers are in the report tables linked above. '
      + 'If this is a blocked network rather than an outage, the script tag at the '
      + 'bottom of this page is the only external request the site makes.';
    b.classList.remove('hidden');
  }
  return false;
}
function baseOptions(extra) {
  const o = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: themeInk(), boxWidth: 12, font: { size: 12 } } },
      tooltip: { padding: 10 }
    },
    scales: {
      x: { ticks: { color: themeInk(), font: { size: 11 } }, grid: { color: gridColor() } },
      y: { ticks: { color: themeInk(), font: { size: 11 } }, grid: { color: gridColor() },
           beginAtZero: true }
    }
  };
  return Object.assign(o, extra || {});
}
""" % json.dumps(SERIES_COLORS)

# file:// blocks fetch as a cross-origin read; say so instead of showing an
# empty page and letting the reader think the data is missing.
FETCH_HELPER = """
async function loadJSON(path) {
  if (location.protocol === 'file:') {
    throw new Error('This page reads its data with fetch(), which browsers block on '
      + 'file:// URLs. Serve the folder instead: run "python3 -m http.server" inside '
      + 'reports/ and open http://localhost:8000/, or just use the published Pages site.');
  }
  const res = await fetch(path, { cache: 'no-cache' });
  if (!res.ok) throw new Error('could not load ' + path + ' (HTTP ' + res.status + ')');
  return res.json();
}
function showError(id, err) {
  const b = document.getElementById(id);
  if (!b) return;
  b.textContent = String(err.message || err);
  b.classList.remove('hidden');
}
"""


def esc(x):
    return html.escape(str(x))


def nav_html(active):
    links = []
    for href, label in NAV:
        cur = ' aria-current="page"' if href == active else ""
        links.append(f'<a href="{href}"{cur}>{esc(label)}</a>')
    return '<nav class="site"><div class="wrap">' + "".join(links) + "</div></nav>"


def page(title, header_title, header_meta, body, active,
         extra_css="", extra_js="", chart_js=False, footer=None):
    """One complete dashboard page. `extra_js` runs after Chart.js (if
    requested) and after the DOM, so it can touch both."""
    foot = footer or ("Generated by scripts/ from the committed reports and history. "
                      "Every page is a single file; no build step.")
    scripts = ""
    if chart_js:
        scripts += f'<script src="{CHART_JS}" crossorigin="anonymous"></script>\n'
    if extra_js:
        scripts += f"<script>\n{extra_js}\n</script>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{favicon_link(FAVICON)}
<style>{CSS}{SHARED_CSS}{extra_css}</style>
</head>
<body>
<header class="page"><div class="wrap">
  <h1>{header_title}</h1>
  <div class="meta">{header_meta}</div>
</div></header>
{nav_html(active)}
<div class="wrap">
{body}
<footer class="page">{foot}</footer>
</div>
{scripts}
</body>
</html>"""
