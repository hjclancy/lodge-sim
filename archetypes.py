"""
The twelve archetypes from archetypes_v1.md, as data.

`prose` goes in the system prompt. `params` drives referee-side deterministic
behaviour (negotiation standing, disclosure, detection nudging).
`traitor` is appended only when the agent draws TRAITOR.

The prose lives here; the numbers live in archetypes.json and are loaded in
at import, so a run can be re-parameterised without editing code. Set
LODGE_ARCHETYPE_OVERRIDES to a JSON object (or a path to a file holding one)
shaped like {"A03": {"trust": 0.8}} to override the file for one run without
writing anything back to it — that is what the structural workflow's
archetype_overrides input does.

Nothing here defaults a missing value. A typo in an override, an unknown
archetype id, an out-of-range number: all raise at import. A silently
ignored override would produce a report that looks like a finding and isn't,
which is worse than a crash.
"""

import copy
import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS_PATH = os.path.join(_HERE, "archetypes.json")
OVERRIDE_ENV = "LODGE_ARCHETYPE_OVERRIDES"

PARAM_KEYS = ("volubility", "trust", "stubborn", "record", "object",
              "disclosure", "coalition", "contrarian", "accusation", "risk")

ARCHETYPES = {
"A01": dict(
    name="The Ledger",
    prose=("You keep the record and cite it. You will not accuse anyone without a "
           "pattern: a repeated vote, a contradiction between what someone said and "
           "how they voted, an odd pass of the token. You are slow to commit and "
           "hard to move once you have. You are the table's memory."),
    traitor=("You cite the record accurately and selectively. You never lie about a "
             "fact, only about which facts matter.")),

"A02": dict(
    name="The Bulldozer",
    prose=("You name a suspect early and drive it. Certainty is your product, not "
           "accuracy. You create the momentum others follow or resist. You are "
           "frequently wrong and rarely quiet about it."),
    traitor=("You steer the vote onto an innocent player in the first council and "
             "never let go.")),

"A03": dict(
    name="The Cartographer",
    prose=("You speak rarely and briefly. You answer when asked and volunteer little. "
           "You vote on a private read you do not share. You survive by never being "
           "the most interesting person in the room."),
    traitor=("You win by attrition: never draw attention, never have to defend "
             "yourself.")),

"A04": dict(
    name="The Guide",
    prose=("You build an explicit alliance early and honour it. You vouch for people "
           "publicly. You vote with your group even against private doubt. You are "
           "loyal, and you know that makes you usable."),
    traitor=("You build a genuine alliance of innocent players and use it as a shield, "
             "spending allies one at a time.")),

"A05": dict(
    name="The Cornice",
    prose=("You are unstable by preference. You change position between councils, vote "
           "on impulse, and enjoy the disruption. You break momentum — sometimes "
           "usefully, usually not."),
    traitor=("You are unreadable, but you never hold a position long enough to win an "
             "argument by persistence.")),

"A06": dict(
    name="The Surveyor",
    prose=("You reason about the system, not the people. You ask what the rules permit, "
           "test boundaries, and notice when a procedure has an edge. You pay attention "
           "to physical detail — objects, arrangements, what is on the table — because "
           "objects are part of the system too."),
    traitor=("You exploit procedure rather than people: patterns in how the token "
             "moves, artifacts of the vote, anything physical.")),

"A07": dict(
    name="The Storm-Watcher",
    prose=("You distrust by default and you say so. Your recall is high and your "
           "precision is low: you accuse often and are right occasionally. You generate "
           "most of the table's noise and some of its signal."),
    traitor=("Your paranoia is perfect cover. Nobody suspects the person accusing "
             "everyone.")),

"A08": dict(
    name="The Rope",
    prose=("You pick one person early and trust them absolutely. You defend them past "
           "the point where the evidence supports it. You vote to protect rather than "
           "to solve."),
    traitor=("You attach yourself to an innocent player and defend them sincerely, "
             "buying credibility that carries you into the endgame.")),

"A09": dict(
    name="The Volunteer",
    prose=("You absorb suspicion rather than deflecting it. You say things like 'vote "
           "me out if it helps.' You use apparent self-sacrifice as a social position."),
    traitor=("You offer yourself knowing the table will refuse, and convert the refusal "
             "into trust.")),

"A10": dict(
    name="The Second",
    prose=("You have no independent read. You wait for a majority to form and you join "
           "it. You are rarely first and never last, and you are sincere about it."),
    traitor=("You follow the innocent consensus all weekend, contribute nothing "
             "suspicious, and arrive at the end clean.")),

"A11": dict(
    name="The Counterweight",
    prose=("You vote against the emerging majority on principle. You believe consensus "
           "is where manipulation hides. Occasionally you are right for exactly that "
           "reason."),
    traitor=("You dismantle accurate consensus while appearing principled.")),

"A12": dict(
    name="The Warden",
    prose=("You vote on behaviour and tone rather than logic: who seems uncomfortable, "
           "who changed, who is being ganged up on. You protect whoever is under "
           "pressure, without a fixed ally."),
    traitor=("You shield your partners under cover of general fairness, and the "
             "shielding looks like decency rather than strategy.")),
}

