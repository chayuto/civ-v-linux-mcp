"""Token accounting, stage 4 (docs/TOKEN_ACCOUNTING.md; GitLab #187): the report and the price table.

The test of the stage: the report's sums reproduce each session's own total (a Codex cycle's `turn.completed`),
the per-turn lines with `fixed` and `unplaced` add up to the total, and a model with no list price gets no
dollar figure anywhere, in the table, the footer or the JSON."""
from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness.usage import codex, cycle, join, prices, report, rows

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ledger_report as R  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "usage"
KEYS = ("requests", *rows.COUNTS)
TABLE = {"as_of": "2026-01-01", "models": {"m": {"input": 2.0, "cache_read": 0.5, "cache_write": 4.0, "output": 10.0}}}


def ledger(name: str) -> list[dict]:
    return list(rows.parsed((FIXTURES / name).read_text(encoding="utf-8").splitlines()))


def run(*argv: str) -> str:
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["ledger_report.py", *argv]), contextlib.redirect_stdout(out):
        assert R.main() == 0
    return out.getvalue()


def summarized(paths, ledger_rows, table=None):
    sessions, skipped = report.read(paths)
    report.place(sessions, ledger_rows)
    groups = join.turn_groups(ledger_rows)[0]
    return sessions, report.summary(sessions, groups, table or prices.load()), skipped


def parts(u: dict) -> dict:
    """The per-turn tallies with `fixed` and `unplaced`, summed."""
    tallies = [*u["turns"].values(), *(u[k] for k in ("fixed", "unplaced") if u[k])]
    return {k: sum(t[k] for t in tallies) for k in KEYS}


class PriceTests(unittest.TestCase):
    def test_the_table_names_a_date_and_a_source_for_every_model(self):
        table = prices.load()
        self.assertRegex(table["as_of"], r"\d{4}-\d\d-\d\d\Z")
        self.assertTrue(table["models"])
        for model, p in table["models"].items():
            with self.subTest(model=model):
                self.assertRegex(p["as_of"], r"\d{4}-\d\d-\d\d\Z")
                self.assertTrue(p["source"].startswith("https://"))
                for rate in prices.RATE.values():
                    self.assertGreater(p[rate], 0)
                # a cache read is the cheap way to read, a cache write never cheaper than plain input
                self.assertLess(p["cache_read"], p["input"])
                self.assertGreaterEqual(p["cache_write"], p["input"])

    def test_cost_charges_each_count_at_its_rate_and_reasoning_once(self):
        r = {"model": "m", "new_in": 1_000_000, "cache_read": 2_000_000, "cache_write": 500_000, "out": 100_000,
             "reasoning": 90_000}
        self.assertAlmostEqual(prices.cost(r, TABLE["models"]["m"]), 2.0 + 1.0 + 2.0 + 1.0)
        self.assertAlmostEqual(prices.of([r, r], TABLE), 12.0)

    def test_an_unlisted_model_has_no_cost_and_spoils_the_sum_it_is_in(self):
        known = {"model": "m", "new_in": 10, "cache_read": 0, "cache_write": 0, "out": 1, "reasoning": 0}
        other = {**known, "model": "nobody-1"}
        self.assertIsNone(prices.of([other], TABLE))
        self.assertIsNone(prices.of([known, other], TABLE))
        self.assertIsNone(prices.of([], TABLE))
        self.assertEqual(prices.unlisted([known, other, {**known, "model": None}], TABLE), ["(no model)", "nobody-1"])
        # a row that spent nothing costs nothing, whatever it names
        self.assertEqual(prices.of([known, dict.fromkeys(rows.COUNTS, 0) | {"model": "<synthetic>"}], TABLE),
                         prices.of([known], TABLE))


