"""
LLM client for stage 2.

Handles: JSON-only output contract, malformed-response retry, concurrency,
cost accounting, and a deterministic MockLLM so the whole pipeline can be
tested end to end without spending anything.
"""

import json
import os
import re
import random
import threading
from concurrent.futures import ThreadPoolExecutor

PRICES = {  # USD per million tokens (in, out)
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-5-20250929": (3.00, 15.00),
}


def extract_json(text):
    """Agents are told JSON only, but models add fences and preamble."""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


class LLM:
    def __init__(self, model="claude-haiku-4-5-20251001", max_tokens=400,
                 workers=8, verbose=False):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.max_tokens = max_tokens
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.verbose = verbose
        self._lock = threading.Lock()
        self.calls = 0
        self.in_tok = 0
        self.out_tok = 0
        self.malformed = 0

    def _one(self, system, user, retries=1):
        for attempt in range(retries + 1):
            try:
                r = self.client.messages.create(
                    model=self.model, max_tokens=self.max_tokens,
                    system=system, messages=[{"role": "user", "content": user}])
            except Exception as e:
                if attempt >= retries:
                    return None
                continue
            with self._lock:
                self.calls += 1
                self.in_tok += r.usage.input_tokens
                self.out_tok += r.usage.output_tokens
            text = "".join(b.text for b in r.content if b.type == "text")
            data = extract_json(text)
            if data is not None:
                return data
            with self._lock:
                self.malformed += 1
            user = user + "\n\nYour last reply was not valid JSON. Reply with the JSON object only."
        return None

    def ask(self, system, user):
        return self._one(system, user)

    def ask_many(self, jobs):
        """jobs: list of (key, system, user) -> dict key -> parsed json | None"""
        futs = {k: self.pool.submit(self._one, s, u) for k, s, u in jobs}
        return {k: f.result() for k, f in futs.items()}

    def cost(self):
        pin, pout = PRICES.get(self.model, (0, 0))
        return (self.in_tok / 1e6) * pin + (self.out_tok / 1e6) * pout

    def summary(self):
        return (f"calls={self.calls} in={self.in_tok} out={self.out_tok} "
                f"malformed={self.malformed} est_cost=${self.cost():.2f}")


class MockLLM:
    """Deterministic stand-in. Verifies plumbing, costs nothing.

    Emits plausible reasoning text so the §8.3 detection parser can be tested:
    a fraction of responses mention the plates.
    """

    def __init__(self, seed=0, plate_mention_rate=0.12, **kw):
        self.rng = random.Random(seed)
        self.plate_mention_rate = plate_mention_rate
        self.calls = 0
        self.in_tok = self.out_tok = self.malformed = 0
        self.model = "mock"

    def _one(self, system, user, retries=1):
        self.calls += 1
        names = re.findall(r"\bP\d{2}\b", user)
        target = self.rng.choice(names) if names else None
        reasoning = "considering the table."
        if "SAT_DINNER" in user and self.rng.random() < self.plate_mention_rate:
            reasoning = "the plates are not all the same; the cairn motif is odd."
        action = "END" if self.rng.random() < 0.5 else "BANISH"
        return {"reasoning": reasoning, "action": action, "target": target,
                "accept": self.rng.random() < 0.4,
                "questions": [], "text": "..."}

    def ask(self, system, user):
        return self._one(system, user)

    def ask_many(self, jobs):
        return {k: self._one(s, u) for k, s, u in jobs}

    def cost(self):
        return 0.0

    def summary(self):
        return f"MOCK calls={self.calls} est_cost=$0.00"
