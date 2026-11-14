"""What the tokens of a usage row would cost at list price (docs/TOKEN_ACCOUNTING.md rule 5, stage 4, #187).

`prices.json` beside this file is the table: per model the dollars per million tokens for new input, cache
reads, cache writes and output, each with the date and the page it was read from. The figure is an estimate
of tokens spent, never money paid: the three clients of this project run on subscriptions. A model the table
does not list has no cost, and neither has any sum that holds one of its requests: `of` gives None and the
report prints no dollar figure there.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from harness.usage import rows

PATH = Path(__file__).with_name("prices.json")

# usage count -> the price it is charged at. `reasoning` is part of `out` and is not charged again.
RATE = {"new_in": "input", "cache_read": "cache_read", "cache_write": "cache_write", "out": "output"}


def load(path: Path | str | None = None) -> dict:
    """The price table: `{"as_of", "unit", "note", "models": {model: {input, cache_read, cache_write, output,
    as_of, source}}}`."""
    with open(path or PATH, encoding="utf-8") as fh:
        table = json.load(fh)
    table.setdefault("models", {})
    return table


def cost(row: dict, price: dict) -> float:
    """Dollars for one usage row (or any dict of the counts) at one model's prices."""
    return sum((row.get(k) or 0) * price[rate] for k, rate in RATE.items()) / 1_000_000


def of(usage: Iterable[dict], table: dict) -> float | None:
    """The cost of the rows together; None when there is no row, or when any row that read or wrote a token
    names a model the table does not list (a partial sum would be a wrong sum)."""
    total, seen = 0.0, False
    for r in usage:
        seen = True
        if not any(r.get(k) for k in rows.COUNTS):
            continue
        price = table["models"].get(r.get("model") or "")
        if price is None:
            return None
        total += cost(r, price)
    return round(total, 4) if seen else None


def unlisted(usage: Iterable[dict], table: dict) -> list[str]:
    """The models of the rows that have no price, sorted ("(no model)" for a row that names none)."""
    return sorted({r.get("model") or "(no model)" for r in usage
                   if any(r.get(k) for k in rows.COUNTS) and (r.get("model") or "") not in table["models"]})
