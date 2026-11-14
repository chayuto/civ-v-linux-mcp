"""The usage row: one model request, in every client's terms.

    {"t": 1794612894.2, "client": "codex/0.166.0", "model": "gpt-6.1-sol", "session": "<id>", "request": "<id>",
     "new_in": 5491, "cache_read": 12032, "cache_write": 0, "out": 100, "reasoning": 0,
     "calls": [{"tool": "state", "action": "units"}], "source": "codex-rollout"}

`new_in + cache_read + cache_write` is everything the model read on that request: `new_in` was read at the full
input price, `cache_read` from the provider's cache, `cache_write` was read and stored. `out` is everything it
wrote and `reasoning` the part of `out` that was thinking, where the client says (all three clients count it
inside the output). `t` is when the response was complete, in epoch seconds, or None when the client's file
carries no time. `calls` are the civ5 calls the request issued, labelled as a ledger row labels them
(`harness.surface.classes.called_as`), so the two files speak of a call in the same words.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable, Iterator

from harness.surface import classes

COUNTS = ("new_in", "cache_read", "cache_write", "out", "reasoning")

# The arguments a call's action label is read from, and the only ones a reader looks at. Everything else a call
# carried (a note's words, a deal's items) stays in the client's file: a fixture cut down to these reads to the
# same rows as the file it was cut from (scripts/cut_usage_fixture.py checks exactly that).
ACTION_ARGS = ("what", "view", "to", "action", "book", "choice")
WORD = re.compile(r"[A-Za-z0-9_.:/<>+-]{1,80}\Z")


def row(*, t: float | None, client: str, model: str | None, session: str | None, request: str | None,
        counts: dict[str, int], calls: list[dict] | None = None, source: str) -> dict[str, Any]:
    return {"t": t, "client": client, "model": model, "session": session, "request": request,
            **{k: int(counts.get(k) or 0) for k in COUNTS}, "calls": calls or [], "source": source}


def total(rows: Iterable[dict]) -> dict[str, int]:
    """The sums a session's own total is compared with: the five counts and the number of requests."""
    out = {"requests": 0, **dict.fromkeys(COUNTS, 0)}
    for r in rows:
        out["requests"] += 1
        for k in COUNTS:
            out[k] += r[k]
    return out


def bare_name(name: Any, server: str = "civ5") -> str | None:
    """`mcp__civ5__state` (Claude Code, Codex), `civ5__state` (Grok's `use_tool`) -> `state`; None for a tool
    of another server or the client's own."""
    if not isinstance(name, str):
        return None
    for prefix in (f"mcp__{server}__", f"{server}__"):
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix):]
    return None


def action_args(args: Any) -> dict[str, Any]:
    """The label-bearing arguments of a call and nothing else: short words and whole numbers."""
    if not isinstance(args, dict):
        return {}
    out = {}
    for k in ACTION_ARGS:
        v = args.get(k)
        if (isinstance(v, str) and WORD.match(v)) or (isinstance(v, int) and not isinstance(v, bool)):
            out[k] = v
    return out


def call(tool: str, args: Any = None) -> dict[str, str]:
    """A civ5 call by its bare name, as the ledger would label it: an old name reads as the new call it means."""
    as_ = classes.called_as(tool, action_args(args))
    return {"tool": as_["tool"], "action": as_.get("action") or ""}


def parsed(lines: Iterable[str]) -> Iterator[dict]:
    """The JSON objects of a JSONL stream; a line that is not one (a torn last line, a banner) is passed over."""
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if isinstance(o, dict):
            yield o


def epoch(stamp: Any) -> float | None:
    """An ISO time ("2026-11-13T22:55:48.750Z") or a number of seconds, as epoch seconds."""
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        return float(stamp)
    if isinstance(stamp, str):
        try:
            return round(datetime.fromisoformat(stamp).timestamp(), 3)
        except ValueError:
            return None
    return None
