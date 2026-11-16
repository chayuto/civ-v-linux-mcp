"""Tokens per seat for the page, from the clients' own usage records (docs/TOKEN_ACCOUNTING.md stage 6, #189).

The spectator is the operator's view, so it may show what no seat is told: what each seat's model has read and
written. Nothing is counted here. `--usage <file or dir>` (repeatable) names the same paths
`scripts/ledger_report.py --usage` takes, and every poll that finds one of those files or the ledger changed
runs the report's own steps over them (`report.read`, `report.place`, `report.summary`), so the figures on the
page are the report's figures for the same files at that moment:

    {"seats": [{"seat": 0, "clients": [{"client": "codex/gpt-6.1-sol", "model": "gpt-6.1-sol"}],
                "game": {requests, new_in, cache_read, cache_write, out, reasoning[, cost]},
                "turn": 243, "this_turn": {...}}],
     "total": {...}, "prices": {"as_of": ..., "unlisted": [...]}}

`game` is the report's line for that seat: every request the paths hold for it, the `fixed` and `unplaced`
ones of its sessions included. "This game" is therefore what the operator points `--usage` at; a directory
holding other games' sessions counts them too, exactly as the report would. `this_turn` is the report's row
for the seat's latest turn in the ledger (zeros until a request is placed there); a seat the ledger never
names has no turn. `seat` None collects the requests that are on no seat. `cost` is tokens at list price
(`harness/usage/prices.json`), absent wherever a model has none.

The event replaces the one before it (a request whose call is still running is placed by the call before it,
and moves to its own turn once the ledger holds the row), so a recording's last usage event is what the
report prints for the session: that equality is the stage's test. Counts, ids and labels only, never a word
of a transcript (rule 2). A poll costs a `stat` per file while nothing changed and a full read when something
did: about 70 ms for one session's directory, under 2 s for a thousand cycles (measured 2026-11-15).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ..usage import join, prices, report, rows

EMPTY = {"requests": 0, **dict.fromkeys(rows.COUNTS, 0)}


def ledger_rows(path: str | Path) -> list[dict]:
    """The ledger's rows, read whole. A line that is not a row (a half-written last one) is passed over."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict) and isinstance(r.get("t"), (int, float)) and "kind" in r and "ok" in r:
                    out.append(r)
    except OSError:
        return []
    return out


def counts(tally: dict | None) -> dict:
    """A report tally as the page takes it: the request count, the five token counts, `cost` where known."""
    if not tally:
        return dict(EMPTY)
    return {k: tally[k] for k in (*EMPTY, "cost") if k in tally}


def shape(summary: dict, groups: list[dict]) -> dict:
    """The usage event's data from the report's summary and the turn groups it was summed over."""
    latest: dict[Any, int] = {}
    for i, g in enumerate(groups):
        latest[g["seat"]] = i
    seats = []
    for s in summary["seats"]:
        row: dict[str, Any] = {"seat": s["seat"], "clients": s["clients"], "game": counts(s)}
        i = latest.get(s["seat"]) if s["seat"] is not None else None
        if i is not None:
            row["turn"] = groups[i]["turn"]
            row["this_turn"] = counts(summary["turns"].get(i))
        seats.append(row)
    return {"seats": seats, "total": counts(summary["total"]), "prices": summary["prices"]}


def read(pool: Iterable[Path | str], ledger_path: str | Path | None, table: dict, server: str = "civ5") -> dict:
    """The usage event's data for these usage files against this ledger, by the report's own steps."""
    ledger = ledger_rows(ledger_path) if ledger_path else []
    sessions, _ = report.read(pool, server)
    report.place(sessions, ledger)
    groups, _ = join.turn_groups(ledger)
    return shape(report.summary(sessions, groups, table), groups)


class UsageWatch:
    def __init__(self, paths: Iterable[str | Path], ledger_path: str | Path | None,
                 prices_path: str | Path | None = None, server: str = "civ5",
                 exclude: Iterable[str | Path | None] = ()):
        """`exclude`: files under the paths that are no client's record and grow all the time (the spectator's
        own recording); the ledger is left out by itself. A log directory often holds all three."""
        self.paths = [Path(p).expanduser() for p in paths]
        self.ledger_path = ledger_path
        self.table = prices.load(prices_path)
        self.server = server
        self.exclude = {Path(p).expanduser().resolve() for p in (ledger_path, *exclude) if p}
        self.signature: tuple | None = None
        self.last: dict | None = None

    def pool(self) -> list[Path]:
        """The usage files there are right now (a path that does not exist yet is waited for)."""
        return [p for p in report.files(self.paths) if p.is_file() and p.resolve() not in self.exclude]

    def _signature(self, pool: list[Path]) -> tuple:
        out = []
        for p in [*pool, *([Path(self.ledger_path)] if self.ledger_path else [])]:
            try:
                st = p.stat()
            except OSError:
                continue
            out.append((str(p), st.st_size, st.st_mtime_ns))
        return tuple(out)

    def poll(self) -> dict | None:
        """The usage event's data when it differs from the last one handed out, else None. Nothing is read
        while no usage file and no ledger byte changed; no event is made of paths that hold no session yet."""
        pool = self.pool()
        signature = self._signature(pool)
        if signature == self.signature:
            return None
        data = read(pool, self.ledger_path, self.table, self.server)
        self.signature = signature
        if data == self.last or (self.last is None and not data["seats"]):
            return None
        self.last = data
        return data
