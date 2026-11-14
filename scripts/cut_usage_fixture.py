#!/usr/bin/env python3
"""Cut a client's usage file down to numbers, for a test fixture (docs/TOKEN_ACCOUNTING.md stage 0, GitLab #183).

A transcript holds everything a model was told and everything it said. A fixture holds none of it: this script
builds each kept row anew from a short list of fields -- counts, times, a model name, a civ5 tool name and the
arguments its action label is read from (`harness.usage.rows.ACTION_ARGS`) -- and writes nothing else. Session,
request, message and tool-call ids are replaced by counters (`session-1`, `request-7`). Rows that carry no usage
and no civ5 call are dropped; a call to another server or to one of the client's own tools is dropped with them.

Before it writes, the script reads the original and the cut with the same reader and refuses unless the rows are
equal (ids aside): a fixture is exactly as good a test of the reader as the file it came from.

    .venv/bin/python scripts/cut_usage_fixture.py claude-code ~/.claude/projects/<slug>/<session>.jsonl \\
        tests/fixtures/usage/claude-code-transcript.jsonl
    .venv/bin/python scripts/cut_usage_fixture.py codex-rollout ~/.codex/sessions/.../rollout-....jsonl OUT
    .venv/bin/python scripts/cut_usage_fixture.py codex-exec logs/night/codex-c41.jsonl OUT
    .venv/bin/python scripts/cut_usage_fixture.py grok logs/night/grok-c1.jsonl OUT
    .venv/bin/python scripts/cut_usage_fixture.py claude-stream <log-dir>/claude-c1.jsonl OUT
    .venv/bin/python scripts/cut_usage_fixture.py ledger logs/calls.jsonl OUT --client codex/gpt-6.1-sol \
        --since 1794631925 --until 1794632062

A seat-loop stream (grok, codex-exec, claude-stream) keeps the loop's two rows, `seat_loop.cycle` and
`seat_loop.cycle_end`. The ledger cut (#186, for the join's tests) keeps the rows of the named `--client` labels
inside the time window and of each row its time, seat, label, kind, sizes, `ok` and turn: no arguments, no
excerpt, no refusal text.

Re-run it when a client changes its format; `tests/test_usage_fixtures.py` fails if a fixture ever carries a key
or a string this script would not have written.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.usage import claude_code, codex, cycle, grok, rows

SERVER = "civ5"


class Ids:
    """Every id of a file becomes `<kind>-<n>`, the same id the same counter."""

    def __init__(self) -> None:
        self.seen: dict[tuple[str, str], str] = {}
        self.count: dict[str, int] = {}

    def __call__(self, kind: str, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        key = (kind, value)
        if key not in self.seen:
            self.count[kind] = self.count.get(kind, 0) + 1
            self.seen[key] = f"{kind}-{self.count[kind]}"
        return self.seen[key]


def pick(d: Any, keys: tuple[str, ...]) -> dict:
    """The whole-number fields of `d` among `keys`."""
    d = d if isinstance(d, dict) else {}
    return {k: d[k] for k in keys if isinstance(d.get(k), int) and not isinstance(d[k], bool)}


def word(v: Any) -> str | None:
    return v if isinstance(v, str) and rows.WORD.match(v) else None


CLAUDE_USAGE = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
CLAUDE_TOTAL = ("inputTokens", "outputTokens", "thinkingTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
CODEX_USAGE = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens",
               "reasoning_output_tokens", "total_tokens")
GROK_USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens",
              "reasoning_tokens", "total_tokens")
GROK_TOTAL = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls")


def number(v: Any) -> int | float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


LOOP_NUMBERS = ("t", "seat", "cycle", "turns", "start", "end", "rc")
LOOP_WORDS = ("agent", "model", "effort", "client", "usage_file")


def loop_row(o: dict, ids: Ids) -> dict | None:
    """The seat loop's own rows (`seat_loop.cycle`, `seat_loop.cycle_end`), field by field; None for any other."""
    if o.get("type") not in (cycle.CYCLE, cycle.CYCLE_END):
        return None
    out: dict = {"type": o["type"]}
    out.update({k: o[k] for k in LOOP_NUMBERS if number(o.get(k)) is not None})
    out.update({k: o[k] for k in LOOP_WORDS if word(o.get(k))})
    if isinstance(o.get("session"), str):
        out["session"] = ids("session", o["session"])
    return out