class CycleReportTests(unittest.TestCase):
    """The three live cycles of stage 2 through the report (Maya t242, 2026-11-13)."""

    def setUp(self):
        self.ledger = ledger("cycles/calls.jsonl")
        self.sessions, self.u, self.skipped = summarized([FIXTURES / "cycles"], self.ledger)

    def test_every_cycle_reproduces_the_clients_own_total(self):
        self.assertEqual([s["name"] for s in self.u["sessions"]],
                         ["claude-c1.jsonl", "codex-c1.jsonl", "grok-c1.jsonl"])
        for s in self.u["sessions"]:
            with self.subTest(s["name"]):
                self.assertEqual({k: s[k] for k in rows.COUNTS}, cycle.own_total(FIXTURES / "cycles" / s["name"]))
                self.assertEqual(s["short_by"], {})
        # the kept records are read through their cycles, never a second time as sessions of their own
        self.assertEqual(self.skipped, 1)          # calls.jsonl: no reader takes a row from a ledger

    def test_turns_fixed_and_unplaced_add_up_to_the_total(self):
        self.assertEqual(parts(self.u), {k: self.u["total"][k] for k in KEYS})
        every = [r for s in self.sessions for r in s["usage"]]
        self.assertEqual({k: self.u["total"][k] for k in KEYS}, rows.total(every))
        self.assertIsNone(self.u["unplaced"])
        self.assertEqual(sum(c["requests"] for c in self.u["clients"]), self.u["total"]["requests"])

    def test_a_request_goes_to_the_report_turn_of_its_calls(self):
        groups = join.turn_groups(self.ledger)[0]
        for i, t in self.u["turns"].items():
            labels = {r["client"] for r in groups[i]["rows"]}
            mine = [p for s in self.sessions for p in s["placed"] if p["where"] == "turn"
                    and s["label"] in labels and any(r in groups[i]["rows"] for r in s["groups"][p["group"]]["rows"])]
            self.assertEqual(t["requests"], len(mine))

    def test_the_client_lines_measure_tokens_per_reply_byte(self):
        by = {c["client"]: c for c in self.u["clients"]}
        self.assertEqual(set(by), {"claude/sonnet", "codex/gpt-6.1-sol", "grok/grok-4.6"})
        for c in by.values():
            self.assertGreater(c["reply_bytes"], 0)
            self.assertGreater(c["fresh_in"], 0)
            self.assertLessEqual(c["turn_read"] + c["fixed"], report.read_in(c))
        self.assertEqual(by["codex/gpt-6.1-sol"]["reply_bytes"],
                         sum(r["bytes"] for r in self.ledger if r["client"] == "codex/gpt-6.1-sol"))

    def test_an_unlisted_model_prints_no_dollar_figure_anywhere(self):
        # the Grok CLI's model is on no public price list: the fixture's cycle is the live case
        self.assertEqual(self.u["prices"]["unlisted"], ["grok-4.6-build"])
        self.assertNotIn("cost", self.u["total"])
        grok = next(c for c in self.u["clients"] if c["client"] == "grok/grok-4.6")
        self.assertNotIn("cost", grok)
        self.assertIn("cost", next(c for c in self.u["clients"] if c["client"] == "codex/gpt-6.1-sol"))
        text = run(str(FIXTURES / "cycles" / "calls.jsonl"), "--usage", str(FIXTURES / "cycles" / "grok-c1.jsonl"))
        self.assertNotIn("$0", text)
        self.assertNotRegex(text, r"\d\.\d\d\s*$|est \$\d")
        self.assertNotIn("est $:", text)
        self.assertIn("no list price, so no dollar figure: grok-4.6-build", text)
        js = run(str(FIXTURES / "cycles" / "calls.jsonl"), "--usage", str(FIXTURES / "cycles" / "grok-c1.jsonl"),
                 "--json")
        self.assertNotIn('"cost"', js)

    def test_the_table_carries_the_usage_columns(self):
        text = run(str(FIXTURES / "cycles" / "calls.jsonl"), "--usage", str(FIXTURES / "cycles"))
        head, *lines = text.splitlines()
        for col in ("req", "new in", "cached", "out", "think", "est $"):
            self.assertIn(col, head)
        total = next(line for line in lines if line.startswith("total"))
        t = self.u["total"]
        self.assertEqual(total.split()[1:], [str(t["requests"]), str(t["new_in"] + t["cache_write"]),
                                             str(t["cache_read"]), str(t["out"]), str(t["reasoning"])])
        self.assertIn("sessions: 3 equal to the client's own total, 0 differ", text)
        self.assertIn("new input tokens per reply byte (bytes / 4 says 0.25)", text)
        self.assertIn("a subscription pays no per-token price", text)

    def test_without_usage_the_report_is_the_ledgers_alone(self):
        text = run(str(FIXTURES / "cycles" / "calls.jsonl"))
        self.assertNotIn("req", text.splitlines()[0])
        self.assertNotIn("usage", text)
        for line in run(str(FIXTURES / "cycles" / "calls.jsonl"), "--json").splitlines():
            self.assertNotIn("usage", json.loads(line))

    def test_the_client_filter_keeps_that_clients_sessions(self):
        js = run(str(FIXTURES / "cycles" / "calls.jsonl"), "--usage", str(FIXTURES / "cycles"), "--client", "codex",
                 "--json").splitlines()
        u = json.loads(js[-1])["usage"]
        self.assertEqual([s["name"] for s in u["sessions"]], ["codex-c1.jsonl"])
        self.assertEqual({k: u["total"][k] for k in rows.COUNTS}, cycle.own_total(FIXTURES / "cycles" / "codex-c1.jsonl"))


