"""question() on an AI's offer named nobody: the scratch deal read `from: 0, to: 1` (the engine puts the active
player first) and the civ's name, the leader and the line that came with the offer were only in turn status
(live Maya t237, 2026-11-13: Portugal's research agreement). The table read now says who sits across it."""
from __future__ import annotations

import unittest

from harness.client import TunerdError
from harness.game import Game


def _game(deal, rel):
    g = Game.__new__(Game)
    g.seat = 0
    g._runtime_ok = True
    g.h = lambda name, *a, **kw: name
    g.q = lambda code, **kw: dict(deal, items=[dict(i) for i in deal["items"]]) if code == "incoming_deal" else 268
    if isinstance(rel, Exception):
        def relationship(other, pid=None):
            raise rel
        g.relationship = relationship
    else:
        g.relationship = lambda other, pid=None: rel
    return g


DEAL = {"ok": True, "from": 0, "to": 1, "n": 1, "items": [{"type": "GOLD_PER_TURN", "from_us": False, "amount": 3}]}
OFFER = {"state": "DIPLO_UI_STATE_TRADE_AI_MAKES_OFFER", "turn": 237,
         "text": "I feel that a Research Agreement is a mutually beneficial arrangement."}


class IncomingDealNamesTheOtherSideTests(unittest.TestCase):
    def test_the_civ_the_leader_and_the_line_of_the_offer(self):
        r = _game(DEAL, {"ok": True, "civ": "Portugal", "leader": "Maria I", "history": [OFFER]}).incoming_deal()
        self.assertEqual((r["other"], r["civ"], r["leader"]), (1, "Portugal", "Maria I"))
        self.assertEqual((r["speech"], r["speech_turn"]), (OFFER["text"], 237))
        self.assertEqual((r["from"], r["to"]), (0, 1))            # the table's two ends, unchanged

    def test_no_line_when_the_last_exchange_was_not_an_offer(self):
        hist = [OFFER, {"state": "DIPLO_UI_STATE_BLANK_DISCUSSION", "turn": 238, "text": "Farewell."}]
        r = _game(DEAL, {"ok": True, "civ": "Portugal", "leader": "Maria I", "history": hist}).incoming_deal()
        self.assertEqual(r["civ"], "Portugal")
        self.assertNotIn("speech", r)

    def test_a_relationship_read_that_fails_leaves_the_table_as_it_was(self):
        r = _game(DEAL, TunerdError("gone")).incoming_deal()
        self.assertTrue(r["ok"])
        for key in ("other", "civ", "leader", "speech"):
            self.assertNotIn(key, r)


if __name__ == "__main__":
    unittest.main()
