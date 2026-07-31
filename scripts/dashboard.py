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

Styling comes from report_common.CSS — HOUSE STYLE v3 — plus the nav, chart
and control rules below. Two of that system's laws bind hardest here:

  * Colour is information (§7.1-2). Cobalt marks exactly one thing per view —
    the active nav tab, the changed slider, the link — and nothing is coloured
    to look nice. Vermilion appears in one place on the whole site, the
    Traitor edge in the trace, which is what "<1%, never without Cobalt" means
    in practice.
  * Every chart is one family of tints (§3). SERIES_COLORS is Mode A, the
    Cobalt ramp, and no chart mixes it with anything. Where the data is
    nominal rather than ordered, series are told apart by position, direct
    label, dash and point shape — never by tint step alone.
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
nav.site {
  background: var(--surface); border-bottom: 1px solid var(--rule);
  margin-bottom: var(--s32); position: sticky; top: 0; z-index: 5;
}
nav.site .wrap { display: flex; gap: var(--s4); flex-wrap: wrap;
                 padding-top: var(--s8); padding-bottom: var(--s8); }
nav.site a {
  padding: var(--s8) var(--s12); border-radius: var(--radius); text-decoration: none;
  color: var(--text-muted); font-size: var(--t-small); font-weight: 500;
}
nav.site a:hover { background: var(--surface-2); color: var(--accent); }
/* The active tab is the nav's Cobalt moment; the aria-current attribute
   carries the same fact for anyone not reading colour. */
nav.site a[aria-current="page"] {
  background: var(--cobalt); color: var(--paper); font-weight: 500;
}
header.page { margin-bottom: 0; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: var(--s16); }
.scroll table { margin: 0; font-size: var(--t-caption); }
.scroll th, .scroll td { padding: var(--s8) var(--s12); }
.scroll + p.note { margin-top: var(--s4); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums;
                 font-family: var(--mono); }
th.num { font-family: var(--sans); }
/* Report kind is a nominal category, so it is carried by the label, not by a
   hue per kind (§7.3, §7.9). */
.kind {
  display: inline-block; padding: 0 var(--s8); border-radius: var(--radius);
  font-family: var(--mono); font-size: var(--t-micro); line-height: 1.6;
  font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em;
  border: 1px solid var(--rule); background: var(--surface-2); color: var(--text-muted);
}
.controls { margin: var(--s24) 0 var(--s12) 0; display: flex; gap: var(--s8);
            flex-wrap: wrap; align-items: center; }
.controls .label { font-size: var(--t-small); color: var(--text-muted); font-weight: 500; }
button.btn, select.ctl, input.ctl {
  font-family: var(--sans); font-size: var(--t-small); padding: var(--s8) var(--s12);
  border-radius: var(--radius); border: 1px solid var(--rule-strong);
  background: var(--surface); color: var(--text);
}
select.ctl:focus-visible, input.ctl:focus-visible, button.btn:focus-visible {
  outline: 2px solid var(--cobalt); outline-offset: 1px;
}
button.btn { cursor: pointer; font-weight: 500; }
button.btn:hover { border-color: var(--accent); color: var(--accent); }
button.btn.primary { background: var(--cobalt); border-color: var(--cobalt); color: var(--paper); }
button.btn.primary:hover { background: var(--cobalt-press); border-color: var(--cobalt-press);
                           color: var(--paper); }
button.btn[aria-pressed="true"] { background: var(--cobalt); border-color: var(--cobalt);
                                  color: var(--paper); }
.chartbox {
  background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius-lg);
  padding: var(--s16) var(--s16) var(--s12) var(--s16); margin: var(--s8) 0 var(--s24) 0;
}
.chartbox h3 { margin: 0 0 var(--s4) 0; color: var(--text);
               font-size: var(--t-h4); line-height: 1.3; font-weight: 500; }
.chartbox .cap { color: var(--text-muted); font-size: var(--t-small); line-height: 1.45;
                 margin: 0 0 var(--s12) 0; max-width: 78ch; }
.chartwrap { position: relative; height: 340px; }
.banner {
  border-radius: 0 var(--radius) var(--radius) 0; padding: var(--s12) var(--s16);
  margin: var(--s16) 0;
  border-left: 4px solid var(--warning); background: var(--surface-2);
  font-size: var(--t-small);
}
.banner.hidden { display: none; }
.empty { color: var(--text-muted); font-style: italic; }
pre.code {
  background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
  padding: var(--s12) var(--s16); overflow-x: auto;
  font-family: var(--mono); font-size: var(--t-caption); line-height: 1.45;
}
"""

# Chart series colour — HOUSE STYLE §3 Mode A, the Cobalt tint ramp, dark to
# light. Every chart on the site is one family: no chart mixes Cobalt and
# Vermilion, and there are no foreign hues. Five steps is the legible ceiling
# the spec sets, so anything needing more than five series distinguishes them
# by dash pattern and point shape as well (§7.9 — never colour alone).
SERIES_COLORS = ["#062A99", "#0A45F5", "#4773F7", "#84A2FA", "#C2D0FC"]

# Chart.js defaults + the helpers every chart page uses: theme-aware ink and
# grid colours read from the live tokens, dash/point patterns for multi-series
# charts, and the "did Chart.js actually load" guard.
CHART_BOOT = """
// The Mode A ramp, ordered by EMPHASIS rather than by lightness: PALETTE[0] is
// always the step that carries hardest against the page. On Paper that is the
// dark end; on an Ink ground the ramp reverses, because #062A99 on #191C22 is
// under the 3:1 mark floor while #C2D0FC is the one that reads. Same family,
// same five steps — §3 is about the family, not the direction.
const RAMP_A = %s;
const PALETTE = window.matchMedia('(prefers-color-scheme: dark)').matches
  ? RAMP_A.slice().reverse() : RAMP_A;
// Series beyond the fifth reuse a tint but change dash and point shape, so no
// two series on one chart are told apart by colour alone.
const DASHES = [[], [6, 4], [2, 3]];
const POINTS = ['circle', 'rect', 'triangle'];
function token(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
function themeInk() { return token('--text', '#101215'); }
function themeMuted() { return token('--text-muted', '#5A606D'); }
function gridColor() { return token('--rule', '#E3E5EA'); }
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
      legend: { labels: { color: themeInk(), boxWidth: 12, boxHeight: 12,
                          font: { family: 'Roboto, system-ui, Arial, sans-serif', size: 12 } } },
      tooltip: { padding: 10, backgroundColor: '#101215', cornerRadius: 4,
                 titleFont: { family: 'Roboto, system-ui, Arial, sans-serif', weight: '500' },
                 bodyFont: { family: 'Roboto Mono, ui-monospace, Menlo, monospace' } }
    },
    scales: {
      x: { ticks: { color: themeMuted(), font: { size: 11 } }, grid: { color: gridColor() },
           border: { color: gridColor() } },
      y: { ticks: { color: themeMuted(), font: { size: 11 } }, grid: { color: gridColor() },
           border: { color: gridColor() }, beginAtZero: true }
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
