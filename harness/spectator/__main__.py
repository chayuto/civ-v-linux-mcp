"""`python -m harness.spectator`: serve the live visualization, record the stream, or replay a recording.

  python -m harness.spectator --ledger logs/calls.jsonl --record logs/spectate.jsonl
  python -m harness.spectator --replay logs/spectate.jsonl

Live mode needs tunerd (CIV5_TUNERD_SOCK or the default socket) and reads the ledger the seat servers write
(their CIV5_CALL_LOG). Replay needs no game at all. Either way the page is at http://HOST:PORT/.

`--usage PATH` (repeatable, live mode) adds tokens per seat to the page, this turn and this game: the paths
are the ones `scripts/ledger_report.py --usage` takes (a seat-loop log directory, a Codex rollout, a Claude
Code transcript, or a directory of them), read by the report's own code, so the page and the report agree.
Name the files of the game being watched: everything under the paths is counted. A cycle that is still
running is read per request only when the client's own directory is among the paths (`--usage logs/night
--usage ~/.codex/sessions`); Grok's stream carries its requests as they happen. The counts go into the
recording, so a replay shows them with no usage file at hand. Operator's view: no seat reads this page.

The page scrubs through whatever is recorded: under --replay the whole file, from its start, on the page's own
clock (play, pause, speed, a slider with the turn boundaries marked); live with --record, everything this
spectator has recorded, with a "live" button back to the tail. `--speed N` makes the server pace the replayed
stream as well (the page's own player ignores it); the default pushes the file at once.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import threading

from .feed import Feed, Live, replay
from .server import WEB_DIR, serve


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m harness.spectator", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", help="the seat servers' CIV5_CALL_LOG file to tail")
    ap.add_argument("--notes-dir", help="notebook dir (default: harness.notes.notes_dir())")
    ap.add_argument("--usage", action="append", metavar="PATH",
                    help="a client's usage record or a directory of them, for tokens per seat on the page "
                         "(what scripts/ledger_report.py --usage takes); repeatable; needs --ledger")
    ap.add_argument("--prices", help="a price table in place of harness/usage/prices.json")
    ap.add_argument("--record", help="append the merged stream to this JSONL file (the page can scrub through it)")
    ap.add_argument("--replay", help="replay this recording instead of watching a game")
    ap.add_argument("--speed", type=float, default=0.0,
                    help="server-side replay pacing (0 = the whole file at once, the page's player does the timing)")
    ap.add_argument("--sock", help="tunerd socket (default: CIV5_TUNERD_SOCK / XDG_RUNTIME_DIR)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--web", type=pathlib.Path, default=WEB_DIR, help="the page's directory")
    a = ap.parse_args(argv)

    feed = Feed(record_path=a.record, recording_path=a.replay or a.record, mode="replay" if a.replay else "live")
    if a.replay:
        threading.Thread(target=replay, args=(a.replay, feed, a.speed), daemon=True).start()
    else:
        if not a.ledger:
            print("spectator: --ledger is needed in live mode (the seat servers' CIV5_CALL_LOG)", file=sys.stderr)
        from ..client import Civ5
        usage = None
        if a.usage:
            from .usage_watch import UsageWatch
            usage = UsageWatch(a.usage, a.ledger, a.prices, exclude=[a.record])
        live = Live(feed, Civ5(a.sock), a.ledger, a.notes_dir, usage=usage)
        threading.Thread(target=live.run, daemon=True).start()
    print(f"spectator: http://{a.host}:{a.port}/  ({'replay ' + a.replay if a.replay else 'live'})", file=sys.stderr)
    try:
        serve(feed, a.host, a.port, a.web)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