def cut_claude(objs: Iterator[dict], ids: Ids) -> Iterator[dict]:
    for o in objs:
        m = o.get("message")
        if o.get("type") == "assistant" and isinstance(m, dict) and isinstance(m.get("usage"), dict):
            u = pick(m["usage"], CLAUDE_USAGE)
            details = pick(m["usage"].get("output_tokens_details"), ("thinking_tokens",))
            if details:
                u["output_tokens_details"] = details
            content = []
            for block in m.get("content") if isinstance(m.get("content"), list) else ():
                if not isinstance(block, dict) or block.get("type") != "tool_use" \
                        or rows.bare_name(block.get("name"), SERVER) is None or not word(block.get("name")):
                    continue
                content.append({"type": "tool_use", "id": ids("tool", block.get("id")), "name": block["name"],
                                "input": rows.action_args(block.get("input"))})
            yield {"type": "assistant", "requestId": ids("request", o.get("requestId")),
                   "sessionId": ids("session", o.get("sessionId")), "timestamp": word(o.get("timestamp")),
                   "version": word(o.get("version")),
                   "message": {"id": ids("message", m.get("id")), "model": word(m.get("model")), "usage": u,
                               "content": content}}
        elif o.get("type") == "cost-state" and isinstance(o.get("modelUsage"), dict):
            yield {"type": "cost-state", "sessionId": ids("session", o.get("sessionId")),
                   "modelUsage": {model: pick(u, CLAUDE_TOTAL) for model, u in o["modelUsage"].items() if word(model)}}


def cut_claude_stream(objs: Iterator[dict], ids: Ids) -> Iterator[dict]:
    """The `claude -p` stream the seat loop keeps: the loop's rows and the total on `result`. Its `assistant`
    rows are no source of usage (the first frame's counts) and are left behind with everything else."""
    for o in objs:
        if (own := loop_row(o, ids)) is not None:
            yield own
        elif o.get("type") == "result" and isinstance(o.get("modelUsage"), dict):
            t = {"t": o["t"]} if number(o.get("t")) is not None else {}
            yield {"type": "result", **t,
                   "modelUsage": {model: pick(u, CLAUDE_TOTAL) for model, u in o["modelUsage"].items() if word(model)}}


def cut_codex_rollout(objs: Iterator[dict], ids: Ids) -> Iterator[dict]:
    for o in objs:
        kind, p = o.get("type"), o.get("payload")
        if not isinstance(p, dict):
            continue
        head = {"timestamp": word(o.get("timestamp")), "type": kind}
        if kind == "session_meta":
            yield {**head, "payload": {"id": ids("session", p.get("id") or p.get("session_id")),
                                       "cli_version": word(p.get("cli_version")), "originator": word(p.get("originator"))}}
        elif kind == "turn_context":
            yield {**head, "payload": {"model": word(p.get("model"))}}
        elif kind == "token_usage_record":
            yield {**head, "payload": {"session_id": ids("session", p.get("session_id")),
                                       "response_id": ids("request", p.get("response_id")),
                                       "usage": pick(p.get("usage"), CODEX_USAGE),
                                       "thread_token_usage": pick(p.get("thread_token_usage"), CODEX_USAGE)}}
        elif kind == "response_item" and p.get("type") == codex.SCRIPT:
            yield {**head, "payload": {"type": codex.SCRIPT}}        # when a script was written, and nothing of it
        elif kind == "event_msg" and p.get("type") == "item_completed":
            item = p.get("item")
            if isinstance(item, dict) and item.get("type") == "McpToolCall" and item.get("server") == SERVER \
                    and word(item.get("tool")):
                yield {**head, "payload": {"type": "item_completed",
                                           "item": {"type": "McpToolCall", "server": SERVER, "tool": item["tool"],
                                                    "arguments": rows.action_args(item.get("arguments")),
                                                    "duration": pick(item.get("duration"), ("secs", "nanos"))}}}


def cut_codex_exec(objs: Iterator[dict], ids: Ids) -> Iterator[dict]:
    for o in objs:
        kind, item = o.get("type"), o.get("item")
        if (own := loop_row(o, ids)) is not None:
            yield own
        elif kind == "thread.started":
            yield {"type": kind, "thread_id": ids("session", o.get("thread_id"))}
        elif kind == "turn.completed" and isinstance(o.get("usage"), dict):
            yield {"type": kind, "usage": pick(o["usage"], CODEX_USAGE)}
        elif kind == "item.completed" and isinstance(item, dict) and item.get("type") == "mcp_tool_call" \
                and item.get("server") == SERVER and word(item.get("tool")):
            yield {"type": kind, "item": {"type": "mcp_tool_call", "server": SERVER, "tool": item["tool"],
                                          "arguments": rows.action_args(item.get("arguments")),
                                          "status": word(item.get("status"))}}


def cut_grok(objs: Iterator[dict], ids: Ids) -> Iterator[dict]:
    for o in objs:
        kind = o.get("type")
        t = {"t": o["t"]} if isinstance(o.get("t"), (int, float)) else {}
        if (own := loop_row(o, ids)) is not None:
            yield own
        elif kind == "usage" and isinstance(o.get("usage"), dict):
            yield {"type": kind, **t, "usage": pick(o["usage"], GROK_USAGE)}
        elif kind == "tool_call":
            raw = o.get("rawInput") if isinstance(o.get("rawInput"), dict) else {}
            if o.get("toolName") == "use_tool" and rows.bare_name(raw.get("tool_name"), SERVER) and word(raw.get("tool_name")):
                yield {"type": kind, **t, "toolName": "use_tool",
                       "rawInput": {"tool_name": raw["tool_name"], "tool_input": rows.action_args(raw.get("tool_input"))}}
            elif rows.bare_name(o.get("toolName"), SERVER) and word(o.get("toolName")):
                yield {"type": kind, **t, "toolName": o["toolName"], "rawInput": rows.action_args(raw)}
        elif kind == "end":
            used = o.get("modelUsage") if isinstance(o.get("modelUsage"), dict) else {}
            yield {"type": kind, **t, "sessionId": ids("session", o.get("sessionId")),
                   "usage": pick(o.get("usage"), GROK_USAGE),
                   "modelUsage": {model: pick(u, GROK_TOTAL) for model, u in used.items() if word(model)}}