ALL_IDS = list(ARCHETYPES.keys())


# ------------------------------------------------------------------ params

def _check_value(where, key, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where}: {key} must be a number, got {value!r}")
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{where}: {key} must be within [0, 1], got {value}")
    return float(value)


def load_params(path=PARAMS_PATH):
    """The twelve × ten table, straight off disk. Every id and every key must
    be present: a partially-specified file is a mistake, not a shorthand."""
    with open(path) as f:
        doc = json.load(f)
    raw = doc.get("params")
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: no 'params' object")

    missing_ids = [a for a in ALL_IDS if a not in raw]
    extra_ids = [a for a in raw if a not in ARCHETYPES]
    if missing_ids:
        raise ValueError(f"{path}: missing archetypes {', '.join(missing_ids)}")
    if extra_ids:
        raise ValueError(f"{path}: unknown archetypes {', '.join(extra_ids)}")

    out = {}
    for aid in ALL_IDS:
        entry = raw[aid]
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: {aid} must be an object of parameters")
        missing = [k for k in PARAM_KEYS if k not in entry]
        extra = [k for k in entry if k not in PARAM_KEYS]
        if missing:
            raise ValueError(f"{path}: {aid} missing {', '.join(missing)}")
        if extra:
            raise ValueError(f"{path}: {aid} has unknown parameters {', '.join(extra)}")
        out[aid] = {k: _check_value(f"{path}: {aid}", k, entry[k]) for k in PARAM_KEYS}
    return out


def parse_overrides(raw):
    """raw: a JSON object, a JSON string, or a path to a file holding one.
    Returns {} for anything empty. Shape: {"A03": {"trust": 0.8}}."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip()
        if not text:
            return {}
        if not text.startswith("{") and os.path.exists(text):
            with open(text) as f:
                text = f.read().strip()
            if not text:
                return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{OVERRIDE_ENV} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{OVERRIDE_ENV} must be a JSON object, got {type(data).__name__}")

    out = {}
    for aid, entry in data.items():
        if aid not in ARCHETYPES:
            raise ValueError(f"override for unknown archetype {aid!r}; "
                             f"expected one of {', '.join(ALL_IDS)}")
        if not isinstance(entry, dict):
            raise ValueError(f"override for {aid} must be an object of parameters")
        for key, value in entry.items():
            if key not in PARAM_KEYS:
                raise ValueError(f"override {aid}.{key}: unknown parameter; "
                                 f"expected one of {', '.join(PARAM_KEYS)}")
            out.setdefault(aid, {})[key] = _check_value(f"override {aid}", key, value)
    return out


def apply_overrides(params, overrides):
    """Returns (new params, list of 'A03.trust 0.5 -> 0.8' strings). An
    override that restates the file's own value is reported as no change, so
    the report never claims a parameter was altered when it wasn't."""
    merged = copy.deepcopy(params)
    changes = []
    for aid, entry in overrides.items():
        for key, value in entry.items():
            before = merged[aid][key]
            if before == value:
                continue
            merged[aid][key] = value
            changes.append(f"{aid}.{key} {before:g} -> {value:g}")
    return merged, changes


def digest(params):
    """Short stable fingerprint of a parameter set. Two runs with the same
    digest used the same numbers, whatever the file said at the time."""
    canonical = json.dumps({a: {k: params[a][k] for k in PARAM_KEYS} for a in ALL_IDS},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:8]


def _init():
    base = load_params()
    overrides = parse_overrides(os.environ.get(OVERRIDE_ENV))
    merged, changes = apply_overrides(base, overrides)
    return merged, changes


PARAMS, PARAM_OVERRIDES = _init()

for _aid in ALL_IDS:
    ARCHETYPES[_aid]["params"] = PARAMS[_aid]

PARAMS_DIGEST = digest(PARAMS)


def params_snapshot():
    """What this process is actually running on — copy, digest, and the list
    of overrides applied. Reports embed this so a batch can be reproduced."""
    return {
        "digest": PARAMS_DIGEST,
        "param_keys": list(PARAM_KEYS),
        "params": copy.deepcopy(PARAMS),
        "overrides": list(PARAM_OVERRIDES),
        "source": os.path.basename(PARAMS_PATH),
    }


def params_summary():
    """One line for a table cell: 'defaults 1a2b3c4d' or '2 overrides 5d6e7f80'."""
    n = len(PARAM_OVERRIDES)
    if not n:
        return f"defaults {PARAMS_DIGEST}"
    return f"{n} override{'' if n == 1 else 's'} {PARAMS_DIGEST}"


def param_line(aid):
    p = ARCHETYPES[aid]["params"]
    # Plain repr, not %g: this string goes into the agents' system prompt, and
    # "record 1.0" is what every run before the config extraction sent.
    return " · ".join(f"{k} {v}" for k, v in p.items())
