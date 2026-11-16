"""Token accounting, stage 3 (docs/TOKEN_ACCOUNTING.md; GitLab #186): the join of usage rows and ledger rows.

The test of the stage: every request lands in exactly one turn, in `fixed` or in `unplaced`, and the per-turn
sums are the session's total, which is the client's own."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from harness import call_ledger
from harness.usage import codex, cycle, join, rows

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "usage"


def ledger(name: str) -> list[dict]:
    return list(rows.parsed((FIXTURES / name).read_text(encoding="utf-8").splitlines()))


def sums(per_turn: list[dict]) -> dict:
    return {k: sum(x[k] for x in per_turn) for k in ("requests", *rows.COUNTS)}


def U(t, *calls, source="claude-code-transcript", **counts) -> dict:
    """A usage row at time `t` that issued `calls` ("state/units", "turn/finish")."""
    return rows.row(t=t, client="c", model="m", session="s", request=str(t), counts=counts or {"new_in": 1},
                    calls=[dict(zip(("tool", "action"), c.partition("/")[::2])) for c in calls], source=source)


def L(start, label, seconds=0.5, turn=None, ok=True, seat=0, kind=None, client="c") -> dict:
    """A ledger row of a call that began at `start`."""
    tool, _, action = label.partition("/")
    wait = tool in ("finish_turn", "wait_for_my_turn") or (tool == "turn" and action in ("finish", "end", "wait"))
    r = {"t": start + seconds, "seat": seat, "tool": tool, "kind": kind or ("wait" if wait else "read"),
         "bytes": 10, "seconds": seconds, "trips": 1, "ok": ok, "client": client}
    if action:
        r["action"] = action
    if turn is not None:
        r["turn"] = turn
    return r


class CycleFixtureTests(unittest.TestCase):
    """One cycle of each agent, read from the log directory and the ledger alone (live 2026-11-13, Maya t242)."""

    def placed(self, agent):
        stream = FIXTURES / "cycles" / f"{agent}-c1.jsonl"
        head, placed, groups = join.place_cycle(stream, ledger("cycles/calls.jsonl"))
        per_turn = join.per_turn(placed)
        # nothing dropped, nothing twice: the turns add up to the rows, and the rows to the client's own total
        self.assertEqual(sums(per_turn), rows.total(placed))
        self.assertEqual({k: sums(per_turn)[k] for k in rows.COUNTS}, cycle.own_total(stream))
        self.assertTrue(all(p["where"] in ("turn", "fixed") for p in placed))
        # every call of the cycle is a ledger row and every ledger row of the cycle is a call
        self.assertEqual(sum(p["matched"] for p in placed), sum(len(p["calls"]) for p in placed))
        self.assertEqual(sum(p["matched"] for p in placed), sum(len(g["rows"]) for g in groups))
        return head, placed, groups, per_turn

    def test_claude(self):
        _, placed, groups, per_turn = self.placed("claude")
        self.assertEqual([(g["seat"], g["turn"], len(g["rows"])) for g in groups], [(0, 242, 6)])
        # its first request already called `turn briefing`: nothing is `fixed`
        self.assertEqual([(x["where"], x["turn"], x["requests"]) for x in per_turn], [("turn", 242, 9)])
        self.assertEqual([p["matched"] for p in placed], [1, 0, 1, 1, 1, 1, 1, 0, 0])

    def test_codex(self):
        _, placed, groups, per_turn = self.placed("codex")
        self.assertEqual([(g["seat"], g["turn"], len(g["rows"]), g["open"]) for g in groups], [(0, 242, 23, False)])
        self.assertEqual([(x["where"], x["turn"], x["seat"], x["requests"]) for x in per_turn],
                         [("fixed", None, None, 1), ("turn", 242, 0, 10)])
        # the two closing requests (the report, the last word) issued nothing: the turn of the call before them
        self.assertEqual([(p["where"], p["matched"]) for p in placed[-2:]], [("turn", 0), ("turn", 0)])

    def test_grok(self):
        head, placed, _, per_turn = self.placed("grok")
        self.assertEqual([(x["where"], x["turn"], x["requests"]) for x in per_turn], [("fixed", None, 1), ("turn", 243, 8)])
        self.assertEqual({(p["label"], p["cycle"]) for p in placed}, {(head["client"], 1)})

    def test_a_cycle_whose_label_the_ledger_does_not_know_is_fixed_and_unplaced(self):
        _, placed, groups = join.place_cycle(FIXTURES / "cycles" / "grok-c1.jsonl", ledger("session/calls.jsonl"))
        self.assertEqual(groups, [])
        self.assertEqual([p["where"] for p in placed], ["fixed"] + ["unplaced"] * 8)
        self.assertEqual(sums(join.per_turn(placed)), rows.total(placed))


class SessionFixtureTests(unittest.TestCase):
    """A Codex session outside the seat loop: thirteen turns (t26 to t38), 69 calls, the ledger of the same hour."""

    def test_every_request_lands_in_one_turn_and_the_turns_add_up_to_the_sessions_own_total(self):
        lines = (FIXTURES / "session" / "codex-rollout.jsonl").read_text(encoding="utf-8").splitlines()
        usage = codex.read(lines)
        mine = join.ledger_of(ledger("session/calls.jsonl"), "codex/gpt-6.1-sol", usage[0]["t"], usage[-1]["t"] + 600)
        placed, groups = join.place(usage, mine)
        per_turn = join.per_turn(placed)
        self.assertEqual({k: sums(per_turn)[k] for k in rows.COUNTS}, codex.thread_total(lines))
        self.assertEqual(sums(per_turn)["requests"], 68)
        self.assertEqual([(x["where"], x["turn"], x["requests"]) for x in per_turn],
                         [("fixed", None, 1), ("turn", 26, 8), ("turn", 27, 6), ("turn", 28, 4), ("turn", 29, 6),
                          ("turn", 30, 8), ("turn", 31, 4), ("turn", 32, 2), ("turn", 33, 4), ("turn", 34, 3),
                          ("turn", 35, 4), ("turn", 36, 2), ("turn", 37, 2), ("turn", 38, 14)])     # 36 and 37: a finish each
        self.assertEqual(sum(p["matched"] for p in placed), 69)
        self.assertEqual(sum(len(g["rows"]) for g in groups), 69)
        self.assertEqual([g["turn"] for g in groups], list(range(26, 39)))
        self.assertEqual([g["open"] for g in groups], [False] * 12 + [True])
        self.assertEqual([p["group"] for p in placed if p["where"] == "turn"],
                         sorted(p["group"] for p in placed if p["where"] == "turn"))        # turns never run backwards


class PlaceTests(unittest.TestCase):
    def test_a_request_is_of_the_turn_of_its_first_call_and_one_without_a_call_of_the_call_before_it(self):
        book = [L(10, "state/units", turn=5), L(20, "turn/finish", seconds=30, turn=6), L(51, "state/units", turn=6),
                L(70, "turn/finish", seconds=5, turn=7)]
        usage = [U(1), U(9, "state/units"), U(19, "turn/finish", "state/units", source=codex.SOURCE),   # a script: ends 5, reads 6
                 U(60), U(69, "turn/finish"), U(80)]
        placed, groups = join.place(usage, book)
        self.assertEqual([(g["turn"], len(g["rows"])) for g in groups], [(5, 2), (6, 2)])
        self.assertEqual([(p["where"], p["turn"], p["matched"]) for p in placed],
                         [("fixed", None, 0), ("turn", 5, 1), ("turn", 5, 2), ("turn", 6, 0), ("turn", 6, 1), ("turn", 6, 0)])
        self.assertEqual([(x["where"], x["turn"], x["requests"]) for x in join.per_turn(placed)],
                         [("fixed", None, 1), ("turn", 5, 2), ("turn", 6, 3)])

    def test_a_call_the_ledger_does_not_hold_places_nothing(self):
        # a tool name that does not exist never reached the server (Grok, 2026-11-13): no ledger row
        placed, _ = join.place([U(1, "nonexistent"), U(2, "state/units"), U(3, "nonexistent"), U(4)],
                               [L(2.1, "state/units", turn=9)])
        self.assertEqual([(p["where"], p["turn"], p["matched"]) for p in placed],
                         [("unplaced", None, 0), ("turn", 9, 1), ("turn", 9, 0), ("turn", 9, 0)])

    def test_with_no_ledger_a_session_is_fixed_until_its_first_call_and_unplaced_after(self):
        placed, groups = join.place([U(1), U(2, "state/units"), U(3)], [])
        self.assertEqual(groups, [])
        self.assertEqual([p["where"] for p in placed], ["fixed", "unplaced", "unplaced"])
        self.assertEqual([(x["where"], x["group"], x["requests"]) for x in join.per_turn(placed)],
                         [("fixed", None, 1), ("unplaced", None, 2)])

    def test_calls_of_one_request_ran_side_by_side_and_match_in_any_order(self):
        book = [L(5.3, "notebook/recall", turn=3), L(5.1, "reference/playbook", turn=3), L(5.2, "turn/briefing", turn=3)]
        placed, _ = join.place([U(5, "turn/briefing", "notebook/recall", "reference/playbook")], book)
        self.assertEqual(placed[0]["matched"], 3)

    def test_the_same_label_twice_is_taken_in_order_and_never_twice(self):
        book = [L(2, "state/units", turn=1), L(3, "turn/finish", turn=2), L(12, "state/units", turn=2)]
        hits = join.match([U(1, "state/units"), U(2.9, "turn/finish"), U(11, "state/units"), U(13, "state/units")], book)
        self.assertEqual([[h and h["t"] for h in hs] for hs in hits], [[2.5], [3.5], [12.5], [None]])

    def test_a_call_is_not_matched_to_a_row_from_before_its_request_or_from_after_the_next(self):
        # the ledger missed the first request's call; the row of the same label is the third request's
        usage = [U(100, "state/units"), U(110), U(200, "state/units")]
        hits = join.match(usage, [L(201, "state/units", turn=4)])
        self.assertEqual([[h is not None for h in hs] for hs in hits], [[False], [], [True]])
        # and a row that began well before the request was complete is another session's
        self.assertEqual(join.match([U(100, "state/units")], [L(50, "state/units")]), [[None]])
        # a Codex script outlives its response: the model polls twice while `finish` waits, then the script reads on
        slow = [U(100, "turn/finish", "state/units", source=codex.SOURCE), U(130, source=codex.SOURCE),
                U(160, source=codex.SOURCE)]
        placed, _ = join.place(slow, [L(100.2, "turn/finish", seconds=90, turn=8), L(190.5, "state/units", turn=8)])
        self.assertEqual([p["matched"] for p in placed], [2, 0, 0])

    def test_rows_without_a_time_are_matched_by_order_alone(self):
        book = [L(10, "state/units", turn=1), L(20, "turn/finish", turn=2), L(30, "state/units", turn=2)]
        placed, _ = join.place([U(None), U(None, "state/units"), U(None, "turn/finish"), U(None, "state/units")], book)
        self.assertEqual([(p["where"], p["turn"]) for p in placed], [("fixed", None), ("turn", 1), ("turn", 1), ("turn", 2)])

    def test_a_ledger_row_in_an_older_vocabulary_is_the_call_it_means_now(self):
        book = [L(2, "inspect/cities", turn=1), L(3, "tactical_view", turn=1), L(4, "finish_turn", turn=2), L(9, "batch")]
        self.assertEqual([join.label(r) for r in book],
                         [("state", "cities"), ("state", "unit/tactical"), ("turn", "finish"), ("batch", "")])
        placed, _ = join.place([U(1, "state/cities", "state/unit/tactical"), U(3.9, "turn/finish"), U(8, "batch/")], book)
        self.assertEqual([p["matched"] for p in placed], [2, 1, 1])

    def test_two_seats_of_one_client_are_grouped_apart(self):
        book = [L(1, "state/units", turn=7, seat=0), L(2, "state/units", turn=7, seat=1), L(3, "turn/finish", turn=8, seat=0),
                L(4, "state/cities", turn=7, seat=1), L(5, "state/cities", turn=8, seat=0)]
        placed, groups = join.place([U(0.5, "state/units"), U(1.5, "state/units"), U(2.5, "turn/finish"), U(3.5, "state/cities"),
                                     U(4.5, "state/cities")], book)
        self.assertEqual([(g["seat"], g["turn"], len(g["rows"])) for g in groups], [(0, 7, 2), (1, 7, 2), (0, 8, 1)])
        self.assertEqual([(p["seat"], p["turn"]) for p in placed], [(0, 7), (1, 7), (0, 7), (1, 7), (0, 8)])
        self.assertEqual([(x["seat"], x["turn"], x["requests"]) for x in join.per_turn(placed)], [(0, 7, 2), (1, 7, 2), (0, 8, 1)])

    def test_a_placed_row_is_a_copy(self):
        usage = [U(1, "state/units")]
        placed, _ = join.place(usage, [L(1.5, "state/units", turn=2)])
        self.assertNotIn("where", usage[0])
        self.assertEqual({k: placed[0][k] for k in ("where", "group", "turn", "seat", "matched")},
                         {"where": "turn", "group": 0, "turn": 2, "seat": 0, "matched": 1})


class LedgerOfTests(unittest.TestCase):
    def test_one_clients_rows_inside_the_window(self):
        book = [L(10, "state/units", client="a"), L(10, "state/units", client="b"), L(95, "turn/finish", seconds=60, client="a"),
                L(500, "state/units", client="a"), L(20, "state/units", client="a", seat=1), L(30, "state/units", client=None)]
        self.assertEqual([r["t"] for r in join.ledger_of(book, "a", 9, 100)], [10.5, 155, 20.5])      # began inside: kept
        self.assertEqual([r["t"] for r in join.ledger_of(book, "a", 9, 100, seat=1)], [20.5])
        self.assertEqual(len(join.ledger_of(book, "a")), 4)
        self.assertEqual(join.ledger_of(book, "nobody"), [])


class TurnGroupsTests(unittest.TestCase):
    def test_the_grouping_the_report_and_the_join_share(self):
        book = [L(1, "state/units", turn=4), L(2, "turn/finish", ok=False, turn=4), L(3, "turn/finish", turn=5),
                L(4, "turn/wait", turn=5), L(5, "notebook/recall"), L(6, "turn/finish", turn=6), L(7, "state/units")]
        got = call_ledger.turn_groups(book)
        # a refused finish leaves the turn open; a wait after the one that succeeded is the same turn; a turn none of
        # whose reads names a number takes the one the wait before it returned
        self.assertEqual([(g["turn"], len(g["rows"]), g["open"]) for g in got], [(4, 4, False), (5, 2, False), (6, 1, True)])
        self.assertEqual(call_ledger.turn_groups([]), [])
        self.assertEqual(json.loads(json.dumps([g["turn"] for g in got])), [4, 5, 6])

    def shape(self, book):
        return [(g["turn"], [r.get("action", "") for r in g["rows"]], g["open"]) for g in call_ledger.turn_groups(book)]

    def test_a_wait_that_came_back_at_its_own_turn_did_not_end_it(self):
        """A leader's screen stops the wait: the answers and the next wait are still that turn (the bench cycles
        of 2026-11-15 were ten turns in 18 to 20 groups)."""
        book = [L(1, "state/units", turn=243), L(2, "turn/finish", turn=243), L(3, "question/", turn=243),
                L(4, "answer/1", turn=243), L(5, "turn/wait", turn=243), L(6, "question/", turn=243),
                L(7, "answer/accept", turn=243), L(8, "turn/wait", turn=244), L(9, "state/units", turn=244),
                L(10, "turn/finish", turn=244), L(11, "answer/leave", turn=244)]
        self.assertEqual(self.shape(book), [
            (243, ["units", "finish", "", "1", "wait", "", "accept", "wait"], False),
            (244, ["units", "finish", "leave"], True)])               # stopped again, and the ledger ends there

    def test_a_turn_with_nothing_to_do_but_end_it_is_a_turn(self):
        book = [L(1, "state/units", turn=35), L(2, "turn/finish", turn=36), L(3, "turn/wait", turn=36),
                L(4, "turn/finish", turn=37), L(5, "turn/finish", turn=38), L(6, "state/units", turn=38)]
        self.assertEqual(self.shape(book), [(35, ["units", "finish", "wait"], False), (36, ["finish"], False),
                                            (37, ["finish"], False), (38, ["units"], True)])

    def test_a_call_at_another_turn_with_no_wait_in_between_starts_a_turn(self):
        # the turn came round while a leader's screen was being answered: the refused finish already says 94
        book = [L(1, "state/units", turn=93), L(2, "turn/finish", turn=93), L(3, "answer/1", turn=93),
                L(4, "turn/finish", ok=False, turn=94), L(5, "order/unit", turn=94), L(6, "turn/finish", turn=95),
                L(7, "turn/finish", ok=False, turn=95), L(8, "state/units", turn=95),
                L(9, "state/units", turn=242), L(10, "turn/finish", turn=243)]          # a save was loaded
        self.assertEqual(self.shape(book), [(93, ["units", "finish", "1"], False), (94, ["finish", "unit", "finish"], False),
                                            (95, ["finish", "units"], False), (242, ["units", "finish"], False)])

    def test_rows_without_a_turn_fall_back_to_the_wait_alone(self):
        book = [L(1, "state/units"), L(2, "turn/finish"), L(3, "turn/wait"), L(4, "state/units"), L(5, "turn/finish"),
                L(6, "turn/finish")]
        self.assertEqual(self.shape(book), [(None, ["units", "finish", "wait"], False),
                                            (None, ["units", "finish", "finish"], False)])


if __name__ == "__main__":
    unittest.main()