LEDGER_NUMBERS = ("t", "seat", "bytes", "seconds", "trips", "turn")
LEDGER_WORDS = ("tool", "action", "called", "kind", "client")
LEDGER_FLAGS = ("ok", "turn_inferred")


def cut_ledger(objs: Iterator[dict], ids: Ids) -> Iterator[dict]:
    """A call ledger row without its words: no `args`, no `excerpt`, no `err`, nothing the attention added."""
    for o in objs:
        if number(o.get("t")) is None or not word(o.get("tool")) or not word(o.get("kind")):
            continue
        out = {k: o[k] for k in LEDGER_NUMBERS if number(o.get(k)) is not None}
        out.update({k: o[k] for k in LEDGER_WORDS if word(o.get(k))})
        out.update({k: o[k] for k in LEDGER_FLAGS if isinstance(o.get(k), bool)})
        yield out


def ledger_rows(lines: list[str]) -> list[Any]:
    """What the join reads of a ledger row."""
    keys = ("t", "seat", "tool", "action", "kind", "seconds", "ok", "turn", "client")
    return [{k: o.get(k) for k in keys} for o in rows.parsed(lines)]


def loop_head(lines: list[str]) -> dict:
    """The cycle header a stream reads to, less the session id (the cut renumbers it)."""
    return {k: v for k, v in cycle.header(lines).items() if k not in ("session", "killed")}


def exec_rows(lines: list[str]) -> list[Any]:
    """The exec stream has no per-request row: what a cut must keep is its total and its civ5 calls, in order."""
    calls = [rows.call(o["item"]["tool"], o["item"].get("arguments")) for o in rows.parsed(lines)
             if o.get("type") == "item.completed" and isinstance(o.get("item"), dict)
             and o["item"].get("type") == "mcp_tool_call" and o["item"].get("server") == SERVER]
    return [codex.exec_total(lines), calls, loop_head(lines)]


SOURCES: dict[str, tuple[Callable, Callable]] = {
    "claude-code": (cut_claude, lambda lines: [claude_code.read(lines), claude_code.session_total(lines)]),
    "claude-stream": (cut_claude_stream, lambda lines: [claude_code.stream_total(lines), loop_head(lines)]),
    "ledger": (cut_ledger, ledger_rows),
    "codex-rollout": (cut_codex_rollout, lambda lines: [codex.read(lines), codex.thread_total(lines)]),
    "codex-exec": (cut_codex_exec, exec_rows),
    "grok": (cut_grok, lambda lines: [grok.read(lines), grok.total(lines), loop_head(lines)]),
}


def renamed(value: Any, ids: Ids) -> Any:
    """`value` with every session and request id of a usage row replaced as the cut replaced it."""
    if isinstance(value, list):
        return [renamed(v, ids) for v in value]
    if isinstance(value, dict) and "request" in value and "session" in value:
        return {**value, "session": ids("session", value["session"]),
                "request": ids("request", value["request"]) if value["source"] != grok.SOURCE else value["request"]}
    return value


def cut(source: str, lines: list[str]) -> list[str]:
    """The cut lines of `lines`; SystemExit when the cut does not read as the original does."""
    cutter, reader = SOURCES[source]
    ids = Ids()
    out = [json.dumps(o, separators=(",", ":")) for o in cutter(rows.parsed(lines), ids)]
    before, after = renamed(reader(lines), ids), reader(out)
    if before != after:
        raise SystemExit(f"cut_usage_fixture: the cut reads differently from the original ({source}); not written")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--client", action="append", help="ledger: keep the rows under this label (repeatable)")
    ap.add_argument("--since", type=float, help="ledger: keep rows written at or after this epoch second")
    ap.add_argument("--until", type=float, help="ledger: keep rows written at or before this epoch second")
    args = ap.parse_args()
    with open(args.infile, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if args.source == "ledger":
        lines = [json.dumps(o) for o in rows.parsed(lines)
                 if (not args.client or o.get("client") in args.client)
                 and (args.since is None or (number(o.get("t")) or 0) >= args.since)
                 and (args.until is None or (number(o.get("t")) or 0) <= args.until)]
    out = cut(args.source, lines)
    Path(args.outfile).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{args.outfile}: {len(out)} rows from {len(lines)} lines, {sum(len(x) + 1 for x in out)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
