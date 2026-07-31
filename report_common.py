"""
Shared HTML shell for the Lodge's standalone reports (structural + reasoning).

Both reports are single self-contained .html files meant to be opened
directly in a browser — no server, no external assets, no build step. This
module only supplies the page shell and shared CSS so the two report
generators don't duplicate styling; it has no opinion about report content.

Styling follows HOUSE STYLE — Design System v3: quiet type, disciplined
neutrals, colour used only as information. Three notes on how the spec meets
this codebase:

  * Fonts. The system asks for Roboto / Roboto Mono. These pages are
    self-contained by design, so no webfont is fetched; the stacks below name
    Roboto first (it renders where installed) and fall back to system-ui /
    Arial, which §7.10 sanctions as part of the system. Fit is not used —
    it is licensed through Adobe Fonts and there is no head title here that
    calls for it.
  * Dark mode. The system is light-only. The pages already supported a dark
    scheme and dropping it would be a regression, so dark is derived from the
    same tokens: neutrals reverse, and the accent moves up the Cobalt ramp to
    --cA4, because Cobalt itself does not clear the contrast floor on Ink.
  * Roles vs tokens. The palette tokens below are the spec verbatim and never
    change. Everything else references the role variables (--bg, --surface,
    --text, --rule, --accent …), which is what the dark block remaps.
"""

import html
from urllib.parse import quote

CSS = """
:root {
  /* ---- HOUSE STYLE v3 tokens (§8), verbatim ---- */
  --ink: #101215; --n800: #2C313A; --n600: #5A606D; --n500: #7C828E;
  --n300: #C4C8D0; --n200: #E3E5EA; --n100: #F1F2F5; --n050: #F8F9FB;
  --paper: #FFFFFF;
  --cobalt: #0A45F5; --cobalt-press: #0836C2; --cobalt-tint: #C2D0FC;
  --vermilion: #F01818;
  --success: #10A257; --warning: #F5A623; --danger: #E5352B; --info: #0A45F5;
  /* chart Mode A — Cobalt tints (dark->light) */
  --cA1: #062A99; --cA2: #0A45F5; --cA3: #4773F7; --cA4: #84A2FA; --cA5: #C2D0FC;
  /* chart Mode B — Vermilion tints (dark->light) */
  --cB1: #900E0E; --cB2: #F01818; --cB3: #F55C5C; --cB4: #F98F8F; --cB5: #FDBFBF;
  --o100: 1; --o72: .72; --o48: .48; --o24: .24; --o12: .12; --o06: .06;
  --radius: 4px; --radius-lg: 8px;
  --sans: 'Roboto', system-ui, -apple-system, 'Segoe UI', Arial, sans-serif;
  --mono: 'Roboto Mono', ui-monospace, Menlo, monospace;

  /* ---- 8pt spacing (§6) ---- */
  --s4: 4px; --s8: 8px; --s12: 12px; --s16: 16px; --s24: 24px;
  --s32: 32px; --s48: 48px; --s64: 64px; --s96: 96px;

  /* ---- type scale (§5), 1.25 major third on a 16px base ---- */
  --t-display: 49px; --t-h1: 39px; --t-h2: 31px; --t-h3: 25px; --t-h4: 20px;
  --t-body: 16px; --t-small: 14px; --t-caption: 13px; --t-micro: 11px;

  /* ---- roles: light ---- */
  --bg: var(--n050);
  --surface: var(--paper);
  --surface-2: var(--n100);
  --zebra: var(--n050);
  --text: var(--ink);
  --text-muted: var(--n600);
  --rule: var(--n200);
  --rule-strong: var(--n300);
  --accent: var(--cobalt);
  --accent-press: var(--cobalt-press);
  --accent-tint: var(--cobalt-tint);
  --on-accent: var(--paper);
  --mark: var(--cobalt-tint);
}
@media (prefers-color-scheme: dark) {
  :root {
    /* Derived, not specified: the two lifted surfaces are Ink stepped toward
       N-800 so panels separate from the ground without a shadow. */
    --bg: var(--ink);
    --surface: #191C22;
    --surface-2: var(--n800);
    --zebra: #15181D;
    --text: var(--n100);
    --text-muted: var(--n300);
    --rule: #343A44;
    --rule-strong: #464D59;
    --accent: var(--cA4);
    --accent-press: var(--cA5);
    --accent-tint: #1C2B58;
    --on-accent: var(--ink);
    --mark: #22346B;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0 0 var(--s64) 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: var(--t-body);
  font-weight: 400;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.wrap {
  max-width: 920px;
  margin: 0 auto;
  padding: 0 var(--s24);
}
/* Flat by default (§6): the banner is neutral, and the single Cobalt rule at
   the top is the view's one Cobalt moment. */
header.page {
  background: var(--surface);
  border-top: 3px solid var(--cobalt);
  border-bottom: 1px solid var(--rule);
  color: var(--text);
  padding: var(--s48) 0 var(--s32) 0;
  margin-bottom: var(--s48);
}
header.page .wrap h1 {
  margin: 0 0 var(--s8) 0;
  font-size: var(--t-h1);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -0.01em;
}
header.page .wrap .meta {
  color: var(--text-muted);
  font-size: var(--t-small);
  line-height: 1.45;
}
h2 {
  font-size: var(--t-h2);
  line-height: 1.15;
  font-weight: 500;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s8);
  margin-top: var(--s48);
  margin-bottom: var(--s16);
}
h3 {
  font-size: var(--t-h3);
  line-height: 1.2;
  font-weight: 500;
  color: var(--text);
  margin-top: var(--s32);
  margin-bottom: var(--s8);
}
h4 { font-size: var(--t-h4); line-height: 1.3; font-weight: 500; }
p { max-width: 72ch; }
a { color: var(--accent); text-underline-offset: 2px; }
a:hover { color: var(--accent-press); }
.summary {
  font-size: var(--t-body);
  background: var(--surface);
  border: 1px solid var(--rule);
  border-left: 3px solid var(--cobalt);
  border-radius: var(--radius);
  padding: var(--s16) var(--s24);
}
/* Warning is functional state, so it carries the rule; the fill stays neutral
   to keep the view's colour coverage where §2 wants it. */
.disclaimer {
  background: var(--surface-2);
  border-left: 4px solid var(--warning);
  border-radius: 0 var(--radius) var(--radius) 0;
  padding: var(--s16) var(--s24);
  margin: var(--s24) 0;
  font-size: var(--t-small);
}
.disclaimer strong { color: var(--text); font-weight: 500; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: var(--s12) 0 var(--s24) 0;
  background: var(--surface);
  font-size: var(--t-small);
  border-radius: 0;
}
caption {
  caption-side: top;
  text-align: left;
  font-weight: 500;
  color: var(--text);
  padding-bottom: var(--s8);
}
th, td {
  border: 1px solid var(--rule);
  padding: var(--s8) var(--s12);
  text-align: right;
}
/* Mono for data (§5); the label column stays sans. */
td:not(:first-child) { font-family: var(--mono); font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
thead th {
  background: var(--surface-2);
  color: var(--text);
  font-weight: 500;
}
tbody tr:nth-child(even) { background: var(--zebra); }
.note {
  color: var(--text-muted);
  font-size: var(--t-caption);
  line-height: 1.4;
  margin: calc(-1 * var(--s12)) 0 var(--s24) 0;
}
/* Never colour alone (§7.9): the dot is a second cue and the pill's own text
   states the state, so the label reads in grayscale. */
.pill {
  display: inline-flex;
  align-items: baseline;
  gap: var(--s8);
  padding: var(--s4) var(--s8);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  font-size: var(--t-caption);
  font-weight: 500;
}
.pill::before {
  content: "";
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--n500);
}
.pill.ok::before { background: var(--success); }
.pill.bad::before { background: var(--danger); }
code {
  font-family: var(--mono);
  font-size: 0.875em;
  background: var(--surface-2);
  border: 1px solid var(--rule);
  padding: 0 var(--s4);
  border-radius: var(--radius);
}
footer.page {
  margin-top: var(--s48);
  padding-top: var(--s16);
  border-top: 1px solid var(--rule);
  color: var(--text-muted);
  font-size: var(--t-caption);
}
"""


