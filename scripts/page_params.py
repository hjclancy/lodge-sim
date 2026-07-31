"""Builds reports/params.html — the archetype parameter sliders.

Defaults are read from archetypes.json at build time and inlined, so the page
works from a file:// path and can't drift from the committed file: rebuilding
the dashboard after editing archetypes.json updates the sliders' baseline.

The page produces JSON to paste into the structural workflow's
archetype_overrides input. It deliberately copies only the parameters that
differ from the defaults, because that is what the input expects — a full
twelve-by-ten object would work too, but it would record every parameter as
"overridden" in the report and make a two-slider experiment unreadable.
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
for _p in (_REPO, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from archetypes import ALL_IDS, ARCHETYPES, PARAM_KEYS, PARAMS_DIGEST, load_params
import dashboard as dash

EXTRA_CSS = """
.arch { border: 1px solid var(--rule); background: var(--surface); border-radius: var(--radius-lg);
        padding: var(--s16); margin-bottom: var(--s16); }
.arch > header { display: flex; align-items: baseline; gap: var(--s12); flex-wrap: wrap;
                 margin-bottom: var(--s12); }
.arch h3 { margin: 0; font-size: var(--t-h4); line-height: 1.3; font-weight: 500;
           color: var(--text); }
.arch .aid { font-family: var(--mono); font-size: var(--t-small); color: var(--text-muted); }
.arch .changed-count { margin-left: auto; font-size: var(--t-caption);
                       font-family: var(--mono); color: var(--text-muted); }
/* "Changed from the committed defaults" is the one thing on this page worth
   colour, so it is the only place Cobalt appears in the body. */
.arch.dirty { border-color: var(--cobalt); }
.arch.dirty .changed-count { color: var(--accent); font-weight: 500; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: var(--s4) var(--s24); }
.row { display: grid; grid-template-columns: 6.5rem 1fr 3.2rem; align-items: center;
       gap: var(--s8); padding: var(--s4) 0; }
.row label { font-size: var(--t-small); color: var(--text-muted); }
.row.dirty label { color: var(--accent); font-weight: 500; }
.row output { font-family: var(--mono); font-size: var(--t-small); text-align: right;
              font-variant-numeric: tabular-nums; }
.row .dot { display: none; }
.row.dirty output::after { content: " •"; color: var(--accent); }
/* accent-color would fill the whole track, and 120 filled tracks on one page
   is nowhere near §2's ~89% neutral. The track stays a neutral rule and only
   the thumb — which is the part that actually carries the value — is Cobalt. */
input[type=range], input.ctl[type=range] {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 16px; background: transparent; cursor: pointer;
  border: none; padding: 0;
}
input[type=range]::-webkit-slider-runnable-track {
  height: 2px; background: var(--rule-strong); border-radius: 0;
}
input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 12px; height: 12px; margin-top: -5px; border: none;
  border-radius: 50%; background: var(--accent);
}
input[type=range]::-moz-range-track {
  height: 2px; background: var(--rule-strong); border-radius: 0;
}
input[type=range]::-moz-range-thumb {
  width: 12px; height: 12px; border: none; border-radius: 50%; background: var(--accent);
}
input[type=range]:focus-visible { outline: 2px solid var(--cobalt); outline-offset: 2px; }
.sticky-actions {
  position: sticky; bottom: 0; background: var(--bg);
  border-top: 1px solid var(--rule); padding: var(--s12) 0; margin-top: var(--s16);
  display: flex; gap: var(--s8); align-items: center; flex-wrap: wrap; z-index: 4;
}
.sticky-actions .status { font-size: var(--t-small); color: var(--text-muted); }
/* The button already says "Copied"; the check is the second cue. On a
   secondary button Success rides the border and the glyph, so the label stays
   at full contrast. On the Cobalt primary the glyph stays white — Success on
   Cobalt is neither legible nor a pairing the system allows. */
