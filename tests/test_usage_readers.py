"""Token accounting, stages 0 and 1 (docs/TOKEN_ACCOUNTING.md; GitLab #183, #184): the usage row, the three
clients' readers, and the fixtures cut from real files down to numbers."""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

from harness.usage import claude_code, codex, grok, rows

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "usage"
sys.path.insert(0, str(ROOT / "scripts"))
import cut_usage_fixture as CUT  # noqa: E402


def lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text(encoding="utf-8").splitlines()


def J(o: dict) -> str:
    return json.dumps(o)


def counts(total: dict) -> dict:
    return {k: total[k] for k in rows.COUNTS}


class FixtureTotalsTests(unittest.TestCase):
    """Each fixture reads to the totals counted by hand, which are also the client's own (rule 4: nothing
    dropped, nothing twice). The literals were taken from the clients' total rows, not from the readers."""

    def test_claude_code_session(self):
        got = claude_code.read(lines("claude-code-transcript.jsonl"))
        self.assertEqual(rows.total(got), {"requests": 68, "new_in": 138, "cache_read": 11884780,
                                           "cache_write": 219313, "out": 77416, "reasoning": 26873})
        # 139 rows on file, 138 of them assistant rows for 68 requests: a request is written once per content block
        self.assertEqual(sum(1 for x in lines("claude-code-transcript.jsonl") if '"assistant"' in x), 138)
        own = claude_code.session_total(lines("claude-code-transcript.jsonl"))
        self.assertEqual(counts(rows.total(got)), own["claude-fable-5-2"])
        self.assertEqual(sum(len(r["calls"]) for r in got), 9)
        self.assertIn({"tool": "turn", "action": "status"}, [c for r in got for c in r["calls"]])
        self.assertEqual({(r["client"], r["model"], r["session"], r["source"]) for r in got},
                         {("claude-code/2.1.319", "claude-fable-5-2", "session-1", "claude-code-transcript")})
        self.assertTrue(all(isinstance(r["t"], float) for r in got))
        self.assertEqual([r["t"] for r in got], sorted(r["t"] for r in got))

    def test_codex_rollout_and_its_exec_stream(self):
        got = codex.read(lines("codex-rollout.jsonl"))
        want = {"new_in": 140866, "cache_read": 5797120, "cache_write": 0, "out": 9038, "reasoning": 2325}
        self.assertEqual(rows.total(got), {"requests": 107, **want})
        # the same cycle three ways: the per-request rows, the rollout's running total, the exec stream's one total
        # (5,937,986 input tokens there, of which 5,797,120 cached)
        self.assertEqual(codex.thread_total(lines("codex-rollout.jsonl")), want)
        self.assertEqual(codex.exec_total(lines("codex-exec.jsonl")), want)
        self.assertEqual(sum(len(r["calls"]) for r in got), 72)
        self.assertEqual(sum(1 for x in lines("codex-exec.jsonl") if "mcp_tool_call" in x), 72)
        self.assertEqual({(r["client"], r["model"], r["session"]) for r in got}, {("codex/0.157.1", "gpt-5.6-terra", "session-1")})
        # an old tool name is labelled as the call it means, as a ledger row labels it
        self.assertEqual(got[1]["calls"], [{"tool": "turn", "action": "briefing"}])

    def test_grok_stream(self):
        got = grok.read(lines("grok-stream.jsonl"))
        want = {"new_in": 189288, "cache_read": 8370432, "cache_write": 0, "out": 20317, "reasoning": 11944}
        self.assertEqual(rows.total(got), {"requests": 78, **want})
        self.assertEqual(grok.total(lines("grok-stream.jsonl")), want)
        self.assertEqual(sum(len(r["calls"]) for r in got), 108)
        self.assertEqual({(r["model"], r["session"], r["t"]) for r in got}, {("grok-4.7-build", "session-1", None)})
        self.assertEqual([r["request"] for r in got], [str(i) for i in range(78)])


