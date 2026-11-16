"""The usage half of the ledger report (docs/TOKEN_ACCOUNTING.md stage 4, GitLab #187).

`scripts/ledger_report.py --usage <file or dir>` hands the paths here. What they may hold:

    <agent>-c<n>.jsonl      a seat-loop cycle (`cycle.read`: the stream, or the record the loop kept beside it)
    rollout-*.jsonl         a Codex session            anything else that one of the three readers takes rows
    <session>.jsonl         a Claude Code transcript    from is a session of that client; other files are passed over

A directory is read with everything under it. A Codex cycle from before the loop kept its record finds its
rollout by thread id among the files given, so `--usage logs/night --usage ~/.codex/sessions` reads the old
night cycles per request. A session that is no cycle and made no civ5 call is not a game session and is left
out (a transcript directory holds every coding session too).

    sessions = report.read(paths)                       # rows and the client's own total, per session
    report.place(sessions, ledger_rows)                 # `join.place` against each session's stretch of ledger
    summary = report.summary(sessions, groups, table)   # per report turn, fixed, unplaced, per client, total

Every request of every session is in exactly one of the per-turn sums, `fixed` or `unplaced`, so they add up
to `total` (rule 4), and `total` is the rows of all sessions. Where a client's own total says more than its
rows hold (Claude Code answers some requests without keeping a row), the session carries the difference as
`short_by`: printed on its own line, never folded into a sum. Cost is `prices.of`: None where a model has no
list price. Operator-side like the rest of the package.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from harness.usage import claude_code, codex, cycle, grok, join, prices, rows

# Seconds after a session's last request in which its calls may still start, for a session with no end time
# of its own: the last response's script runs on, and a wait for the turn can take minutes.
AFTER = 900.0


def files(paths: Iterable[Path | str]) -> list[Path]:
    """The paths given, a directory replaced by every `.jsonl` under it."""
    out: list[Path] = []
    for p in map(Path, paths):
        out += sorted(q for q in p.rglob("*.jsonl") if q.is_file()) if p.is_dir() else [p]
    return out


def _own_claude(lines: list[str]) -> dict[str, int] | None:
    per_model = claude_code.session_total(lines)
    return {k: sum(u[k] for u in per_model.values()) for k in rows.COUNTS} if per_model else None


READERS = ((claude_code, _own_claude), (codex, codex.thread_total), (grok, grok.total))


def read(paths: Iterable[Path | str], server: str = "civ5") -> tuple[list[dict], int]:
    """(sessions, files left out). A session is `{"name", "path", "kind": "cycle" | "session", "head",
    "usage", "own"}`: the cycle's header ({} for a bare session), its usage rows and the client's own total
    (None where the file holds none). Left out: a file no reader takes a row from, and a bare session with no
    civ5 call. The client's own file of a session a cycle already gave is passed over without being counted
    as left out: it is that cycle again."""
    pool = files(paths)

    def find(agent: str, session: str | None) -> Path | None:
        hits = [p for p in pool if session and (p.stem == session or p.name.endswith(f"-{session}.jsonl"))]
        return hits[-1] if hits else None

    out, used, skipped = [], set(), 0
    streams = [p for p in pool if cycle.NAME.match(p.name)]
    for p in streams:
        head, usage = cycle.read(p, server, find)
        used.add(p)
        if head.get("usage_path"):
            used.add(Path(head["usage_path"]))
        out.append({"name": p.name, "path": str(p), "kind": "cycle", "head": head, "usage": usage,
                    "own": cycle.own_total(p)})
    # A cycle's record is a copy the loop kept; the client's own file of the same session may be among the
    # paths too (the live record a running cycle is read from, `--usage logs/night --usage ~/.codex/sessions`).
    # It is the same requests, so it is not a second session.
    in_cycles = {(r["source"], r["session"]) for s in out for r in s["usage"] if r.get("session")}
    for p in pool:
        if p in used:
            continue
        with p.open(errors="replace") as fh:
            lines = fh.readlines()
        usage, total = [], None
        for reader, own in READERS:
            usage = reader.read(lines, server)
            if usage:
                total = own(lines)
                break
        if not any(r["calls"] for r in usage):
            skipped += 1
            continue
        if all((r["source"], r.get("session")) in in_cycles for r in usage):
            continue
        out.append({"name": p.name, "path": str(p), "kind": "session", "head": {}, "usage": usage, "own": total})
    return out, skipped


def span(session: dict) -> tuple[float | None, float | None]:
    """(start, end) of the stretch of ledger a session's calls can be in: the cycle header's times, else
    from its first request to `AFTER` its last. (None, None) for rows without a time."""
    head = session["head"]
    ts = [r["t"] for r in session["usage"] if r.get("t") is not None]
    start = head.get("start") or (min(ts) if ts else None)
    end = head.get("end") or (max(ts) + AFTER if ts else None)
    return start, end


def guess_label(usage: list[dict], ledger: list[dict], start: float, end: float) -> str | None:
    """The ledger's client label a session with no header played under: the one whose rows in the session's
    stretch match the most of its calls. None when no label matches any."""
    best, most = None, 0
    for lab in sorted({r["client"] for r in ledger if r.get("client")}):
        mine = join.ledger_of(ledger, lab, start, end)
        if not mine:
            continue
        n = sum(p["matched"] for p in join.place(usage, mine)[0])
        if n > most:
            best, most = lab, n
    return best


def place(sessions: list[dict], ledger: list[dict]) -> None:
    """Give every session `label` (the header's, else guessed), `placed` and `groups` (`join.place`). A
    session with neither a time nor a header meets no ledger row: its requests are `fixed` or `unplaced`."""
    for s in sessions:
        start, end = span(s)
        label = s["head"].get("client")
        if label is None and start is not None:
            label = guess_label(s["usage"], ledger, start, end)
        mine = join.ledger_of(ledger, label, start, end) if label and start is not None else []
        s["label"] = label
        s["placed"], s["groups"] = join.place(s["usage"], mine)


def tally(usage: Iterable[dict], table: dict) -> dict[str, Any]:
    """`rows.total` of the rows with their `cost`; the key is absent where `prices.of` knows none."""
    usage = list(usage)
    out: dict[str, Any] = rows.total(usage)
    c = prices.of(usage, table)
    if c is not None:
        out["cost"] = c
    return out


def read_in(t: dict) -> int:
    """Everything the model read: new input, cache reads and cache writes."""
    return t["new_in"] + t["cache_read"] + t["cache_write"]


def short_by(session: dict) -> dict[str, int] | None:
    """What the client's own total holds beyond the session's rows, per count that differs (negative where
    the rows hold more); {} when they agree, None when the client states no total."""
    own = session["own"]
    if own is None:
        return None
    mine = rows.total(session["usage"])
    return {k: own[k] - mine[k] for k in rows.COUNTS if k in own and own[k] != mine[k]}


def session_seat(session: dict) -> Any:
    """The seat a session played: the cycle header's, else the one seat its placed requests are on. None for
    a bare session whose requests are on no seat or on several (its `fixed` part then belongs to no seat)."""
    seat = session["head"].get("seat")
    if seat is not None:
        return seat
    seats = {p["seat"] for p in session["placed"] if p["where"] == "turn" and p["seat"] is not None}
    return seats.pop() if len(seats) == 1 else None


def summary(sessions: list[dict], groups: list[dict], table: dict) -> dict:
    """Everything the report prints about usage. `groups` are the report's own turn groups
    (each a dict with the `rows` of the ledger it holds); a request placed in a turn goes to the report turn
    that holds the first ledger row of its group.

        turns      {index of the report turn: tally}
        fixed      tally of the requests before each session's first call (None when there is none)
        unplaced   tally of the requests the ledger does not cover
        total      tally of every request; `turns`, `fixed` and `unplaced` add up to it
        clients    per (ledger label or the reader's client, model): tally, `turns` with `turn_read` and
                   `turn_out` (the tokens of the requests placed in them), `fixed` (the read tokens of its
                   fixed requests), `fresh_in` and `reply_bytes` (new input and cache writes of the requests
                   placed in turns, against the bytes of the replies in those turns)
        seats      per seat, in seat order: `seat`, the tally of every request of that seat (its turns, and
                   the `fixed` and `unplaced` requests of the sessions that played it: `session_seat`) and
                   its `clients` ({client, model}); `seat` None last, for requests on no seat. The seats add
                   up to `total` (a cost only where every model among them has a price)
        sessions   per session: name, kind, client, models, tally, `own`, `short_by`
        prices     the table's date and the models seen that it does not list
    """
    index_of = {id(r): i for i, g in enumerate(groups) for r in g["rows"]}
    per_turn: dict[int, list[dict]] = {}
    fixed: list[dict] = []
    unplaced: list[dict] = []
    everything: list[dict] = []
    clients: dict[tuple, dict] = {}
    seats: dict[Any, dict] = {}
    listed = []
    for s in sessions:
        seen_groups: dict[tuple, set[int]] = {}
        own_seat = session_seat(s)
        for p in s["placed"]:
            everything.append(p)
            key = (s["label"] or p["client"], p["model"])
            at = seats.setdefault(p["seat"] if p["seat"] is not None else own_seat, {"rows": [], "clients": set()})
            at["rows"].append(p)
            at["clients"].add(key)
            c = clients.setdefault(key, {"rows": [], "fixed": [], "placed": [], "turns": set(), "fresh": 0,
                                         "ledger": {}})
            c["rows"].append(p)
            i = index_of.get(id(s["groups"][p["group"]]["rows"][0])) if p["where"] == "turn" else None
            if i is not None:
                per_turn.setdefault(i, []).append(p)
                c["turns"].add(i)
                c["placed"].append(p)
                c["fresh"] += p["new_in"] + p["cache_write"]
                seen_groups.setdefault(key, set()).add(p["group"])
            elif p["where"] == "fixed":
                fixed.append(p)
                c["fixed"].append(p)
            else:
                unplaced.append(p)
        for key, gs in seen_groups.items():
            for g in gs:
                for r in s["groups"][g]["rows"]:
                    clients[key]["ledger"][id(r)] = r.get("bytes") or 0
        listed.append({"name": s["name"], "kind": s["kind"], "client": s["label"],
                       "models": sorted({r["model"] or "(no model)" for r in s["usage"]}),
                       **tally(s["usage"], table), "own": s["own"], "short_by": short_by(s)})
    out_clients = []
    for (label, model), c in sorted(clients.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        in_turns = rows.total(c["placed"])
        out_clients.append({"client": label, "model": model, **tally(c["rows"], table), "turns": len(c["turns"]),
                            "turn_read": read_in(in_turns), "turn_out": in_turns["out"],
                            "fixed": read_in(rows.total(c["fixed"])), "fresh_in": c["fresh"],
                            "reply_bytes": sum(c["ledger"].values())})
    out_seats = [{"seat": seat, **tally(at["rows"], table),
                  "clients": [{"client": c, "model": m} for c, m in sorted(at["clients"], key=lambda k: (str(k[0]), str(k[1])))]}
                 for seat, at in sorted(seats.items(), key=lambda kv: (kv[0] is None, not isinstance(kv[0], int),
                                                                       kv[0] if isinstance(kv[0], int) else str(kv[0])))]
    return {"turns": {i: tally(ps, table) for i, ps in sorted(per_turn.items())},
            "fixed": tally(fixed, table) if fixed else None,
            "unplaced": tally(unplaced, table) if unplaced else None,
            "total": tally(everything, table), "clients": out_clients, "seats": out_seats, "sessions": listed,
            "prices": {"as_of": table.get("as_of"), "unlisted": prices.unlisted(everything, table)}}
