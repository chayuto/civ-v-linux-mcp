"""Claude Code: the session transcript, `~/.claude/projects/<slug>/<session>.jsonl`.

Every `assistant` row carries `message.usage` and a `requestId`. One request is written once per content block
(a thought, a text, each tool call), each row with the same usage: a request is counted once, by its id, and the
tool calls of its rows are gathered. `input_tokens` is the part read at full price; the cached part is beside it
(`cache_read_input_tokens`, `cache_creation_input_tokens`), not inside it. `thinking_tokens` is inside
`output_tokens`. Read off Claude Code 2.1.319 (2026-11-13).

The client's own total is the `cost-state` row it writes when a session ends (`session_total`).
"""
from __future__ import annotations

from typing import Any, Iterable

from harness.usage import rows

SOURCE = "claude-code-transcript"


def counts(u: dict) -> dict[str, int]:
    details = u.get("output_tokens_details")
    return {"new_in": u.get("input_tokens") or 0, "cache_read": u.get("cache_read_input_tokens") or 0,
            "cache_write": u.get("cache_creation_input_tokens") or 0, "out": u.get("output_tokens") or 0,
            "reasoning": (details.get("thinking_tokens") or 0) if isinstance(details, dict) else 0}


def read(lines: Iterable[str], server: str = "civ5") -> list[dict]:
    """One row per request, in the order the requests first appear."""
    by: dict[str, dict] = {}
    tool_ids: dict[str, set] = {}
    for o in rows.parsed(lines):
        m = o.get("message")
        if o.get("type") != "assistant" or not isinstance(m, dict):
            continue
        u = m.get("usage")
        key = o.get("requestId") or m.get("id")
        if not isinstance(u, dict) or key is None or m.get("model") == "<synthetic>":
            continue                              # a message the client wrote itself (an interrupt notice): no request
        version = o.get("version")
        r = by.get(key)
        if r is None:
            r = by[key] = rows.row(t=None, client=f"claude-code/{version}" if version else "claude-code",
                                   model=m.get("model"), session=o.get("sessionId"), request=key,
                                   counts={}, source=SOURCE)
            tool_ids[key] = set()
        r.update(counts(u))                       # the same on every row of a request; the last one stands
        t = rows.epoch(o.get("timestamp"))
        if t is not None and (r["t"] is None or t > r["t"]):
            r["t"] = t
        content = m.get("content")
        for block in content if isinstance(content, list) else ():
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            bare = rows.bare_name(block.get("name"), server)
            if bare is None or block.get("id") in tool_ids[key]:
                continue
            tool_ids[key].add(block.get("id"))
            r["calls"].append(rows.call(bare, block.get("input")))
    return list(by.values())


def session_total(lines: Iterable[str]) -> dict[str, dict[str, int]]:
    """What the client itself says the session cost, per model, from its last `cost-state` row; {} when the
    session has not written one (it is still open, or it crashed). `inputTokens` there is the full-price part."""
    return _model_usage(lines, "cost-state")


def stream_total(lines: Iterable[str]) -> dict[str, dict[str, int]]:
    """The same total from a `claude -p --output-format stream-json` stream (what the seat loop keeps): the
    `modelUsage` of its last row, `result`; {} for a stream cut off before it. The stream is no source of rows:
    an `assistant` row there carries the usage of the request's first frame, so its output count is short (24
    where the transcript, written when the request is complete, says 33). The loop keeps the transcript."""
    return _model_usage(lines, "result")


def _model_usage(lines: Iterable[str], kind: str) -> dict[str, dict[str, int]]:
    last: Any = None
    for o in rows.parsed(lines):
        if o.get("type") == kind and isinstance(o.get("modelUsage"), dict):
            last = o["modelUsage"]
    out = {}
    for model, u in (last or {}).items():
        if isinstance(u, dict):
            out[model] = {"new_in": u.get("inputTokens") or 0, "cache_read": u.get("cacheReadInputTokens") or 0,
                          "cache_write": u.get("cacheCreationInputTokens") or 0, "out": u.get("outputTokens") or 0,
                          "reasoning": u.get("thinkingTokens") or 0}
    return out