.copied { font-weight: 500; }
.copied::before { content: "\\2713\\00a0"; }
button.btn.copied:not(.primary) { color: var(--text); border-color: var(--success); }
button.btn.copied:not(.primary)::before { color: var(--success); }
details.preview { margin-top: var(--s12); }
details.preview summary { cursor: pointer; font-size: var(--t-small); color: var(--accent); }
"""

SCRIPT = r"""
const DEFAULTS = __DEFAULTS__;
const KEYS = __KEYS__;
const IDS = __IDS__;

const state = JSON.parse(JSON.stringify(DEFAULTS));

function round2(v) { return Math.round(v * 100) / 100; }

function changedSubset() {
  const out = {};
  for (const aid of IDS) {
    for (const k of KEYS) {
      if (round2(state[aid][k]) !== round2(DEFAULTS[aid][k])) {
        (out[aid] = out[aid] || {})[k] = round2(state[aid][k]);
      }
    }
  }
  return out;
}

function countChanged() {
  let n = 0;
  for (const aid of IDS) for (const k of KEYS) {
    if (round2(state[aid][k]) !== round2(DEFAULTS[aid][k])) n++;
  }
  return n;
}

function refresh() {
  for (const aid of IDS) {
    let dirty = 0;
    for (const k of KEYS) {
      const row = document.getElementById('row-' + aid + '-' + k);
      const changed = round2(state[aid][k]) !== round2(DEFAULTS[aid][k]);
      row.classList.toggle('dirty', changed);
      if (changed) dirty++;
    }
    const card = document.getElementById('card-' + aid);
    card.classList.toggle('dirty', dirty > 0);
    card.querySelector('.changed-count').textContent =
      dirty ? dirty + ' changed' : '';
  }
  const n = countChanged();
  document.getElementById('status').textContent = n === 0
    ? 'No changes — this is the committed archetypes.json.'
    : n + ' parameter' + (n === 1 ? '' : 's') + ' changed across '
      + Object.keys(changedSubset()).length + ' archetype(s).';
  document.getElementById('preview').textContent =
    n === 0 ? '{}' : JSON.stringify(changedSubset(), null, 2);
}

function setValue(aid, key, value) {
  state[aid][key] = value;
  document.getElementById('out-' + aid + '-' + key).textContent = value.toFixed(2);
  refresh();
}

async function copyText(text, btn) {
  const label = btn.textContent;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      // http:// and file:// have no clipboard API; the textarea trick still works.
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    btn.textContent = 'Copied';
    btn.classList.add('copied');
  } catch (e) {
    btn.textContent = 'Copy failed — select the preview below';
  }
  setTimeout(function () { btn.textContent = label; btn.classList.remove('copied'); }, 1800);
}