class SessionReportTests(unittest.TestCase):
    """A Codex session of eleven turns, a bare rollout with no cycle header: the label is found in the ledger."""

    def setUp(self):
        self.ledger = ledger("session/calls.jsonl")
        self.sessions, self.u, _ = summarized([FIXTURES / "session" / "codex-rollout.jsonl"], self.ledger)

    def test_the_label_is_the_one_whose_rows_match(self):
        self.assertEqual(self.sessions[0]["label"], "codex/gpt-6.1-sol")
        stranger = [{**r, "client": "someone/else", "tool": "notebook", "action": "recall"} for r in self.ledger[:5]]
        sessions, _ = report.read([FIXTURES / "session" / "codex-rollout.jsonl"])
        report.place(sessions, stranger + self.ledger)
        self.assertEqual(sessions[0]["label"], "codex/gpt-6.1-sol")

    def test_the_json_lines_add_up_to_the_rollouts_own_total(self):
        js = [json.loads(line) for line in run(str(FIXTURES / "session" / "calls.jsonl"), "--usage",
                                               str(FIXTURES / "session"), "--json").splitlines()]
        turns, u = js[:-1], js[-1]["usage"]
        own = codex.thread_total((FIXTURES / "session" / "codex-rollout.jsonl").read_text().splitlines())
        got = {k: sum(t["usage"][k] for t in turns if "usage" in t) + (u["fixed"] or {}).get(k, 0)
               + (u["unplaced"] or {}).get(k, 0) for k in rows.COUNTS}
        self.assertEqual(got, own)
        self.assertEqual({k: u["total"][k] for k in rows.COUNTS}, own)
        self.assertEqual(sum(1 for t in turns if "usage" in t), 13)        # t26 to t38
        self.assertAlmostEqual(sum(t["usage"]["cost"] for t in turns if "usage" in t) + u["fixed"]["cost"],
                               u["total"]["cost"], places=3)

    def test_a_ledger_that_does_not_cover_the_session_leaves_it_unplaced_and_whole(self):
        sessions, u, _ = summarized([FIXTURES / "session" / "codex-rollout.jsonl"], [])
        self.assertIsNone(sessions[0]["label"])
        self.assertEqual(u["turns"], {})
        self.assertEqual(parts(u), {k: u["total"][k] for k in KEYS})
        self.assertEqual({k: u["total"][k] for k in KEYS}, {k: self.u["total"][k] for k in KEYS})
        self.assertEqual(u["clients"][0]["reply_bytes"], 0)


