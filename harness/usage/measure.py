"""What grows in a session (docs/TOKEN_ACCOUNTING.md stage 5, GitLab #188).

A model request reads its whole context again, so a session's cost is the area under its context curve. Three
questions are answered from one session's placed rows (`report.place`), all by subtraction, none by a tokenizer:

    requests(placed)    the curve: per request its `context` (everything it read) and what the context `grew`
                        by before the next request. `brought` is that growth less the request's own output:
                        the replies to its calls, as the model was charged for them. A request after which the
                        context is smaller is a `reset` (the client compacted) and brought nothing countable.
    turns(placed, t)    per turn of the session in order of play: `nth`, the game `turn`, the context at its
                        `first` and `last` request, and the tally of its requests (`report.tally`)
    labels(placed)      per `(tool, action)`: how many calls, the tokens their replies brought and the bytes the
                        ledger recorded for them. A request's `brought` is shared among its calls by reply
                        bytes (equally where the ledger lacks one); a request with no civ5 call is `NO_CALL`
                        (a thought, the client's own tools, a user's message).
    halves(turns, f)    one session of 2h turns against two sessions of h: `one` is what was spent, `two` is
                        twice the first h turns with the fixed part paid twice. An estimate from one run; two
                        real runs of `--turns N` and `--turns N/2` are compared by `session`'s totals.

`brought` is an estimate where a client does not carry all of its output forward (thinking it drops makes the
figure too small by that much); the sums over a session are exact: context at the last request less context at
the first is everything that was added. Operator-side like the rest of the package.
"""
from __future__ import annotations

from typing import Any, Iterable

from harness.usage import report

NO_CALL = ("(no civ5 call)", "")


def requests(placed: list[dict]) -> list[dict]:
    reads = [report.read_in(p) for p in placed]
    out = []
    for i, p in enumerate(placed):
        grew = reads[i + 1] - reads[i] if i + 1 < len(placed) else None
        reset = grew is not None and grew < 0
        out.append({"n": i + 1, "where": p["where"], "group": p["group"], "turn": p["turn"], "context": reads[i],
                    "out": p["out"], "grew": grew, "reset": reset,
                    "brought": None if grew is None or reset else grew - p["out"]})
    return out


def turns(placed: list[dict], table: dict) -> list[dict]:
    """One row per game turn that has a request, in order of play. The ledger's turn groups are game turns
    since 2026-11-16 (`call_ledger.turn_groups`); groups that follow one another with the same turn number are
    still read as one turn here (a ledger whose rows carry no turn splits at every wait that succeeded), and the
    same number met again later is a turn played again after a reload."""
    runs: list[list[dict]] = []
    for p in sorted((p for p in placed if p["where"] == "turn"), key=lambda p: p["group"]):
        if runs and runs[-1][-1]["turn"] == p["turn"]:
            runs[-1].append(p)
        else:
            runs.append([p])
    return [{"nth": n, "turn": ps[0]["turn"], "first": report.read_in(ps[0]), "last": report.read_in(ps[-1]),
             **report.tally(ps, table)} for n, ps in enumerate(runs, 1)]


def labels(placed: list[dict]) -> list[dict]:
    """`[{"tool", "action", "calls", "tokens", "bytes"}]`, the most tokens first. `tokens` over all labels is the
    sum of `brought` over the session."""
    acc: dict[tuple[str, str], dict[str, Any]] = {}
    for p, r in zip(placed, requests(placed)):
        if r["brought"] is None:
            continue
        calls = p.get("calls") or []
        sizes = p.get("reply_bytes") or [None] * len(calls)
        if not calls:
            keys, weights = [NO_CALL], [1.0]
        elif all(sizes) and len(sizes) == len(calls):
            keys, weights = [(c["tool"], c["action"]) for c in calls], [b / sum(sizes) for b in sizes]
        else:
            keys, weights = [(c["tool"], c["action"]) for c in calls], [1 / len(calls)] * len(calls)
        for k, w, b in zip(keys, weights, sizes if calls else [None]):
            a = acc.setdefault(k, {"tool": k[0], "action": k[1], "calls": 0, "tokens": 0.0, "bytes": 0})
            a["calls"] += 1
            a["tokens"] += r["brought"] * w
            a["bytes"] += b or 0
    out = sorted(acc.values(), key=lambda a: -a["tokens"])
    for a in out:
        a["tokens"] = round(a["tokens"])
    return out


