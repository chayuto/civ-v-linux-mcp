"""turn_digest keeps the newest DIGEST_MAX_EVENTS events and says what it cut (live t192: 350 rows / 75 KB)."""
import unittest

from harness.game import Game
from harness.game_parts.events import DIGEST_MAX_EVENTS


def game_with_events(events):
    g = Game.__new__(Game)
    g.seat = 0
    g._pid = lambda pid=None: 0
    g.q = lambda body, timeout=None: list(events) if "take_events" in body else []
    return g


class DigestCapTests(unittest.TestCase):
    def test_under_the_cap_nothing_is_cut(self):
        ev = [{"kind": "notification", "turn": 10, "seq": i, "audience": 0, "data": {"text": f"n{i}"}} for i in range(5)]
        out = game_with_events(ev).turn_digest()
        self.assertEqual(len(out["events"]), 5)
        self.assertNotIn("omitted", out)

    def test_a_row_carries_nothing_a_seat_cannot_use(self):
        """#191: `audience` is always the reader, a notification's `ntype` is a hash and `d1` / `d2` raw engine words."""
        ev = [{"kind": "notification", "turn": 10, "seq": 7, "audience": 0,
               "data": {"text": "Uxmal has Grown!", "summary": "Uxmal Grows", "id": 3, "ntype": 1319111517, "d1": 8192,
                        "d2": -1, "player": 0, "city_id": 8192, "x": 4, "y": 5}},
              {"kind": "turn_start", "turn": 10, "seq": 8, "audience": 0, "data": {"d1": "kept: not a notification"}}]
        note, other = game_with_events(ev).turn_digest()["events"]
        self.assertEqual(note, {"kind": "notification", "turn": 10, "seq": 7,
                                "data": {"text": "Uxmal has Grown!", "summary": "Uxmal Grows", "id": 3, "player": 0,
                                         "city_id": 8192, "x": 4, "y": 5}})
        self.assertEqual(other, {"kind": "turn_start", "turn": 10, "seq": 8, "data": {"d1": "kept: not a notification"}})

    def test_over_the_cap_keeps_the_newest_and_counts_the_rest(self):
        n = DIGEST_MAX_EVENTS + 30
        ev = [{"kind": "notification" if i % 2 else "turn_start", "turn": 163 + i // 12, "seq": i + 1, "audience": 0,
               "data": {"text": f"n{i}"}} for i in range(n)]
        out = game_with_events(ev).turn_digest()
        self.assertEqual(len(out["events"]), DIGEST_MAX_EVENTS)
        self.assertEqual(out["events"][-1]["seq"], n, "the newest rows are the ones kept")
        om = out["omitted"]
        self.assertEqual(om["count"], 30)
        self.assertEqual(om["turns"], [163, 163 + 29 // 12])
        self.assertEqual(sum(om["by_kind"].values()), 30)
        self.assertIn("state(what='notifications')", om["hint"])


if __name__ == "__main__":
    unittest.main()
