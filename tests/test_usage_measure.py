"""Token accounting, stage 5 (docs/TOKEN_ACCOUNTING.md; GitLab #188): what grows.

The test of the stage: everything measured is a subtraction over the placed rows, so the parts add up. What the
replies brought, summed over the labels, is the context's growth less the output; the turns' tallies are the
requests placed in turns; and a session of 2h turns is compared with twice its own first h."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.usage import codex, join, measure, report, rows

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import usage_measure as M  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "usage"
TABLE = {"as_of": "2026-01-01", "models": {"m": {"input": 2.0, "cache_read": 0.5, "cache_write": 4.0, "output": 10.0}}}


def P(context, out=0, calls=(), sizes=None, group=None, where=None, turn=None, model="m") -> dict:
    """A placed row that read `context` tokens (all from the cache) and wrote `out`."""
    r = rows.row(t=None, client="c", model=model, session="s", request=None,
                 counts={"cache_read": context, "out": out},
                 calls=[dict(zip(("tool", "action"), c.partition("/")[::2])) for c in calls], source="x")
    return {**r, "where": where or ("turn" if group is not None else "fixed"), "group": group,
            "turn": turn if turn is not None else (None if group is None else 100 + group), "seat": 0,
            "matched": len(calls), "reply_bytes": list(sizes) if sizes is not None else [None] * len(calls)}


def fixture_session() -> dict:
    lines = (FIXTURES / "session" / "codex-rollout.jsonl").read_text(encoding="utf-8").splitlines()
    ledger = list(rows.parsed((FIXTURES / "session" / "calls.jsonl").read_text(encoding="utf-8").splitlines()))
    s = {"name": "codex-rollout.jsonl", "kind": "session", "head": {}, "usage": codex.read(lines),
         "own": codex.thread_total(lines)}
    report.place([s], ledger)
    return s


class RequestTests(unittest.TestCase):
    def test_what_a_request_brought_is_the_growth_less_its_own_output(self):
        r = measure.requests([P(1000, out=50), P(1400, out=10), P(1410)])
        self.assertEqual([(x["context"], x["grew"], x["brought"]) for x in r],
                         [(1000, 400, 350), (1400, 10, 0), (1410, None, None)])

    def test_a_smaller_context_after_a_request_is_a_reset_and_brought_nothing(self):
        r = measure.requests([P(9000, out=50), P(2000, out=5), P(2100)])
        self.assertEqual([(x["reset"], x["brought"]) for x in r], [(True, None), (False, 95), (False, None)])

    def test_context_is_everything_read(self):
        p = P(100)
        p.update(new_in=7, cache_write=3)
        self.assertEqual(measure.requests([p])[0]["context"], 110)


class LabelTests(unittest.TestCase):
    def test_a_requests_replies_are_shared_by_the_bytes_the_ledger_recorded(self):
        labs = measure.labels([P(1000, out=100, calls=("state/units", "turn/finish"), sizes=(300, 900)), P(1500)])
        self.assertEqual([(a["tool"], a["action"], a["calls"], a["tokens"], a["bytes"]) for a in labs],
                         [("turn", "finish", 1, 300, 900), ("state", "units", 1, 100, 300)])

    def test_equally_where_the_ledger_lacks_a_call(self):
        labs = measure.labels([P(1000, calls=("state/units", "turn/finish"), sizes=(300, None)), P(1500)])
        self.assertEqual(sorted((a["action"], a["tokens"], a["bytes"]) for a in labs),
                         [("finish", 250, 0), ("units", 250, 300)])

    def test_a_request_with_no_call_is_its_own_label_and_the_labels_add_up_to_the_growth_less_output(self):
        placed = [P(1000, out=20), P(1100, out=30, calls=("state/units",), sizes=(64,)), P(1900, out=5), P(1905)]
        labs = measure.labels(placed)
        self.assertEqual({(a["tool"], a["action"]): a["tokens"] for a in labs},
                         {measure.NO_CALL: 80, ("state", "units"): 770})
        self.assertEqual(sum(a["tokens"] for a in labs), (1905 - 1000) - (20 + 30 + 5))

    def test_the_last_request_and_a_reset_count_no_call(self):
        labs = measure.labels([P(9000, calls=("state/units",), sizes=(10,)), P(100, calls=("turn/finish",), sizes=(10,))])
        self.assertEqual(labs, [])


class TurnTests(unittest.TestCase):
    PLACED = [P(100), P(200, group=0), P(300, out=7, group=0), P(500, group=1), P(600, group=2), P(650, group=2),
              P(700, group=3)]

    def test_one_row_per_turn_in_order_of_play_with_the_context_at_its_ends(self):
        ts = measure.turns(self.PLACED, TABLE)
        self.assertEqual([(t["nth"], t["turn"], t["requests"], t["first"], t["last"], t["out"]) for t in ts],
                         [(1, 100, 2, 200, 300, 7), (2, 101, 1, 500, 500, 0), (3, 102, 2, 600, 650, 0),
                          (4, 103, 1, 700, 700, 0)])
        self.assertAlmostEqual(ts[0]["cost"], (500 * 0.5 + 7 * 10.0) / 1e6, delta=1e-4)      # a tally's cost is rounded

    def test_one_long_session_against_two_of_half_the_length(self):
        s = measure.session({"name": "n", "kind": "cycle", "head": {"turns": 4}, "placed": self.PLACED}, TABLE)
        h = s["halves"]
        self.assertEqual((h["turns"], h["one"]["read"], h["two"]["read"]), (4, 3050, 2 * (100 + 500 + 500)))
        self.assertAlmostEqual(h["two"]["cost"], 2 * (1100 * 0.5 + 7 * 10.0) / 1e6, delta=3e-4)
        self.assertEqual((s["cycle_turns"], s["requests"], s["peak"], s["resets"]), (4, 7, 700, 0))

    def test_an_odd_last_turn_is_left_out_of_both_sides_and_one_turn_has_no_halves(self):
        ts = measure.turns(self.PLACED[:6], TABLE)
        self.assertEqual(measure.halves(ts, None)["one"]["read"], 500 + 500)
        self.assertIsNone(measure.halves(ts[:1], None))

    def test_an_unlisted_model_has_no_cost_on_either_side(self):
        s = measure.session({"name": "n", "kind": "cycle", "head": {},
                             "placed": [P(100, group=0, model="nobody"), P(200, group=1, model="nobody")]}, TABLE)
        self.assertNotIn("cost", s["halves"]["one"])
        self.assertNotIn("cost", s["halves"]["two"])
        self.assertNotIn("cost", s["total"])

    def test_positions_average_the_sessions_that_got_that_far(self):
        a = measure.session({"name": "a", "kind": "cycle", "head": {}, "placed": self.PLACED}, TABLE)
        b = measure.session({"name": "b", "kind": "cycle", "head": {}, "placed": [P(400, group=0)]}, TABLE)
        pos = measure.positions([a, b])
        self.assertEqual([(p["nth"], p["sessions"], p["first"], p["read"]) for p in pos],
                         [(1, 2, 300.0, 450.0), (2, 1, 500.0, 500.0), (3, 1, 600.0, 1250.0), (4, 1, 700.0, 700.0)])


class FixtureTests(unittest.TestCase):
    """The eleven-turn Codex session of the join's tests."""

    def test_the_parts_add_up(self):
        s = fixture_session()
        m = measure.session(s, TABLE)
        self.assertEqual([t["turn"] for t in m["turns"]], [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 38])
        per_turn = join.per_turn(s["placed"])
        self.assertEqual([t["requests"] for t in m["turns"]], [x["requests"] for x in per_turn if x["where"] == "turn"])
        self.assertEqual(sum(t["requests"] for t in m["turns"]) + m["fixed"]["requests"], m["requests"])
        reqs = measure.requests(s["placed"])
        self.assertEqual(m["resets"], 0)
        self.assertAlmostEqual(sum(a["tokens"] for a in m["labels"]),
                               reqs[-1]["context"] - reqs[0]["context"] - sum(r["out"] for r in reqs[:-1]),
                               delta=len(m["labels"]))                      # each label's share is rounded
        self.assertEqual(sum(a["calls"] for a in m["labels"] if (a["tool"], a["action"]) != measure.NO_CALL),
                         sum(len(p["calls"]) for p in s["placed"][:-1]))
        self.assertEqual(m["halves"]["turns"], 10)
        self.assertEqual(m["halves"]["one"]["read"],
                         sum(report.read_in(t) for t in m["turns"][:10]) + report.read_in(m["fixed"]))

    def test_every_matched_call_carries_the_ledgers_reply_size(self):
        s = fixture_session()
        for p in s["placed"]:
            self.assertEqual(len(p["reply_bytes"]), len(p["calls"]))
            self.assertEqual(sum(b is not None for b in p["reply_bytes"]), p["matched"])