def _spent(tallies: Iterable[dict]) -> dict[str, Any]:
    tallies = list(tallies)
    out: dict[str, Any] = {"read": sum(report.read_in(t) for t in tallies), "out": sum(t["out"] for t in tallies)}
    if tallies and all("cost" in t for t in tallies):
        out["cost"] = sum(t["cost"] for t in tallies)
    return out


def halves(turn_rows: list[dict], fixed: dict | None) -> dict | None:
    """None for a session of fewer than two turns. An odd last turn is left out of both sides."""
    h = len(turn_rows) // 2
    if h < 1:
        return None
    f = [fixed] if fixed else []
    one, half = _spent(f + turn_rows[:2 * h]), _spent(f + turn_rows[:h])
    return {"turns": 2 * h, "one": one, "two": {k: 2 * v for k, v in half.items()}}


def session(s: dict, table: dict) -> dict:
    """Everything measured of one placed session (`report.place` gave it `placed`)."""
    placed = s["placed"]
    reqs = requests(placed)
    fixed = [p for p in placed if p["where"] == "fixed"]
    f = report.tally(fixed, table) if fixed else None
    ts = turns(placed, table)
    models = sorted({p["model"] or "(no model)" for p in placed})
    return {"name": s["name"], "path": s.get("path"), "kind": s["kind"], "client": s.get("label") or (placed[0]["client"] if placed else None),
            "models": models, "cycle_turns": s["head"].get("turns"), "requests": len(placed),
            "resets": sum(r["reset"] for r in reqs), "peak": max((r["context"] for r in reqs), default=0),
            "fixed": f, "turns": ts, "labels": labels(placed), "halves": halves(ts, f),
            "total": report.tally(placed, table)}


def positions(sessions: list[dict]) -> list[dict]:
    """Per turn position (the 1st, 2nd, ... turn of a session), the mean over the sessions that got that far:
    `{"nth", "sessions", "requests", "first", "read", "out"}` and `cost` where every one has it."""
    out = []
    for n in range(1, max((len(s["turns"]) for s in sessions), default=0) + 1):
        rows_ = [s["turns"][n - 1] for s in sessions if len(s["turns"]) >= n]
        k = len(rows_)
        row = {"nth": n, "sessions": k, "requests": sum(t["requests"] for t in rows_) / k,
               "first": sum(t["first"] for t in rows_) / k, "read": sum(report.read_in(t) for t in rows_) / k,
               "out": sum(t["out"] for t in rows_) / k}
        if all("cost" in t for t in rows_):
            row["cost"] = sum(t["cost"] for t in rows_) / k
        out.append(row)
    return out


def by_cycle_length(sessions: list[dict]) -> list[dict]:
    """Per length a session was asked to play (the cycle header's `turns`; None outside the seat loop): how many
    sessions, the turns they played and what they spent, `{"cycle_turns", "sessions", "turns", "requests",
    "read", "out"}` with `cost` where every session has one."""
    by: dict[Any, list[dict]] = {}
    for s in sessions:
        by.setdefault(s["cycle_turns"], []).append(s)
    out = []
    for n, ss in sorted(by.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        row = {"cycle_turns": n, "sessions": len(ss), "turns": sum(len(s["turns"]) for s in ss),
               "requests": sum(s["requests"] for s in ss), **_spent([s["total"] for s in ss])}
        out.append(row)
    return out


def merged_labels(sessions: list[dict]) -> list[dict]:
    acc: dict[tuple[str, str], dict[str, Any]] = {}
    for s in sessions:
        for a in s["labels"]:
            m = acc.setdefault((a["tool"], a["action"]), {"tool": a["tool"], "action": a["action"], "calls": 0,
                                                          "tokens": 0, "bytes": 0})
            for k in ("calls", "tokens", "bytes"):
                m[k] += a[k]
    return sorted(acc.values(), key=lambda a: -a["tokens"])
