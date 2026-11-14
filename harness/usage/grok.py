"""Grok: the `--output-format streaming-json` stream the seat loop keeps (`<log-dir>/grok-c<cycle>.jsonl`).

A `{"type": "usage"}` event opens each response, and the `tool_call` events up to the next one are the calls
that response issued. A civ5 call is a `use_tool` whose `rawInput.tool_name` is `civ5__<tool>` (a client that
lists the server's tools directly names the tool itself). `input_tokens` is the full-price part, the cached part
is beside it, `reasoning_tokens` is inside `output_tokens`. An event has **no time and no model**: `t` is None
unless the line was stamped on arrival (a `t` key, what the seat loop adds in stage 2, #185), and the model and
the session id come from the stream's last row, `end`, which also carries the client's own total (`total`).
A stream cut off before `end` (a killed cycle, a 402) keeps its rows with no model. Read off Grok CLI 1.0.41
(2026-11-13).
"""
from __future__ import annotations

from typing import Any, Iterable

from harness.usage import rows

SOURCE = "grok-stream"


def counts(u: Any) -> dict[str, int]:
    u = u if isinstance(u, dict) else {}
    return {"new_in": u.get("input_tokens") or 0, "cache_read": u.get("cache_read_input_tokens") or 0,
            "cache_write": u.get("cache_creation_input_tokens") or 0, "out": u.get("output_tokens") or 0,
            "reasoning": u.get("reasoning_tokens") or 0}


def read(lines: Iterable[str], server: str = "civ5", model: str | None = None) -> list[dict]:
    """One row per response, in stream order; `request` is its position (the stream names none)."""
    out: list[dict] = []
    session = None
    for o in rows.parsed(lines):
        kind = o.get("type")
        if kind == "usage" and isinstance(o.get("usage"), dict):
            out.append(rows.row(t=rows.epoch(o.get("t")), client="grok", model=model, session=None,
                                request=str(len(out)), counts=counts(o["usage"]), source=SOURCE))
        elif kind == "tool_call" and out:
            raw = o.get("rawInput") if isinstance(o.get("rawInput"), dict) else {}
            if o.get("toolName") == "use_tool":
                bare, args = rows.bare_name(raw.get("tool_name"), server), raw.get("tool_input")
            else:
                bare, args = rows.bare_name(o.get("toolName"), server), raw
            if bare is not None:
                out[-1]["calls"].append(rows.call(bare, args))
        elif kind == "end":
            session = o.get("sessionId") or session
            used = o.get("modelUsage")
            if model is None and isinstance(used, dict) and len(used) == 1:
                model = next(iter(used))
    for r in out:
        r["model"], r["session"] = r["model"] or model, session
    return out


def total(lines: Iterable[str]) -> dict[str, int] | None:
    """The client's own total, from the `end` row; None for a stream that never reached it."""
    last: Any = None
    for o in rows.parsed(lines):
        if o.get("type") == "end" and isinstance(o.get("usage"), dict):
            last = o["usage"]
    return counts(last) if last is not None else None
