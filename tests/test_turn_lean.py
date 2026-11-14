"""#191: what the reply to a turn boundary leaves out (mcp_tools.turn._lean)."""
import unittest

from harness.mcp_tools.turn import QUIET_FLAGS, _lean


class LeanTests(unittest.TestCase):
    def test_false_flags_go_true_ones_and_the_rest_stay(self):
        st = {**dict.fromkeys(QUIET_FLAGS, False), "discussion_pending": True, "my_turn": False, "alive": True,
              "active_player": 0, "game_state": 0, "pending_popups": [], "happiness": 0, "turn": 242}
        r = _lean({"ok": True, "ended": True, "status": st})
        self.assertEqual(r["status"], {"discussion_pending": True, "my_turn": False, "alive": True, "active_player": 0,
                                       "game_state": 0, "happiness": 0, "turn": 242})

    def test_a_wait_reply_is_its_own_status(self):
        r = _lean({"ok": True, "my_turn": True, "paused": False, "hotseat": True, "pending_popups": ["BUTTONPOPUP_X"]})
        self.assertEqual(r, {"ok": True, "my_turn": True, "hotseat": True, "pending_popups": ["BUTTONPOPUP_X"]})

    def test_a_refused_end_does_not_carry_the_todo_twice(self):
        todo = {"units": [{"id": 7}], "promotions": []}
        r = _lean({"ok": False, "ended": False, "end_turn": {"ok": False, "err": "x", "todo": dict(todo),
                                                             "skip_actions": [1]}, "status": {"todo": todo}})
        self.assertEqual(r["end_turn"], {"ok": False, "err": "x", "todo": "status.todo", "skip_actions": [1]})
        self.assertEqual(r["status"]["todo"], todo)

    def test_a_refusal_with_no_status_keeps_its_todo(self):
        r = _lean({"ok": False, "end_turn": {"ok": False, "todo": {"units": []}}, "my_turn": True})
        self.assertEqual(r["end_turn"]["todo"], {"units": []})


class QuietListTests(unittest.TestCase):
    def test_the_automated_ids_and_the_note_wake_nobody(self):
        from harness.game import Game
        g = Game.__new__(Game)
        g.seat = 0
        ts = {"turn": 5, "todo": {"units": [], "promotions": [], "automated": {"WORKER": [9, 10]}, "ongoing_note": "x"}}
        self.assertEqual(g._wake_reasons(ts, {"events": [], "notifications": []}), [])


if __name__ == "__main__":
    unittest.main()