class FixtureHoldsNoTextTests(unittest.TestCase):
    """The repository is public and a transcript is not: a fixture carries counts, ids, names and times only."""

    KEYS = {
        "type", "timestamp", "t", "version", "requestId", "sessionId", "message", "id", "model", "usage", "content",
        "name", "input", "modelUsage", "payload", "cli_version", "originator", "session_id", "response_id",
        "thread_token_usage", "item", "server", "tool", "arguments", "status", "thread_id", "toolName", "rawInput",
        "tool_name", "tool_input", "output_tokens_details", *rows.ACTION_ARGS,
        *CUT.CLAUDE_USAGE, *CUT.CLAUDE_TOTAL, *CUT.CODEX_USAGE, *CUT.GROK_USAGE, *CUT.GROK_TOTAL, "thinking_tokens",
        "duration", "secs", "nanos",                                             # when a Codex call started
        *CUT.LOOP_NUMBERS, *CUT.LOOP_WORDS, "session",                           # the seat loop's two rows
        *CUT.LEDGER_NUMBERS, *CUT.LEDGER_WORDS, *CUT.LEDGER_FLAGS}               # a call ledger row, cut
    MODEL = re.compile(r"[a-z0-9.-]{3,40}\Z")

    def walk(self, o, path, under_model_usage=False):
        if isinstance(o, dict):
            for k, v in o.items():
                if under_model_usage:
                    self.assertRegex(k, self.MODEL, path)
                else:
                    self.assertIn(k, self.KEYS, path)
                self.walk(v, f"{path}.{k}", under_model_usage=(k == "modelUsage"))
        elif isinstance(o, list):
            for v in o:
                self.walk(v, path)
        elif isinstance(o, str):
            self.assertRegex(o, rows.WORD, path)       # one word of at most 80 characters: no sentence fits
        else:
            self.assertTrue(o is None or isinstance(o, (int, float)), path)

    def test_every_key_is_listed_and_every_string_is_one_word(self):
        files = sorted(FIXTURES.rglob("*.jsonl"))
        self.assertEqual([str(f.relative_to(FIXTURES)) for f in files], [
            "claude-code-transcript.jsonl", "codex-exec.jsonl", "codex-rollout.jsonl",
            "cycles/calls.jsonl", "cycles/claude-c1.jsonl", "cycles/claude-c1.transcript.jsonl", "cycles/codex-c1.jsonl",
            "cycles/codex-c1.rollout.jsonl", "cycles/grok-c1.jsonl", "grok-stream.jsonl",
            "session/calls.jsonl", "session/codex-rollout.jsonl"])
        self.assertEqual([f.name for f in FIXTURES.rglob("*") if f.is_file() and f.suffix != ".jsonl"], ["README.md"])
        for f in files:
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                self.walk(json.loads(line), f"{f.name}:{n}")

    def test_a_ledger_row_is_cut_down_to_its_label_and_numbers(self):
        raw = [J({"t": 1794632371.5, "seat": 0, "tool": "order", "action": "civ/propose_deal", "kind": "write", "bytes": 135,
                  "seconds": 3.342, "trips": 9, "ok": False, "client": "codex/gpt-6.1-sol", "turn": 243,
                  "turn_inferred": True, "err": "Rome will not take that", "excerpt": "{\"ok\":false}",
                  "args": "{\"gold\":200}", "scope": "act", "refs": [1, 2]})]
        out = CUT.cut("ledger", raw)
        self.assertEqual(json.loads(out[0]), {
            "t": 1794632371.5, "seat": 0, "bytes": 135, "seconds": 3.342, "trips": 9, "turn": 243, "tool": "order",
            "action": "civ/propose_deal", "kind": "write", "client": "codex/gpt-6.1-sol", "ok": False,
            "turn_inferred": True})

    def test_the_cut_leaves_the_words_behind(self):
        secret = "the plan is to take Rome by sea"
        raw = [J({"type": "assistant", "requestId": "req_1", "sessionId": "s", "timestamp": "2026-11-13T22:41:36.195Z",
                  "version": "2.1.319", "cwd": "/home/someone",
                  "message": {"id": "msg_1", "model": "claude-fable-5-2",
                              "usage": {"input_tokens": 2, "output_tokens": 9, "service_tier": "standard"},
                              "content": [{"type": "thinking", "thinking": secret},
                                          {"type": "tool_use", "id": "toolu_1", "name": "mcp__civ5__notebook",
                                           "input": {"action": "remember", "text": secret}},
                                          {"type": "tool_use", "id": "toolu_2", "name": "Bash", "input": {"command": secret}}]}}),
               J({"type": "user", "message": {"role": "user", "content": secret}})]
        out = CUT.cut("claude-code", raw)
        self.assertEqual(len(out), 1)
        text = "\n".join(out)
        for gone in ("Rome", "req_1", "msg_1", "toolu_1", "someone", "Bash", "standard"):
            self.assertNotIn(gone, text)
        self.assertEqual(claude_code.read(out)[0]["calls"], [{"tool": "notebook", "action": "remember"}])

    def test_the_cut_is_refused_when_it_would_read_differently(self):
        # a model name that is not one word cannot be kept, so the cut row would lose it: refused, not written
        raw = [J({"type": "assistant", "requestId": "r", "message": {"model": "two words", "usage": {"input_tokens": 1}}})]
        with self.assertRaises(SystemExit):
            CUT.cut("claude-code", raw)


