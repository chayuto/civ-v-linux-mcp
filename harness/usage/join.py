"""The join: which game turn a model request belongs to (docs/TOKEN_ACCOUNTING.md stage 3, GitLab #186).

Two files of one client meet here: its usage rows (`harness.usage.rows`, one per model request, each naming the
civ5 calls it issued) and its rows of the call ledger (`harness.call_ledger`, one per call, each with the seat,
the game turn and the time). Neither file knows of the other. A usage call and a ledger row are the same call
when they carry the same `(tool, action)` label, in the same order, at times that agree.

    ledger = join.ledger_of(all_ledger_rows, "codex/gpt-6.1-sol", start, end)     # one client, one stretch of time
    placed, groups = join.place(usage_rows, ledger)
    join.per_turn(placed)          # one sum per turn, plus `fixed` and `unplaced`; together the session's total

The ledger rows are grouped into turns per seat exactly as the ledger report groups them
(`call_ledger.turn_groups`). Then every request lands in exactly one place (`where`):

    turn      the turn of the first call it issued (a script that ends turn 242 and goes on to read turn 243 was
              written during 242); a request that issued no call takes the turn of the last call before it
    fixed     it came before the session's first call: the system prompt, the tool listing, the first thought
    unplaced  it issued calls and the ledger holds none of them, and nothing before it was placed either (the
              ledger does not cover this session)

Nothing is dropped and nothing counted twice, so the sums of `per_turn` are the session's total (rule 4).
Operator-side like the rest of the package: nothing here reaches a seat.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from harness import call_ledger
from harness.surface import classes
from harness.surface import vocabulary
from harness.usage import codex, cycle, rows

TOOLS = frozenset(vocabulary.TOOLS)

# Seconds two clocks may disagree by. A request's time is when its response was complete, and its calls start
# after that; Codex writes the record a moment after the script's first call has started (0.1 to 0.2 s seen).
SLACK = 5.0


def started(ledger_row: dict) -> float:
    """When a ledger row's call began: the row is written when the call ends."""
    return ledger_row["t"] - (ledger_row.get("seconds") or 0)


def label(call: dict) -> tuple[str, str]:
    """What a usage call and a ledger row are compared by: `(tool, action)` in today's nine-tool vocabulary. A
    usage call is already in it (`rows.call`). A ledger row keeps the vocabulary of the day it was written
    (`inspect` for `state`, `finish_turn` for `turn` / `finish`), so its tool is read as the call it means now;
    a ledger row of `batch` has no action at all."""
    tool, action = str(call.get("tool")), call.get("action") or ""
    if tool not in TOOLS:
        now = classes.called_as(tool, {})
        tool, action = now["tool"], action or now.get("action") or ""
    return tool, action


def ledger_of(ledger: Iterable[dict], client: str | None, start: float | None = None, end: float | None = None,
              seat: Any = None) -> list[dict]:
    """The ledger rows one session can have made: the rows under its `client` label whose call ran inside
    [start, end] (a bound that is None is open), on `seat` when one is given. In the order given."""
    out = []
    for r in ledger:
        if r.get("client") != client or (seat is not None and r.get("seat") != seat):
            continue
        if (start is not None and r["t"] < start - SLACK) or (end is not None and started(r) > end + SLACK):
            continue
        out.append(r)
    return out


def turn_groups(ledger: list[dict]) -> tuple[list[dict], dict[int, int]]:
    """(`[{"seat", "turn", "open", "rows"}]` in order of their first call, {id(ledger row): its group's index}).
    Each seat's rows are grouped on their own: two seats of one client are two games' worth of turns."""
    by_seat: dict[Any, list[dict]] = {}
    for r in ledger:
        by_seat.setdefault(r.get("seat"), []).append(r)
    groups = [{"seat": seat, **g} for seat, rs in by_seat.items() for g in call_ledger.turn_groups(rs)]
    groups.sort(key=lambda g: min(started(r) for r in g["rows"]))
    return groups, {id(r): i for i, g in enumerate(groups) for r in g["rows"]}


