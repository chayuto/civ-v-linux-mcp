"""Codex: the rollout, `~/.codex/sessions/<y>/<m>/<d>/rollout-<time>-<thread>.jsonl`, and the `codex exec --json`
stream the seat loop keeps (`<log-dir>/codex-c<cycle>.jsonl`).

The rollout has one `token_usage_record` per response, with a time. Its `input_tokens` *includes*
`cached_input_tokens`: 17,523 with 12,032 cached is 5,491 read at full price. `cache_write_input_tokens` has been
0 in every record seen; it is taken to be inside `input_tokens` as the cached part is. `reasoning_output_tokens`
is inside `output_tokens`. The model is on the `turn_context` row before the records it governs.

A civ5 call is an `item_completed` event whose item is a `McpToolCall`. Codex makes its calls from scripts: a
response ends in a `custom_tool_call` item (the `exec` tool), the script starts at once, and the response's usage
record is written a moment later, so a script's first calls can be on file *before* the record of the response
that wrote it (live 2026-11-13: 3 of 23 calls). A call is therefore given to the script that was the latest one
written when the call **started** (the event's time less the item's `duration`), and a script to the first record
after it. A call that outlasts its response (a long wait the model then polls with `wait`, which is a
`function_call` and issues nothing) still belongs to the response that issued it. In a file with no script row
or no times, a call goes to the record before it. Read off Codex CLI 0.166.0 (2026-11-13).

The client's own totals: `thread_total` (the rollout's running total, on its last record) and `exec_total` (the
`turn.completed` rows of the exec stream, which carries no per-request row at all).
"""
from __future__ import annotations

from typing import Any, Iterable

from harness.usage import rows

SOURCE = "codex-rollout"


def counts(u: Any) -> dict[str, int]:
    u = u if isinstance(u, dict) else {}
    cached, written = u.get("cached_input_tokens") or 0, u.get("cache_write_input_tokens") or 0
    return {"new_in": max(0, (u.get("input_tokens") or 0) - cached - written), "cache_read": cached,
            "cache_write": written, "out": u.get("output_tokens") or 0,
            "reasoning": u.get("reasoning_output_tokens") or 0}


SCRIPT = "custom_tool_call"       # the response item that runs a script; its calls start after it
EARLY = 0.05                      # seconds a call's computed start may fall before its script's row


def _seconds(d: Any) -> float:
    if isinstance(d, dict):
        return (d.get("secs") or 0) + (d.get("nanos") or 0) / 1e9
    return 0.0


def read(lines: Iterable[str], server: str = "civ5") -> list[dict]:
    """One row per response, in file order. A response id seen twice is counted once."""
    out: list[dict] = []
    by_id: dict = {}
    scripts: list[dict] = []          # {"t": when the script's row was written, "row": its response's row, "calls": [...]}
    model = session = version = None
    for o in rows.parsed(lines):
        kind, p = o.get("type"), o.get("payload")
        if not isinstance(p, dict):
            continue
        if kind == "session_meta":
            session, version = p.get("id") or p.get("session_id"), p.get("cli_version")
        elif kind == "turn_context":
            model = p.get("model") or model
        elif kind == "response_item" and p.get("type") == SCRIPT:
            t = rows.epoch(o.get("timestamp"))
            if t is not None:
                scripts.append({"t": t, "row": None, "calls": []})
        elif kind == "token_usage_record":
            rid = p.get("response_id")
            r = by_id.get(rid) if rid is not None else None
            if r is None:
                r = rows.row(t=rows.epoch(o.get("timestamp")), client=f"codex/{version}" if version else "codex",
                             model=model, session=p.get("session_id") or session, request=rid,
                             counts=counts(p.get("usage")), source=SOURCE)
                out.append(r)
                if rid is not None:
                    by_id[rid] = r
            for s in scripts:
                if s["row"] is None:                       # written since the record before: this response's script
                    s["row"] = r
                    r["calls"].extend(s.pop("calls"))
        elif kind == "event_msg" and p.get("type") == "item_completed":
            item = p.get("item")
            if not (isinstance(item, dict) and item.get("type") == "McpToolCall" and item.get("server") == server
                    and isinstance(item.get("tool"), str)):
                continue
            done = rows.epoch(o.get("timestamp"))
            started = None if done is None else done - _seconds(item.get("duration"))
            owner = None if started is None else next((s for s in reversed(scripts) if s["t"] <= started + EARLY), None)
            call = rows.call(item["tool"], item.get("arguments"))
            if owner is None:
                if out:
                    out[-1]["calls"].append(call)
            elif owner["row"] is None:
                owner["calls"].append(call)
            else:
                owner["row"]["calls"].append(call)
    return out


def thread_total(lines: Iterable[str]) -> dict[str, int] | None:
    """The rollout's own running total as of its last record; None for a rollout with no record."""
    last = None
    for o in rows.parsed(lines):
        p = o.get("payload")
        if o.get("type") == "token_usage_record" and isinstance(p, dict) and isinstance(p.get("thread_token_usage"), dict):
            last = p["thread_token_usage"]
    return counts(last) if last is not None else None


def exec_total(lines: Iterable[str]) -> dict[str, int] | None:
    """The total of a `codex exec --json` stream: its `turn.completed` rows added up; None when it has none (the
    cycle was killed before the turn ended)."""
    total = None
    for o in rows.parsed(lines):
        if o.get("type") == "turn.completed" and isinstance(o.get("usage"), dict):
            c = counts(o["usage"])
            total = c if total is None else {k: total[k] + c[k] for k in c}
    return total