class ClaudeCodeTests(unittest.TestCase):
    def row(self, request, usage, content=(), ts="2026-11-13T22:41:36.000Z", **more):
        return J({"type": "assistant", "requestId": request, "sessionId": "s1", "timestamp": ts, "version": "2.1.319",
                  "message": {"model": "claude-fable-5-2", "usage": usage, "content": list(content)}, **more})

    def test_a_request_written_once_per_block_is_counted_once(self):
        u = {"input_tokens": 2, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 30, "output_tokens": 50,
             "output_tokens_details": {"thinking_tokens": 20}}
        call = {"type": "tool_use", "id": "t1", "name": "mcp__civ5__state", "input": {"what": "unit", "view": "tactical", "id": 7}}
        got = claude_code.read([self.row("r1", u, [{"type": "thinking"}]),
                                self.row("r1", u, [call], ts="2026-11-13T22:41:38.500Z"),
                                self.row("r1", u, [call], ts="2026-11-13T22:41:37.000Z"),      # the same block again
                                self.row("r2", {"input_tokens": 5, "output_tokens": 1})])
        self.assertEqual(rows.total(got), {"requests": 2, "new_in": 7, "cache_read": 100, "cache_write": 30, "out": 51, "reasoning": 20})
        self.assertEqual(got[0]["calls"], [{"tool": "state", "action": "unit/tactical"}])
        self.assertEqual(got[0]["t"], rows.epoch("2026-11-13T22:41:38.500Z"))                   # the latest row's time

    def test_what_is_not_a_request_or_not_a_civ5_call_is_passed_over(self):
        other = {"type": "tool_use", "id": "t2", "name": "mcp__other__state", "input": {"what": "units"}}
        got = claude_code.read([
            self.row("r1", {"input_tokens": 1, "output_tokens": 1}, [other, {"type": "tool_use", "id": "t3", "name": "Bash"}]),
            J({"type": "assistant", "requestId": "r9", "message": {"model": "<synthetic>", "usage": {"input_tokens": 0}}}),
            J({"type": "user", "message": {"role": "user", "content": "hello"}}),
            '{"type": "assistant", "requestId": "r3", "message": {"usage": {"input_tok',       # a torn last line
            "not json at all"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["calls"], [])
        self.assertEqual(claude_code.read([self.row("r1", {"input_tokens": 1}, [other])], server="other")[0]["calls"],
                         [{"tool": "state", "action": "units"}])

    def test_no_cost_state_row_is_no_total(self):
        self.assertEqual(claude_code.session_total([self.row("r1", {"input_tokens": 1})]), {})


class CodexTests(unittest.TestCase):
    def record(self, rid, inp, cached, out=0, reasoning=0, ts="2026-10-31T01:58:46.057Z"):
        u = {"input_tokens": inp, "cached_input_tokens": cached, "cache_write_input_tokens": 0, "output_tokens": out,
             "reasoning_output_tokens": reasoning}
        return J({"timestamp": ts, "type": "token_usage_record", "payload": {"session_id": "s1", "response_id": rid, "usage": u,
                                                                               "thread_token_usage": u}})

    def call(self, tool, server="civ5", **arguments):
        return J({"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "McpToolCall", "server": server,
                                                                                    "tool": tool, "arguments": arguments}}})

    def test_the_cached_part_is_inside_input_tokens(self):
        got = codex.read([self.record("resp_1", 17523, 12032, out=100)])
        self.assertEqual(counts(got[0]), {"new_in": 5491, "cache_read": 12032, "cache_write": 0, "out": 100, "reasoning": 0})
        self.assertEqual(got[0]["t"], rows.epoch("2026-10-31T01:58:46.057Z"))

    def test_a_call_belongs_to_the_response_before_it_and_the_model_to_the_records_after_it(self):
        got = codex.read([self.call("state", what="units"),                                # before any response: nobody's
                          J({"type": "session_meta", "payload": {"id": "s1", "cli_version": "0.166.0"}}),
                          J({"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}}),
                          self.record("resp_1", 10, 0), self.call("state", what="units"), self.call("x", server="other"),
                          self.record("resp_1", 10, 0),                                    # the same response again
                          J({"type": "turn_context", "payload": {"model": "gpt-6.1-luna"}}),
                          self.record("resp_2", 20, 5), self.call("turn", action="finish"), self.call("turn", action="status")])
        self.assertEqual([(r["request"], r["model"], r["client"]) for r in got],
                         [("resp_1", "gpt-6.1-sol", "codex/0.166.0"), ("resp_2", "gpt-6.1-luna", "codex/0.166.0")])
        self.assertEqual(got[0]["calls"], [{"tool": "state", "action": "units"}])
        self.assertEqual(got[1]["calls"], [{"tool": "turn", "action": "finish"}, {"tool": "turn", "action": "status"}])

    def script(self, ts):
        return J({"timestamp": ts, "type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
                                                                        "input": "await tools.civ5.state()"}})

    def timed(self, tool, ts, secs=0.0, **arguments):
        return J({"timestamp": ts, "type": "event_msg", "payload": {"type": "item_completed", "item": {
            "type": "McpToolCall", "server": "civ5", "tool": tool, "arguments": arguments,
            "duration": {"secs": int(secs), "nanos": int(secs % 1 * 1e9)}}}})

    def test_a_call_that_ran_before_its_responses_record_was_written_is_still_that_responses(self):
        # live 2026-11-13: the script row at .66, its first call done at .76, the response's record at .81
        got = codex.read([self.record("resp_1", 10, 0, ts="2026-11-13T23:52:20.710Z"),
                          self.script("2026-11-13T23:52:21.660Z"),
                          self.timed("state", "2026-11-13T23:52:21.760Z", 0.09, what="unit", view="tactical"),
                          self.record("resp_2", 20, 0, ts="2026-11-13T23:52:21.810Z"),
                          self.timed("state", "2026-11-13T23:52:21.880Z", 0.06, what="map", view="window")])
        self.assertEqual([r["calls"] for r in got], [[], [{"tool": "state", "action": "unit/tactical"},
                                                          {"tool": "state", "action": "map/window"}]])

    def test_a_call_that_outlasts_its_response_stays_with_the_script_that_made_it(self):
        # resp_1's script ends the turn; the model polls (a `wait`, no script) and then writes another script
        # while the long call is still out: it started before that script was written, so it is resp_1's
        got = codex.read([self.script("2026-11-13T23:00:00.000Z"), self.record("resp_1", 10, 0, ts="2026-11-13T23:00:00.100Z"),
                          self.record("resp_2", 10, 0, ts="2026-11-13T23:00:30.000Z"),
                          self.script("2026-11-13T23:00:40.000Z"),
                          self.timed("turn", "2026-11-13T23:00:41.000Z", 40.8, action="finish"),
                          self.record("resp_3", 10, 0, ts="2026-11-13T23:00:41.100Z"),
                          self.timed("state", "2026-11-13T23:00:41.500Z", 0.2, what="units")])
        self.assertEqual([[c["action"] for c in r["calls"]] for r in got], [["finish"], [], ["units"]])

    def test_a_script_whose_response_never_got_a_record_gives_its_calls_to_no_row(self):
        got = codex.read([self.record("resp_1", 10, 0, ts="2026-11-13T23:00:00.000Z"), self.script("2026-11-13T23:00:05.000Z"),
                          self.timed("state", "2026-11-13T23:00:05.300Z", 0.1, what="units")])     # killed here
        self.assertEqual(got[0]["calls"], [])

    def test_totals_of_a_file_that_has_none(self):
        self.assertIsNone(codex.thread_total(['{"type": "session_meta", "payload": {}}']))
        self.assertIsNone(codex.exec_total(['{"type": "turn.started"}']))
        two = [J({"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 1}})] * 2
        self.assertEqual(codex.exec_total(two), {"new_in": 12, "cache_read": 8, "cache_write": 0, "out": 2, "reasoning": 0})


class GrokTests(unittest.TestCase):
    USAGE = {"input_tokens": 2035, "output_tokens": 40, "cache_read_input_tokens": 27648, "cache_creation_input_tokens": 0,
             "reasoning_tokens": 6}

    def use(self, tool_name, **tool_input):
        return J({"type": "tool_call", "toolName": "use_tool", "rawInput": {"tool_name": tool_name, "tool_input": tool_input}})

    def test_calls_follow_their_usage_event_and_the_end_row_names_the_model(self):
        got = grok.read([self.use("civ5__turn", action="status"),                           # before any response: nobody's
                         J({"type": "usage", "usage": self.USAGE, "signature": "x"}), J({"type": "thought", "data": "hm"}),
                         self.use("civ5__order", to="unit", action="move", id=3, args={"x": 1}),
                         J({"type": "tool_call", "toolName": "read_file", "rawInput": {"target_file": "/tmp/x"}}),
                         J({"type": "tool_call", "toolName": "mcp__civ5__state", "rawInput": {"what": "league"}}),
                         J({"type": "usage", "usage": self.USAGE}),
                         J({"type": "end", "sessionId": "abc", "usage": {}, "modelUsage": {"grok-4.7-build": {}}})])
        self.assertEqual([r["calls"] for r in got], [[{"tool": "order", "action": "unit/move"}, {"tool": "state", "action": "league"}], []])
        self.assertEqual(counts(got[0]), {"new_in": 2035, "cache_read": 27648, "cache_write": 0, "out": 40, "reasoning": 6})
        self.assertEqual({(r["model"], r["session"], r["t"]) for r in got}, {("grok-4.7-build", "abc", None)})

    def test_a_stamped_line_gives_the_time_and_a_cut_off_stream_keeps_its_rows(self):
        got = grok.read([J({"type": "usage", "t": 1794612894.2, "usage": self.USAGE})])
        self.assertEqual((got[0]["t"], got[0]["model"], got[0]["session"]), (1794612894.2, None, None))
        self.assertIsNone(grok.total([J({"type": "usage", "usage": self.USAGE})]))
        self.assertEqual(grok.read([J({"type": "usage", "usage": self.USAGE})], model="grok-4.7")[0]["model"], "grok-4.7")


class RowTests(unittest.TestCase):
    def test_only_the_label_bearing_arguments_are_read(self):
        self.assertEqual(rows.action_args({"what": "city", "view": "production", "id": 5, "text": "a note", "to": "two words",
                                           "choice": 2, "action": True}), {"what": "city", "view": "production", "choice": 2})
        self.assertEqual(rows.action_args("not a dict"), {})

    def test_names_of_other_servers_are_not_calls(self):
        self.assertEqual(rows.bare_name("mcp__civ5__state"), "state")
        self.assertEqual(rows.bare_name("civ5__state"), "state")
        for name in ("mcp__civ5__", "mcp__civ6__state", "state", "Bash", None, 7):
            self.assertIsNone(rows.bare_name(name))

    def test_times(self):
        self.assertEqual(rows.epoch("1970-01-01T00:00:01.500Z"), 1.5)
        self.assertEqual(rows.epoch(12), 12.0)
        for bad in ("yesterday", None, True):
            self.assertIsNone(rows.epoch(bad))


if __name__ == "__main__":
    unittest.main()