def favicon_link(emoji):
    """An emoji as the tab icon, inline — the reports have no asset directory
    to put a .ico in, and a browser asking for /favicon.ico on a static host
    is a 404 in every reader's console."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           f'<text y=".9em" font-size="90">{html.escape(emoji)}</text></svg>')
    return f'<link rel="icon" href="data:image/svg+xml,{quote(svg)}">'


def html_shell(title, favicon_emoji, header_title, header_meta, body_html):
    """title: <title> text. header_title/header_meta: the on-page banner.
    body_html: everything below the banner, already-escaped where needed."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{favicon_link(favicon_emoji)}
<style>{CSS}</style>
</head>
<body>
<header class="page"><div class="wrap">
  <h1>{header_title}</h1>
  <div class="meta">{header_meta}</div>
</div></header>
<div class="wrap">
{body_html}
<footer class="page">Generated by the Lodge simulation harness. Self-contained — no external assets.</footer>
</div>
</body>
</html>"""


def esc(x):
    return html.escape(str(x))


def table(headers, rows, caption=None, note=None):
    """headers: list of column labels. rows: list of lists (already strings)."""
    out = ["<table>"]
    if caption:
        out.append(f"<caption>{esc(caption)}</caption>")
    out.append("<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead>")
    out.append("<tbody>")
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    if note:
        out.append(f'<p class="note">{esc(note)}</p>')
    return "\n".join(out)
