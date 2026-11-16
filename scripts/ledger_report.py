#!/usr/bin/env python3
"""Per-turn cost of play from a call ledger (`CIV5_CALL_LOG`, harness/call_ledger.py; GitLab #36).

A turn is every call made while the game stood at that turn, up to and including the wait that ended it
(`call_ledger.turn_groups`: a wait a leader's screen stopped does not end the turn, a turn ended with one call
is a turn).
Inspection (reads) and orders (writes) are counted apart from waiting, whose seconds are the AIs' turns and the
bridge, not the model's overhead. `~tok` is bytes / 4: no client tokenizer is available here.

A row's `client` (CIV5_CLIENT in the server's environment, else the MCP client's name/version) says who made
the call: `--client codex` keeps the rows whose label contains that text, and the footer lists every label seen
with its rows and turns, so two models on the same seat stay apart.

`--usage <file or dir>` (repeatable) adds what each turn cost the model, from the clients' own usage records
(docs/TOKEN_ACCOUNTING.md; `harness/usage/report.py` says which files it takes): per turn `req` (model requests),
`new in` (input read at full price, cache writes included), `cached` (input read from the provider's cache),
`out`, `think` (the part of `out` that was reasoning) and `est $`. Requests before a session's first call are
the line `fixed` (system prompt, tool listing), requests the ledger does not cover the line `unplaced`. The
footer gives the total, each client and model (tokens per turn, cache share, the `fixed` share, and new input
tokens per reply byte: what bytes / 4 should have been), each seat (the line the spectator page's "game" row
repeats, `python -m harness.spectator --usage`), and how each session's rows stand against the client's own
total. `est $` is tokens at the list prices of `harness/usage/prices.json`, an estimate of tokens spent and
never money paid; a model with no list price gets no dollar figure anywhere.

Usage:
    .venv/bin/python scripts/ledger_report.py calls.jsonl [--seat 0] [--client codex] [--json]
        [--usage logs/night [--usage ~/.codex/sessions]] [--prices prices.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import call_ledger
from harness.usage import prices
from harness.usage import report as usage_report


def load(path: str, seat: int | None, client: str | None = None) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if seat is not None and r.get("seat") != seat:
                continue
            if client is not None and client not in (r.get("client") or ""):
                continue
            rows.append(r)
    return rows


def clients(rows: list[dict]) -> list[dict]:
    """Every `client` label in the rows (None for rows without one): rows, seats and the turns it spans."""
    by: dict = {}
    for r in rows:
        c = by.setdefault(r.get("client"), {"client": r.get("client"), "rows": 0, "seats": set(), "turns": []})
        c["rows"] += 1
        c["seats"].add(r.get("seat"))
        if isinstance(r.get("turn"), int):
            c["turns"].append(r["turn"])
    out = []
    for c in by.values():
        ts = sorted(c["turns"])
        out.append({"client": c["client"], "rows": c["rows"], "seats": sorted(c["seats"], key=str),
                    "first_turn": ts[0] if ts else None, "last_turn": ts[-1] if ts else None})
    return sorted(out, key=lambda c: (c["client"] is None, str(c["client"])))


def turns(rows: list[dict]) -> list[dict]:
    """One summary per turn, the rows grouped by `call_ledger.turn_groups` (a turn is ended by a wait that
    returned into another turn; the turn number is the first one a non-wait row carries, else the one the previous
    wait returned),
    each seat's rows on their own, in order of the turns' first rows."""
    return [summary for summary, _ in grouped(rows)]


def grouped(rows: list[dict]) -> list[tuple[dict, dict]]:
    """(the turn's summary, its group) per turn: the group holds the ledger rows the usage join places by.
    Each seat's rows are grouped on their own; the turns come in the file's order of their first rows."""
    at = {id(r): i for i, r in enumerate(rows)}
    by_seat: dict = {}
    for r in rows:
        by_seat.setdefault(r.get("seat"), []).append(r)
    groups = [{"seat": seat, **g} for seat, rs in by_seat.items() for g in call_ledger.turn_groups(rs)]
    out = []
    for g in sorted(groups, key=lambda g: at[id(g["rows"][0])]):
        t = summarize(g["rows"], g["turn"])
        t["seat"] = g["seat"]
        if g["open"]:
            t["open"] = True
        out.append((t, g))
    return out


def label(r: dict) -> str:
    """`tool · action` for a row in the nine-tool vocabulary (stage 2d), the bare tool for an older row."""
    return f"{r['tool']} · {r['action']}" if r.get("action") else str(r.get("tool"))


def summarize(rows: list[dict], fallback_turn: int | None) -> dict:
    reads = [r for r in rows if r["kind"] == "read"]
    writes = [r for r in rows if r["kind"] == "write"]
    waits = [r for r in rows if r["kind"] == "wait"]
    turn = next((r["turn"] for r in rows if r["kind"] != "wait" and isinstance(r.get("turn"), int)), fallback_turn)
    return {
        "turn": turn,
        "reads": len(reads), "read_bytes": sum(r["bytes"] for r in reads),
        "read_trips": sum(r.get("trips") or 0 for r in reads),
        "read_seconds": round(sum(r["seconds"] for r in reads), 1),
        "writes": len(writes), "write_bytes": sum(r["bytes"] for r in writes),
        "refused": sum(1 for r in writes if not r["ok"]),
        "refused_reads": sum(1 for r in reads if not r["ok"]),
        "wait_refused": sum(1 for r in waits if not r["ok"]),
        "wait_seconds": round(sum(r["seconds"] for r in waits), 1),
        "tools": sorted({label(r) for r in reads}),
        "refusals": [f"{label(r)}: {r.get('err', '')}" for r in rows if not r["ok"]],
    }


USAGE_HEAD = f" {'req':>4} {'new in':>9} {'cached':>10} {'out':>7} {'think':>7} {'est $':>8}"


def usage_cells(u: dict | None) -> str:
    """The usage columns of one line; dashes where no request was placed, no dollar figure without a price."""
    if not u:
        return f" {'-':>4} {'-':>9} {'-':>10} {'-':>7} {'-':>7} {'':>8}"
    cost = f"{u['cost']:.2f}" if "cost" in u else ""
    return (f" {u['requests']:>4} {u['new_in'] + u['cache_write']:>9} {u['cache_read']:>10} {u['out']:>7} "
            f"{u['reasoning']:>7} {cost:>8}")


def share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f} %" if whole else "-"


def usage_footer(u: dict, skipped: int) -> list[str]:
    """The lines under the table: the total, each client and model, and the sessions against their own totals."""
    out = []
    total = u["total"]
    read = usage_report.read_in(total)
    fixed = usage_report.read_in(u["fixed"]) if u["fixed"] else 0
    n = len(u["turns"])
    in_turns = sum(usage_report.read_in(t) for t in u["turns"].values())
    out_turns = sum(t["out"] for t in u["turns"].values())
    out.append(f"usage: {total['requests']} requests in {len(u['sessions'])} session(s), {read} tokens read "
               f"({share(total['cache_read'], read)} from cache, {share(fixed, read)} fixed), {total['out']} written"
               + (f", {in_turns // n} read and {out_turns // n} written per turn over {n} turn(s)" if n else "")
               + (f", est ${total['cost']:.2f}" if "cost" in total else ""))
    for c in u["clients"]:
        r = usage_report.read_in(c)
        per = (f", {c['turn_read'] // c['turns']} read and {c['turn_out'] // c['turns']} written per turn over "
               f"{c['turns']} turn(s)" if c["turns"] else "")
        byte = (f", {c['fresh_in'] / c['reply_bytes']:.2f} new input tokens per reply byte (bytes / 4 says 0.25)"
                if c["reply_bytes"] else "")
        out.append(f"usage {c['client'] or '(no label)'} {c['model'] or '(no model)'}: {c['requests']} requests, "
                   f"{r} read ({share(c['cache_read'], r)} from cache, {share(c['fixed'], r)} fixed), "
                   f"{c['out']} written{per}{byte}" + (f", est ${c['cost']:.2f}" if "cost" in c else ""))
    for s in u["seats"]:
        r = usage_report.read_in(s)
        who = ", ".join(sorted({str(c["client"] or "(no label)") for c in s["clients"]}))
        out.append(f"usage {'seat ' + str(s['seat']) if s['seat'] is not None else 'on no seat'} [{who}]: "
                   f"{s['requests']} requests, {r} read ({share(s['cache_read'], r)} from cache), {s['out']} written"
                   + (f", est ${s['cost']:.2f}" if "cost" in s else ""))
    equal =[s for s in u["sessions"] if s["short_by"] == {}]
    differ = [s for s in u["sessions"] if s["short_by"]]
    silent = [s for s in u["sessions"] if s["short_by"] is None]
    out.append(f"sessions: {len(equal)} equal to the client's own total, {len(differ)} differ, "
               f"{len(silent)} with no total of the client's" + (f"; {skipped} file(s) left out" if skipped else ""))
    for s in differ:
        gap = ", ".join(f"{k} {v:+d}" for k, v in s["short_by"].items())
        out.append(f"  {s['name']}: the client's own total against the rows: {gap} "
                   f"(requests the client kept no row for; in no sum above)")
    if len(u["sessions"]) <= 12:
        for s in u["sessions"]:
            mark = {True: "=", False: "!="}[s["short_by"] == {}] if s["short_by"] is not None else "?"
            out.append(f"  {s['name']} [{s['client'] or 'no label'}; {', '.join(s['models'])}]: {s['requests']} requests, "
                       f"{usage_report.read_in(s)} read, {s['out']} written {mark} own total"
                       + (f", est ${s['cost']:.2f}" if "cost" in s else ""))
    if "cost" in total or any("cost" in c for c in u["clients"]):
        out.append(f"est $: tokens at the list prices of {u['prices']['as_of']} (harness/usage/prices.json), "
                   f"an estimate of tokens spent; a subscription pays no per-token price")
    if u["prices"]["unlisted"]:
        out.append(f"no list price, so no dollar figure: {', '.join(u['prices']['unlisted'])}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger")
    ap.add_argument("--seat", type=int)
    ap.add_argument("--client", help="only rows whose `client` label contains this text (e.g. codex, grok, claude)")
    ap.add_argument("--json", action="store_true", help="one JSON object per turn instead of the table")
    ap.add_argument("--usage", action="append", metavar="PATH",
                    help="a client's usage record or a directory of them (seat-loop cycles, Codex rollouts, "
                         "Claude Code transcripts); repeatable")
    ap.add_argument("--prices", help="a price table in place of harness/usage/prices.json")
    a = ap.parse_args()
    rows = load(a.ledger, a.seat, a.client)
    pairs = grouped(rows)
    ts = [t for t, _ in pairs]
    usage = None
    if a.usage:
        sessions, skipped = usage_report.read(a.usage)
        if a.client is not None:
            sessions = [s for s in sessions if any(a.client in str(x) for x in (
                s["head"].get("client"), s["head"].get("agent"), *(r["client"] for r in s["usage"][:1])))]
        usage_report.place(sessions, rows)
        usage = usage_report.summary(sessions, [g for _, g in pairs], prices.load(a.prices))
        for i, t in enumerate(ts):
            if i in usage["turns"]:
                t["usage"] = usage["turns"][i]
    if a.json:
        for t in ts:
            print(json.dumps(t))
        if usage is not None:
            print(json.dumps({"usage": {**{k: v for k, v in usage.items() if k != "turns"}, "left_out": skipped}}))
        return 0
    seats = len({t["seat"] for t in ts}) > 1
    print(f"{'turn':>5} {'reads':>5} {'bytes':>7} {'~tok':>6} {'trips':>5} {'read s':>6} "
          f"{'writes':>6} {'refused':>7} {'wait s':>7}" + (USAGE_HEAD if usage else ""))
    for t in ts:
        mark = (f" seat {t['seat']}" if seats else "") + (" (open)" if t.get("open") else "")
        print(f"{t['turn']!s:>5} {t['reads']:>5} {t['read_bytes']:>7} {t['read_bytes'] // 4:>6} {t['read_trips']:>5} "
              f"{t['read_seconds']:>6} {t['writes']:>6} {t['refused']:>7} {t['wait_seconds']:>7}"
              f"{usage_cells(t.get('usage')) if usage else ''}{mark}")
    done = [t for t in ts if not t.get("open")]
    if done:
        n = len(done)
        print(f"{'mean':>5} {sum(t['reads'] for t in done) / n:>5.1f} {sum(t['read_bytes'] for t in done) / n:>7.0f} "
              f"{sum(t['read_bytes'] for t in done) / n / 4:>6.0f} {sum(t['read_trips'] for t in done) / n:>5.1f} "
              f"{sum(t['read_seconds'] for t in done) / n:>6.1f} {sum(t['writes'] for t in done) / n:>6.1f} "
              f"{sum(t['refused'] for t in done) / n:>7.1f} {sum(t['wait_seconds'] for t in done) / n:>7.1f}"
              f"   over {n} completed turn(s)")
    if usage:
        for name in ("fixed", "unplaced"):
            if usage[name]:
                print(f"{name:<62}{usage_cells(usage[name])}")
        print(f"{'total':<62}{usage_cells(usage['total'])}")
    for t in ts:
        for msg in t["refusals"]:
            print(f"  t{t['turn']} refused {msg}")
    for c in clients(rows):
        span = f"t{c['first_turn']}-t{c['last_turn']}" if c["first_turn"] is not None else "no turn"
        print(f"client {c['client'] or '(none)'}: {c['rows']} rows, seat {','.join(map(str, c['seats']))}, {span}")
    if usage:
        for line in usage_footer(usage, skipped):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