class SourceTests(unittest.TestCase):
    def test_an_old_codex_cycle_finds_its_rollout_among_the_paths_given(self):
        """A cycle from before the loop kept the record: only the exec stream is in the log directory, and the
        rollout lies in the client's own directory under the stream's thread id."""
        stream = (FIXTURES / "cycles" / "codex-c1.jsonl").read_text().splitlines()
        thread = cycle.session_id(stream, {})
        self.assertTrue(thread)
        with tempfile.TemporaryDirectory() as d:
            logs, home = Path(d) / "night", Path(d) / "codex" / "sessions" / "2026" / "11" / "13"
            logs.mkdir()
            home.mkdir(parents=True)
            kept = [line for line in stream if '"seat_loop.' not in line]          # no header: an old stream
            (logs / "codex-c7.jsonl").write_text("\n".join(kept) + "\n")
            shutil.copy(FIXTURES / "cycles" / "codex-c1.rollout.jsonl", home / f"rollout-2026-11-13-{thread}.jsonl")
            alone, _ = report.read([logs])
            self.assertEqual(alone[0]["usage"], [])
            sessions, skipped = report.read([logs, Path(d) / "codex"])
            self.assertEqual((len(sessions), skipped), (1, 0))
            s = sessions[0]
            self.assertEqual({k: rows.total(s["usage"])[k] for k in rows.COUNTS}, s["own"])
            self.assertEqual(report.short_by(s), {})
            # no header, so no label: the ledger says who it was
            report.place(sessions, ledger("cycles/calls.jsonl"))
            self.assertEqual(s["label"], "codex/gpt-6.1-sol")
            self.assertEqual(sum(p["matched"] for p in s["placed"]), sum(len(p["calls"]) for p in s["placed"]))

    def test_a_session_without_a_civ5_call_is_left_out(self):
        with tempfile.TemporaryDirectory() as d:
            lines = (FIXTURES / "grok-stream.jsonl").read_text().splitlines()
            quiet = [line for line in lines if "civ5__" not in line]
            (Path(d) / "other.jsonl").write_text("\n".join(quiet) + "\n")
            sessions, skipped = report.read([d])
            self.assertEqual((sessions, skipped), ([], 1))

    def test_the_clients_own_file_of_a_cycle_is_that_cycle_again(self):
        """`--usage logs --usage ~/.codex/sessions` is how a running cycle is read per request; once the loop
        has kept its copy, the rollout in the client's directory is the same requests a second time (#189)."""
        with tempfile.TemporaryDirectory() as d:
            logs, home = Path(d) / "logs", Path(d) / "codex" / "2026" / "11" / "13"
            shutil.copytree(FIXTURES / "cycles", logs)
            home.mkdir(parents=True)
            head, _ = cycle.read(logs / "codex-c1.jsonl")
            shutil.copy(logs / "codex-c1.rollout.jsonl",
                        home / f"rollout-2026-11-13T22-55-48-{head.get('session') or 'thread'}.jsonl")
            alone, _ = report.read([logs])
            both, skipped = report.read([logs, Path(d) / "codex"])
            self.assertEqual([s["name"] for s in both], [s["name"] for s in alone])
            self.assertEqual(skipped, 1)                    # the ledger in the log directory, as before
            self.assertEqual(rows.total(r for s in both for r in s["usage"]),
                             rows.total(r for s in alone for r in s["usage"]))

    def test_every_request_is_on_one_seat_and_the_seats_add_up(self):
        calls = ledger("cycles/calls.jsonl")
        for r in calls:
            if r["client"] == "grok/grok-4.6":
                r["seat"] = 1
        sessions, _ = report.read([FIXTURES / "cycles"])
        for s in sessions:                                   # the loop's header says which seat a cycle played
            if s["head"]["agent"] == "grok":
                s["head"]["seat"] = 1
                for r in s["usage"]:
                    r["seat"] = 1
        report.place(sessions, calls)
        u = report.summary(sessions, join.turn_groups(calls)[0], prices.load())
        self.assertEqual([s["seat"] for s in u["seats"]], [0, 1])
        self.assertEqual({k: sum(s[k] for s in u["seats"]) for k in KEYS}, {k: u["total"][k] for k in KEYS})
        grok_cycle = next(s for s in sessions if s["head"]["agent"] == "grok")
        self.assertEqual({k: u["seats"][1][k] for k in KEYS}, rows.total(grok_cycle["usage"]),
                         "a seat's line holds its sessions whole: the fixed part too")
        self.assertEqual(u["seats"][1]["clients"], [{"client": "grok/grok-4.6", "model": "grok-4.6-build"}])
        self.assertIn("cost", u["seats"][0])
        self.assertNotIn("cost", u["seats"][1])
        lines = R.usage_footer(u, 0)
        self.assertTrue(any(line.startswith("usage seat 0 [claude/sonnet, codex/gpt-6.1-sol]: ") and "est $" in line
                            for line in lines), lines)
        self.assertTrue(any(re.match(r"usage seat 1 \[grok/grok-4\.6\]: \d+ requests, \d+ read \(.* from cache\), "
                                     r"\d+ written\Z", line) for line in lines), lines)

    def test_a_bare_session_is_on_the_seat_its_calls_were_made_from(self):
        calls = ledger("session/calls.jsonl")
        sessions, u, _ = summarized([FIXTURES / "session" / "codex-rollout.jsonl"], calls)
        self.assertEqual(sessions[0]["head"], {})
        seat = calls[0]["seat"]
        self.assertEqual(report.session_seat(sessions[0]), seat)
        self.assertIsNotNone(u["fixed"])
        self.assertEqual([(s["seat"], s["requests"]) for s in u["seats"]], [(seat, u["total"]["requests"])])
        # with no ledger at all the requests are on no seat
        report.place(sessions, [])
        self.assertIsNone(report.session_seat(sessions[0]))
        nowhere = report.summary(sessions, [], prices.load())
        self.assertEqual([(s["seat"], s["requests"]) for s in nowhere["seats"]], [(None, u["total"]["requests"])])
        self.assertTrue(any(line.startswith("usage on no seat [") for line in R.usage_footer(nowhere, 0)))

    def test_what_the_client_counted_beyond_its_rows_is_a_line_of_its_own(self):
        s = {"usage": [rows.row(t=1.0, client="c", model="m", session="s", request="1",
                                counts={"new_in": 10, "out": 5}, source="x")],
             "own": {"new_in": 25, "cache_read": 0, "cache_write": 0, "out": 9, "reasoning": 0}}
        self.assertEqual(report.short_by(s), {"new_in": 15, "out": 4})
        self.assertIsNone(report.short_by({**s, "own": None}))
        u = {"total": {"requests": 1, "new_in": 10, "cache_read": 0, "cache_write": 0, "out": 5, "reasoning": 0},
             "fixed": None, "unplaced": None, "turns": {}, "clients": [], "seats": [],
             "prices": {"as_of": "x", "unlisted": []},
             "sessions": [{"name": "a.jsonl", "client": None, "models": ["m"], "requests": 1, "new_in": 10,
                           "cache_read": 0, "cache_write": 0, "out": 5, "reasoning": 0, "short_by": {"new_in": 15, "out": 4}}]}
        lines = R.usage_footer(u, 0)
        self.assertIn("sessions: 0 equal to the client's own total, 1 differ, 0 with no total of the client's", lines)
        self.assertTrue(any(re.search(r"a\.jsonl: .*new_in \+15, out \+4", line) for line in lines))
        self.assertEqual(u["total"]["new_in"], 10)          # the difference is in no sum


if __name__ == "__main__":
    unittest.main()
