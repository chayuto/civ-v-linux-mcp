"""The relationship a leader's screen carries is the lean one (#191): nothing false, nothing said twice."""
import json
import unittest

from harness.affordances.questions import discussion_answers
from harness.game_parts.diplomacy import relationship_inline

SPEECH = "It is hard to find worthy friends in this world. What do you say?"

# The read of Korea on the Maya t243 board (bench191, v341), as H.relationship returned it less `relations`.
SEJONG = {
    "ok": True, "player": 7, "civ": "Korea", "leader": "Sejong", "minor": False, "human": False, "at_war": False,
    "turns_locked_in_war": 0, "approach_guess": "MAJOR_CIV_APPROACH_FRIENDLY", "declaration_of_friendship": False,
    "they_denounced_us": False, "we_denounced_them": False, "our_embassy_with_them": True,
    "their_embassy_with_us": True, "open_borders_we_have": True, "open_borders_they_have": True,
    "research_agreement": True, "defensive_pact": False, "wars_fought": 0,
    "opinion": ["You have both chosen to adopt the Order Ideology.", "They have an embassy in your capital."],
    "discuss": {"declare_friendship": True, "stop_digging": False, "stop_spreading_religion": False,
                "share_intrigue": False, "dont_settle": True, "stop_spying": True},
    "history": [{"turn": 240, "state": "DIPLO_UI_STATE_BLANK_DISCUSSION", "text": "Greetings."},
                {"turn": 243, "state": "DIPLO_UI_STATE_DISCUSS_WORK_WITH_US", "text": SPEECH}],
}


class RelationshipInlineTest(unittest.TestCase):
    def setUp(self):
        self.r = relationship_inline(SEJONG, SPEECH)

    def test_what_the_screen_names_is_not_repeated(self):
        for k in ("ok", "player", "leader"):
            self.assertNotIn(k, self.r)
        self.assertEqual(self.r["civ"], "Korea")

    def test_a_false_flag_and_a_zero_counter_are_absent(self):
        for k in ("minor", "human", "at_war", "declaration_of_friendship", "they_denounced_us",
                  "we_denounced_them", "defensive_pact", "turns_locked_in_war", "wars_fought"):
            self.assertNotIn(k, self.r)

    def test_what_is_true_stays(self):
        for k in ("our_embassy_with_them", "their_embassy_with_us", "open_borders_we_have",
                  "open_borders_they_have", "research_agreement"):
            self.assertIs(self.r[k], True)
        self.assertEqual(self.r["approach_guess"], "MAJOR_CIV_APPROACH_FRIENDLY")
        self.assertEqual(self.r["opinion"], SEJONG["opinion"])

    def test_discuss_is_the_list_of_open_asks(self):
        self.assertEqual(self.r["discuss"], ["declare_friendship", "dont_settle", "stop_spying"])

    def test_no_open_ask_is_no_discuss_key(self):
        rel = dict(SEJONG, discuss=dict.fromkeys(SEJONG["discuss"], False))
        self.assertNotIn("discuss", relationship_inline(rel, SPEECH))

    def test_the_speech_is_not_said_twice_and_the_state_stays(self):
        self.assertEqual(self.r["history"], [
            {"turn": 240, "state": "DIPLO_UI_STATE_BLANK_DISCUSSION", "text": "Greetings."},
            {"turn": 243, "state": "DIPLO_UI_STATE_DISCUSS_WORK_WITH_US"}])

    def test_other_words_than_the_speech_stay(self):
        r = relationship_inline(SEJONG, "Something else.")
        self.assertEqual(r["history"][-1]["text"], SPEECH)

    def test_a_human_and_a_war_are_said(self):
        r = relationship_inline(dict(SEJONG, human=True, at_war=True, turns_locked_in_war=4, wars_fought=1))
        self.assertIs(r["human"], True)
        self.assertIs(r["at_war"], True)
        self.assertEqual((r["turns_locked_in_war"], r["wars_fought"]), (4, 1))

    def test_a_failed_read_is_untouched(self):
        bad = {"ok": False, "err": "not met"}
        self.assertEqual(relationship_inline(bad), bad)
        self.assertIsNone(relationship_inline(None))

    def test_the_source_is_not_changed(self):
        before = json.dumps(SEJONG, sort_keys=True)
        relationship_inline(SEJONG, SPEECH)
        self.assertEqual(json.dumps(SEJONG, sort_keys=True), before)

    def test_it_is_at_most_two_thirds_of_the_read(self):
        self.assertLess(len(json.dumps(self.r)), len(json.dumps(SEJONG)) * 2 / 3)

    def test_the_friendship_answer_still_finds_its_state(self):
        screen = {"pending": True, "screen": "discussion", "player": 7, "speech": SPEECH,
                  "buttons": [{"id": 1, "disabled": False, "text": "Yes."}], "relationship": self.r}
        self.assertIn("accept_friendship", json.dumps(discussion_answers(screen)))


if __name__ == "__main__":
    unittest.main()