document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('input[type=range]').forEach(function (el) {
    el.addEventListener('input', function () {
      setValue(el.dataset.aid, el.dataset.key, parseFloat(el.value));
    });
  });

  document.getElementById('copy-overrides').addEventListener('click', function () {
    const n = countChanged();
    if (n === 0) {
      this.textContent = 'Nothing changed yet';
      const self = this;
      setTimeout(function () { self.textContent = 'Copy config JSON'; }, 1600);
      return;
    }
    copyText(JSON.stringify(changedSubset()), this);
  });

  document.getElementById('copy-full').addEventListener('click', function () {
    const full = { schema: 1, param_keys: KEYS, params: {} };
    for (const aid of IDS) {
      full.params[aid] = {};
      for (const k of KEYS) full.params[aid][k] = round2(state[aid][k]);
    }
    copyText(JSON.stringify(full, null, 2) + '\n', this);
  });

  document.getElementById('reset').addEventListener('click', function () {
    for (const aid of IDS) for (const k of KEYS) {
      state[aid][k] = DEFAULTS[aid][k];
      const el = document.getElementById('in-' + aid + '-' + k);
      el.value = DEFAULTS[aid][k];
      document.getElementById('out-' + aid + '-' + k).textContent =
        DEFAULTS[aid][k].toFixed(2);
    }
    refresh();
  });

  refresh();
});
"""

NOTE = """
<div class="prose">
<h2>What to do with these</h2>
<p>Move any sliders, press <strong>Copy config JSON</strong>, then go to
<strong>Actions → Structural report (heuristic bots) → Run workflow</strong> and paste
into the <code>archetype_overrides</code> box. That run uses your numbers and nothing
else changes: the file in the repository is not touched, no commit is made, and the
next run without an override is back on the committed defaults.</p>
<p>The copied JSON holds only the parameters you actually moved — that is the shape
the input expects, and it keeps the report's override list readable. The report for
that run states which parameters were replaced and records a digest of the exact set
used, so a batch can be told apart from its neighbours later. To change the defaults
for good instead, use <strong>Copy full file</strong> and replace
<code>archetypes.json</code> in the repository.</p>
<p>What the ten parameters mean is <code>archetypes_v1.md</code>'s subject.
What they <em>do</em> is <code>heuristic_bots.py</code>'s, and that file is explicit
that its mapping from parameter to decision is one implementer's modeling choice.
Moving a slider changes how those bots behave; it does not discover anything about
how a person with that temperament would play. The Claude agents read only the
prose persona and a one-line rendering of these numbers, so overrides move the
heuristic tier hard and the reasoning tier barely at all.</p>
</div>
"""


def build(out_dir):
    defaults = load_params()
    cards = []
    for aid in ALL_IDS:
        rows = []
        for key in PARAM_KEYS:
            value = defaults[aid][key]
            rows.append(
                f'<div class="row" id="row-{aid}-{key}">'
                f'<label for="in-{aid}-{key}">{dash.esc(key)}</label>'
                f'<input class="ctl" type="range" id="in-{aid}-{key}" '
                f'min="0" max="1" step="0.01" value="{value}" '
                f'data-aid="{aid}" data-key="{key}" '
                f'aria-label="{aid} {key}">'
                f'<output id="out-{aid}-{key}">{value:.2f}</output>'
                f"</div>"
            )
        cards.append(
            f'<section class="arch" id="card-{aid}">'
            f"<header><h3>{dash.esc(ARCHETYPES[aid]['name'])}</h3>"
            f'<span class="aid">{aid}</span>'
            f'<span class="changed-count"></span></header>'
            f'<div class="grid">{"".join(rows)}</div>'
            f"</section>"
        )

    actions = (
        '<div class="sticky-actions">'
        '<button class="btn primary" id="copy-overrides">Copy config JSON</button>'
        '<button class="btn" id="copy-full">Copy full file</button>'
        '<button class="btn" id="reset">Reset to defaults</button>'
        '<span class="status" id="status"></span>'
        "</div>"
        '<details class="preview"><summary>Preview what gets copied</summary>'
        '<pre class="code" id="preview">{}</pre></details>'
    )

    body = "\n".join([NOTE, "<h2>The twelve archetypes</h2>", *cards, actions])
    script = (SCRIPT
              .replace("__DEFAULTS__", json.dumps(defaults))
              .replace("__KEYS__", json.dumps(list(PARAM_KEYS)))
              .replace("__IDS__", json.dumps(ALL_IDS)))

    doc = dash.page(
        title="The Lodge — Archetype parameters",
        header_title="The Lodge — Archetype parameters",
        header_meta=(f"twelve archetypes &times; ten parameters &middot; "
                     f"committed defaults, digest {PARAMS_DIGEST}"),
        body=body,
        active="params.html",
        extra_css=EXTRA_CSS,
        extra_js=script,
        footer=("Defaults inlined from archetypes.json when this page was generated. "
                "Nothing here writes to the repository."),
    )
    path = os.path.join(out_dir, "params.html")
    with open(path, "w") as f:
        f.write(doc)
    return path
