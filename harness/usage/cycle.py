"""One cycle of the seat loop (`scripts/llm_seat_loop.py`), read from the log directory alone (#185).

The loop keeps `<agent>-c<cycle>.jsonl`, the CLI's stream, with every line stamped on arrival (`t`) between two
rows of its own: `seat_loop.cycle` (agent, model, effort, seat, cycle, turns, start, client, session) and
`seat_loop.cycle_end` (start, end, rc, killed, session, usage_file). Where the stream is not the client's
per-request record, the loop copies that record beside it when the cycle ends and names it in `usage_file`:

    grok    the stream itself (the stamps are its only times)
    codex   <agent>-c<cycle>.rollout.jsonl      the exec stream has one total and no request
    claude  <agent>-c<cycle>.transcript.jsonl   the stream's assistant rows carry the usage of the request's
                                                first frame (output 24 where the finished request wrote 33)

`read` gives the cycle's header and its usage rows, each with the header's `seat`, `cycle` and `label` (the
client label the call ledger writes, `<agent>/<model>`, which is what the join matches on). `own_total` is what
the client itself says the cycle cost, from the stream's last row, to hold the rows against.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from harness.usage import claude_code, codex, grok, rows

CYCLE, CYCLE_END = "seat_loop.cycle", "seat_loop.cycle_end"
NAME = re.compile(r"(?P<agent>[a-z]+)-c(?P<cycle>\d+)\.jsonl\Z")


def header(lines: Iterable[str]) -> dict:
    """The loop's two rows as one dict; {} for a stream from before the loop wrote them. A stream that holds a
    cycle number run twice gives the last run."""
    head: dict = {}
    for o in rows.parsed(lines):
        if o.get("type") == CYCLE:
            head = {k: v for k, v in o.items() if k not in ("type", "t")}
        elif o.get("type") == CYCLE_END and head:
            head.update({k: v for k, v in o.items() if k not in ("type", "t") and v is not None})
    return head


def _lines(path: Path) -> list[str]:
    with path.open(errors="replace") as fh:
        return fh.readlines()


def read(stream: Path | str, server: str = "civ5") -> tuple[dict, list[dict]]:
    """(header, usage rows) of one cycle. A stream with no header is read by its file name (`grok-c12.jsonl`);
    a codex or claude cycle whose record was not kept has no rows, and its header has no `usage_file`."""
    stream = Path(stream)
    lines = _lines(stream)
    head = header(lines)
    named = NAME.match(stream.name)
    agent = head.get("agent") or (named.group("agent") if named else None)
    if "cycle" not in head and named:
        head["cycle"] = int(named.group("cycle"))
    if agent:
        head.setdefault("agent", agent)
    kept = stream.with_name(head["usage_file"]) if head.get("usage_file") else None
    if agent == "grok":
        out = grok.read(lines, server)
    elif agent in ("codex", "claude") and kept is not None and kept.is_file():
        out = (codex if agent == "codex" else claude_code).read(_lines(kept), server)
    else:
        out = []
    for r in out:
        r["model"] = r["model"] or head.get("model")          # a grok cycle cut off before `end` names none
        r["seat"], r["cycle"], r["label"] = head.get("seat"), head.get("cycle"), head.get("client")
    return head, out


def own_total(stream: Path | str) -> dict[str, int] | None:
    """The client's own total for the cycle, from its stream; None when the stream never reached it (a killed
    cycle) or the agent is not known."""
    stream = Path(stream)
    lines = _lines(stream)
    named = NAME.match(stream.name)
    agent = header(lines).get("agent") or (named.group("agent") if named else None)
    if agent == "grok":
        return grok.total(lines)
    if agent == "codex":
        return codex.exec_total(lines)
    if agent == "claude":
        per_model = claude_code.stream_total(lines)
        if not per_model:
            return None
        return {k: sum(u[k] for u in per_model.values()) for k in rows.COUNTS}
    return None
