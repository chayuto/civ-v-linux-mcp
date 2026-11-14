#!/usr/bin/env python3
"""What a session's tokens went on, as tables (docs/TOKEN_ACCOUNTING.md stage 5).

    scripts/usage_measure.py logs/calls.jsonl --usage logs/night --usage ~/.codex/sessions
    scripts/usage_measure.py logs/calls.jsonl --usage logs/bench --out docs/measurements

Reads the same files as `ledger_report.py --usage` and measures every session that played `--min-turns` turns
or more (`harness/usage/measure.py`). One document per client and model: the context at each turn position, the
`(tool, action)` replies that brought the most tokens, each session's turns, and one long session against two
of half the length. Without `--out` the documents go to stdout; `--json` prints the measured sessions instead.
Operator-side: reads logs, never the game.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.usage import measure, prices
from harness.usage import report as usage_report


def k(n: float | None) -> str:
    return "" if n is None else f"{n:,.0f}"


def usd(t: dict) -> str:
    return f"{t['cost']:.2f}" if "cost" in t else ""


def table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "|".join(" :--- " if i == 0 else " ---: " for i in range(len(head))) + "|",
            *("| " + " | ".join(r) + " |" for r in rows), ""]


def shown(s: dict) -> str:
    """A session by its folder and file: two runs of one agent both hold a `codex-c1.jsonl`."""
    return f"{Path(s['path']).parent.name}/{s['name']}" if s.get("path") else s["name"]


def family(s: dict) -> tuple[str, str]:
    """(client name, model): one document each. The client name is the part of the label before the slash."""
    return str(s["client"] or "unknown").split("/")[0], "+".join(s["models"])


def document(name: str, model: str, sessions: list[dict], top: int, as_of: str | None) -> str:
    priced = all("cost" in s["total"] for s in sessions)
    out = [f"# {name}, {model}: what grows", "",
           f"{len(sessions)} session(s), {sum(len(s['turns']) for s in sessions)} turns, "
           f"{sum(s['requests'] for s in sessions):,} model requests. Written by `scripts/usage_measure.py`; the "
           f"columns are explained in `docs/TOKEN_ACCOUNTING.md`."
           + (f" Dollars are list prices as of {as_of}, an estimate of tokens spent, not money paid."
              if priced else " The model is on no price list, so there is no dollar column."), "",
           "## By turn position", "",
           "The n-th turn a session played, averaged over the sessions that got that far. `context` is what the "
           "turn's first request read; `read` is everything the turn's requests read.", ""]
    pos = measure.positions(sessions)
    out += table(["nth turn", "sessions", "requests", "context", "read", "out"] + (["est $"] if priced else []),
                 [[str(p["nth"]), str(p["sessions"]), f"{p['requests']:.1f}", k(p["first"]), k(p["read"]), k(p["out"])]
                  + ([usd(p)] if priced else []) for p in pos])
    labs = measure.merged_labels(sessions)
    whole = sum(a["tokens"] for a in labs) or 1
    out += ["## What the replies brought", "",
            "The context's growth after a request, less the request's own output, shared among its calls by reply "
            "size. `tok/byte` is that against the bytes the ledger recorded (bytes / 4 assumes 0.25).", ""]
    out += table(["call", "calls", "tokens", "share", "per call", "tok/byte"],
                 [[f"`{a['tool']}`" + (f" `{a['action']}`" if a["action"] else ""), str(a["calls"]), k(a["tokens"]),
                   f"{100 * a['tokens'] / whole:.1f}%", k(a["tokens"] / a["calls"]),
                   f"{a['tokens'] / a['bytes']:.2f}" if a["bytes"] else ""] for a in labs[:top]])
    out += ["## Session length", "",
            "`one` is the session's first 2h turns as played; `two` is twice its first h turns, the fixed part "
            "paid twice: what two sessions of half the length would have read, if the second went as the first.", ""]
    out += table(["session", "cycle turns", "turns", "requests", "peak context", "resets", "read"]
                 + (["est $"] if priced else []) + ["2h", "one read", "two read", "two / one"]
                 + (["two / one $"] if priced else []),
                 [[f"`{shown(s)[:40]}`", str(s["cycle_turns"] or ""), str(len(s["turns"])), str(s["requests"]),
                   k(s["peak"]), str(s["resets"]), k(usage_report.read_in(s["total"]))]
                  + ([usd(s["total"])] if priced else [])
                  + ([str(h["turns"]), k(h["one"]["read"]), k(h["two"]["read"]),
                      f"{h['two']['read'] / h['one']['read']:.2f}"] if (h := s["halves"]) else ["", "", "", ""])
                  + ([f"{h['two']['cost'] / h['one']['cost']:.2f}" if h and h["one"].get("cost") else ""]
                     if priced else []) for s in sessions])
    out += ["Summed by the length a session was asked to play (the seat loop's `--turns`):", ""]
    out += table(["cycle turns", "sessions", "turns", "requests", "read", "read / turn", "out"]
                 + (["est $", "$ / turn"] if priced else []),
                 [[str(c["cycle_turns"] or "(no loop)"), str(c["sessions"]), str(c["turns"]), str(c["requests"]),
                   k(c["read"]), k(c["read"] / c["turns"]) if c["turns"] else "", k(c["out"])]
                  + ([usd(c), f"{c['cost'] / c['turns']:.3f}" if c["turns"] else ""] if priced else [])
                  for c in measure.by_cycle_length(sessions)])
    for s in sessions:
        out += [f"## `{shown(s)}`", ""]
        out += table(["nth", "game turn", "requests", "context first", "context last", "read", "cached", "out"]
                     + (["est $"] if priced else []),
                     [[str(t["nth"]), str(t["turn"]), str(t["requests"]), k(t["first"]), k(t["last"]),
                       k(usage_report.read_in(t)), k(t["cache_read"]), k(t["out"])] + ([usd(t)] if priced else [])
                      for t in s["turns"]])
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ledger")
    ap.add_argument("--usage", action="append", required=True, metavar="PATH")
    ap.add_argument("--client", help="only sessions whose client label or name contains this text")
    ap.add_argument("--min-turns", type=int, default=10)
    ap.add_argument("--top", type=int, default=20, help="how many call labels to list")
    ap.add_argument("--out", help="a directory: one <client>-<model>.md per document")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--prices")
    a = ap.parse_args()
    with open(a.ledger, encoding="utf-8") as f:
        ledger = [json.loads(line) for line in f if line.strip()]
    price = prices.load(a.prices)
    sessions, _ = usage_report.read(a.usage)
    usage_report.place(sessions, ledger)
    measured = [measure.session(s, price) for s in sessions]
    if a.client:
        measured = [m for m in measured if a.client in str(m["client"]) or a.client in m["name"]]
    kept = [m for m in measured if len(m["turns"]) >= a.min_turns]
    print(f"{len(kept)} of {len(measured)} session(s) played {a.min_turns} turns or more", file=sys.stderr)
    if a.json:
        for m in kept:
            print(json.dumps(m))
        return 0
    docs: dict[tuple[str, str], list[dict]] = {}
    for m in kept:
        docs.setdefault(family(m), []).append(m)
    for (name, model), ss in sorted(docs.items()):
        text = document(name, model, ss, a.top, price.get("as_of"))
        if a.out:
            path = Path(a.out) / (re.sub(r"[^A-Za-z0-9.]+", "-", f"{name}-{model}").strip("-") + ".md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            print(path)
        else:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