class ScriptTests(unittest.TestCase):
    def run_script(self, *argv: str) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["usage_measure.py", *argv]), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            self.assertEqual(M.main(), 0)
        return out.getvalue(), err.getvalue()

    ARGS = (str(FIXTURES / "session" / "calls.jsonl"), "--usage", str(FIXTURES / "session" / "codex-rollout.jsonl"))

    def test_one_document_per_client_and_model(self):
        with tempfile.TemporaryDirectory() as d:
            out, err = self.run_script(*self.ARGS, "--out", d)
            self.assertIn("1 of 1 session(s) played 10 turns or more", err)
            [path] = list(Path(d).iterdir())
            self.assertEqual(out.strip(), str(path))
            self.assertEqual(path.name, "codex-gpt-6.1-sol.md")
            text = path.read_text(encoding="utf-8")
        for heading in ("## By turn position", "## What the replies brought", "## Session length",
                        "## `codex-rollout.jsonl`"):
            self.assertIn(heading, text)
        self.assertIn("| 11 | 38 | 14 |", text)
        self.assertIn("est $", text)

    def test_a_short_session_is_left_out_and_json_prints_the_measured_sessions(self):
        out, err = self.run_script(*self.ARGS, "--min-turns", "12")
        self.assertEqual(out, "")
        self.assertIn("0 of 1", err)
        out, _ = self.run_script(*self.ARGS, "--json")
        [m] = [json.loads(line) for line in out.splitlines()]
        self.assertEqual((m["client"], len(m["turns"])), ("codex/gpt-6.1-sol", 11))

    def test_an_unlisted_model_gets_no_dollar_column(self):
        with tempfile.TemporaryDirectory() as d:
            prices_path = Path(d) / "p.json"
            prices_path.write_text(json.dumps({"as_of": "2026-01-01", "models": {}}), encoding="utf-8")
            out, _ = self.run_script(*self.ARGS, "--prices", str(prices_path))
        self.assertNotIn("$", out)
        self.assertIn("no price list", out)


if __name__ == "__main__":
    unittest.main()