def match(usage: list[dict], ledger: list[dict]) -> list[list[dict | None]]:
    """For every usage row, the ledger row of each of its calls (None for a call the ledger does not hold: a
    tool name that does not exist never reached the server).

    A call takes the earliest ledger row not yet taken that has its label and did not start before its request
    was complete, nor after the next request was (its reply is what the next request read). Codex is spared the
    second bound: a script outlives its response while the model polls. Calls of one request may sit in the
    ledger in any order (they ran side by side); the calls of a later request never come before the earliest
    call of the request before. Rows without a time (a Grok stream nobody stamped) are matched by order alone."""
    order = sorted(ledger, key=started)
    taken = [False] * len(order)
    times = [r.get("t") for r in usage]
    out: list[list[dict | None]] = []
    floor = 0
    for i, r in enumerate(usage):
        lo = None if times[i] is None else times[i] - SLACK
        later = None if r.get("source") == codex.SOURCE else next((t for t in times[i + 1:] if t is not None), None)
        hi = None if later is None else later + SLACK
        got: list[dict | None] = []
        found: list[int] = []
        for c in r.get("calls") or ():
            want, hit = label(c), None
            for j in range(floor, len(order)):
                at = started(order[j])
                if hi is not None and at > hi:
                    break
                if taken[j] or label(order[j]) != want or (lo is not None and at < lo):
                    continue
                hit = j
                break
            if hit is None:
                got.append(None)
            else:
                taken[hit] = True
                found.append(hit)
                got.append(order[hit])
        if found:
            floor = min(found)
        out.append(got)
    return out


def place(usage: list[dict], ledger: list[dict]) -> tuple[list[dict], list[dict]]:
    """(the usage rows, placed; the turn groups of the ledger). `usage` is one session's rows in order, `ledger`
    that client's ledger rows (`ledger_of`). A placed row is a copy with `where` ("turn", "fixed", "unplaced"),
    `group` (the index of its turn group, None outside a turn), `turn`, `seat` (the group's; otherwise what the
    row had), `matched` (how many of its calls the ledger holds) and `reply_bytes` (per call, the size of the
    reply the ledger recorded; None for a call it does not hold)."""
    groups, group_of = turn_groups(ledger)
    placed = []
    last: int | None = None
    called = False
    for r, hits in zip(usage, match(usage, ledger)):
        mine = [group_of[id(h)] for h in hits if h is not None]
        called = called or bool(hits)
        if mine:
            g: int | None = mine[0]
            last = mine[-1]
        else:
            g = last
        p = {**r, "where": "turn" if g is not None else "unplaced" if called else "fixed", "group": g,
             "turn": groups[g]["turn"] if g is not None else None, "matched": len(mine),
             "reply_bytes": [None if h is None else h.get("bytes") or 0 for h in hits]}
        p["seat"] = groups[g]["seat"] if g is not None else r.get("seat")
        placed.append(p)
    return placed, groups


def per_turn(placed: Iterable[dict]) -> list[dict]:
    """The sums the report prints: `fixed` first, then one row per turn group that has a request, in group order,
    then `unplaced`; each `{"where", "group", "seat", "turn", "requests", <the five counts>}`. A group number
    is one stretch of play: a turn played again after a reload is another group with the same `turn`."""
    by: dict[Any, list[dict]] = {}
    for p in placed:
        by.setdefault(p["group"] if p["where"] == "turn" else p["where"], []).append(p)
    keys = [k for k in ("fixed",) if k in by] + sorted(k for k in by if isinstance(k, int)) + \
           [k for k in ("unplaced",) if k in by]
    out = []
    for k in keys:
        first = by[k][0]
        turn = isinstance(k, int)
        out.append({"where": first["where"], "group": k if turn else None, "seat": first["seat"] if turn else None,
                    "turn": first["turn"], **rows.total(by[k])})
    return out


def place_cycle(stream: Path | str, ledger: Iterable[dict]) -> tuple[dict, list[dict], list[dict]]:
    """(header, placed rows, turn groups) of one seat-loop cycle (`cycle.read`): its ledger rows are the ones
    under the header's `client` label between the cycle's start and end. A stream from before the loop wrote a
    header has no label, so every request is `fixed` or `unplaced`."""
    head, usage = cycle.read(stream)
    mine = ledger_of(ledger, head["client"], head.get("start"), head.get("end")) if head.get("client") else []
    placed, groups = place(usage, mine)
    return head, placed, groups
