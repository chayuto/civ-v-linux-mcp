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
        """#191: `audience` is always the reader, a notification's `ntype` is a hash, `d1` / `d2` raw engine words,
        `id` a panel number no call takes and `player` the reader again."""
        ev = [{"kind": "notification", "turn": 10, "seq": 7, "audience": 0,
               "data": {"text": "Uxmal has Grown!", "summary": "Uxmal Grows", "id": 3, "ntype": 1319111517, "d1": 8192,
                        "d2": -1, "player": 0, "city_id": 8192, "x": 4, "y": 5}},
              {"kind": "alert", "turn": 10, "seq": 8, "audience": 0, "data": {"d1": "kept: not a notification"}}]
        note, other = game_with_events(ev).turn_digest()["events"]
        self.assertEqual(note, {"kind": "notification", "turn": 10, "seq": 7,
                                "data": {"text": "Uxmal has Grown!", "summary": "Uxmal Grows",
                                         "city_id": 8192, "x": 4, "y": 5}})
        self.assertEqual(other, {"kind": "alert", "turn": 10, "seq": 8, "data": {"d1": "kept: not a notification"}})

    def test_a_title_the_text_opens_with_is_said_once(self):
        def row(summary, text):
            ev = [{"kind": "notification", "turn": 10, "seq": 1, "audience": 0, "data": {"summary": summary, "text": text}}]
            return game_with_events(ev).turn_digest()["events"][0]["data"]
        same = "Sejong has completed Manhattan Project!"
        self.assertEqual(row(same, same), {"text": same})
        self.assertEqual(row("ENACT: Arts Funding", "ENACT: Arts Funding was passed by the World Congress."),
                         {"text": "ENACT: Arts Funding was passed by the World Congress."})
        self.assertEqual(row("Portugal has Denounced You!", "Portugal has publicly denounced YOU."),
                         {"summary": "Portugal has Denounced You!", "text": "Portugal has publicly denounced YOU."})
        self.assertEqual(row("Only a title", ""), {"summary": "Only a title", "text": ""})

    def test_the_runtime_s_bookkeeping_makes_no_row(self):
        """#191: a turn starting or ending and a unit's model rebuilt are the runtime's own markers (the briefing
        never listed them); a digest of nothing else is empty."""
        ev = [{"kind": k, "turn": 10, "seq": i, "audience": 0, "data": {"player": 0}}
              for i, k in enumerate(("turn_end", "active_player", "turn_start", "unit_graphics_reset"), 1)]
        self.assertEqual(game_with_events(ev).turn_digest()["events"], [])
        ev.append({"kind": "unit_lost", "turn": 10, "seq": 9, "audience": 0, "data": {"player": 0, "unit": "CARAVAN"}})
        self.assertEqual([e["kind"] for e in game_with_events(ev).turn_digest()["events"]], ["unit_lost"])

    def test_a_popup_is_its_name(self):
        ev = [{"kind": "popup_shown", "turn": 10, "seq": 1, "audience": 0, "data": {"name": "BUTTONPOPUP_NEW_ERA", "type": 55}}]
        self.assertEqual(game_with_events(ev).turn_digest()["events"][0]["data"], {"name": "BUTTONPOPUP_NEW_ERA"})

    def test_the_cap_counts_the_rows_a_seat_reads(self):
        ev = [{"kind": "notification" if i % 2 else "turn_start", "turn": 163, "seq": i + 1, "audience": 0,
               "data": {"text": f"n{i}"}} for i in range(DIGEST_MAX_EVENTS + 30)]
        out = game_with_events(ev).turn_digest()
        self.assertEqual(len(out["events"]), (DIGEST_MAX_EVENTS + 30) // 2)
        self.assertNotIn("omitted", out)

    def test_over_the_cap_keeps_the_newest_and_counts_the_rest(self):
        n = DIGEST_MAX_EVENTS + 30
        ev = [{"kind": "notification" if i % 2 else "alert", "turn": 163 + i // 12, "seq": i + 1, "audience": 0,
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
