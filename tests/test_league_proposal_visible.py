"""The World Congress's call for proposals is visible before finish refuses, and the league read has a compact
form (GitLab #117).

Live Maya t197: the status named PRODUCTION; the proposal blocker surfaced only when finish was refused, and the
league read to pick a proposal was 25 KB of repeated resolution text.
"""
import unittest

import test_mcp_safety as support
from harness.briefing import decisions
from harness.game_parts.diplomacy import DiplomacyMixin, league_compact, league_summary
from harness import affordances as A

WORLD = """
GameDefines = { MOVE_DENOMINATOR = 60 }
GameInfo = GameInfo or {}
GameInfo.Units = {}
LEAGUE = { IsInSession = function() return IN_SESSION end, CanPropose = function(_, pid) return CAN end,
           GetRemainingProposalsForMember = function() return 2 end }
Game.GetNumActiveLeagues = function() return 1 end
Game.GetActiveLeague = function() return LEAGUE end
Game.GetActivePlayer = function() return 0 end
Players = { [0] = { IsTurnActive = function() return true end, GetCurrentResearch = function() return 4 end,
                    Units = function() return function() return nil end end,
                    Cities = function() return function() return nil end end,
                    GetTeam = function() return 0 end, GetEndTurnBlockingType = function() return -1 end } }
H.incoming_deal = function() return nil end
H.religion_choice = function() return nil end
IN_SESSION, CAN = false, true
"""


class LeagueProposalTodoLuaTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)

    def test_a_pending_proposal_is_in_the_todo_whatever_the_blocker_says(self):
        self.run_lua("""
        local t = H.todo(0)
        assert(t.league_proposal and t.league_proposal.remaining == 2, H.json(t))
        assert(t.league_proposal.hint:find('propose', 1, true), t.league_proposal.hint)
        CAN = false
        assert(H.todo(0).league_proposal == nil, 'nothing to propose')
        CAN, IN_SESSION = true, true
        assert(H.todo(0).league_proposal == nil, 'in a session the proposals are closed')
        """)


class LeagueProposalDecisionTests(unittest.TestCase):
    def test_the_decision_row_carries_the_read_and_both_orders_and_the_blocker_is_not_repeated(self):
        ts = {"todo": {"units": [], "cities": [], "league_proposal": {"remaining": 2}},
              "blocking_name": "ENDTURN_BLOCKING_PRODUCTION", "blocking_hint": "x", "pending_popups": []}
        rows = decisions(ts, [])
        lp = [r for r in rows if r["kind"] == "league_proposal"]
        self.assertEqual(len(lp), 1)
        tools = [(a["tool"], a["args"].get("what") or a["args"].get("action")) for a in lp[0]["actions"]]
        self.assertEqual(tools, [("state", "league"), ("order", "propose"), ("order", "repeal")])
        self.assertEqual(lp[0]["actions"][0]["args"].get("detail"), "compact")
        ts["blocking_name"] = "ENDTURN_BLOCKING_LEAGUE_CALL_FOR_PROPOSALS"
        kinds = [r["kind"] for r in decisions(ts, [])]
        self.assertEqual(kinds, ["league_proposal"])


OPINION = ("\n\nCivilizations that would be grateful if we proposed this:\n\u2022 India\n\u2022 China"
           "\n\nCivilizations that would be angry if we proposed this:\n\u2022 Venice")
DONE = {"project": "LEAGUE_PROJECT_WORLD_FAIR", "name": "World's Fair", "process": "PROCESS_WORLD_FAIR", "active": False,
        "complete": True, "progress_percent": 107, "our_contribution": 0, "our_tier": 0, "cost": 2814,
        "details": "This project requires a total of 2,814 Production", "rewards": [{"tier": 1, "text": "Exhibitor"}],
        "contributors": [{"player": 11, "civ": "France", "contribution": 779, "tier": 3}]}
OPEN = {"project": "LEAGUE_PROJECT_WORLD_GAMES", "name": "International Games", "process": "PROCESS_WORLD_GAMES",
        "active": True, "complete": False, "progress_percent": 40, "our_contribution": 150, "our_tier": 0, "cost": 5788,
        "tier_1_at": 241, "details": "Parade of Nations ( 241.2 or more): +3 Happiness.",
        "rewards": [{"tier": 1, "text": "Parade of Nations ( 241.2 or more): +3 Happiness."}]}
BETWEEN = {
    "ok": True, "has_league": True, "in_session": False, "active_effects": ["Host: The Maya"],
    "proposable_enact": [{"resolution_type": "RESOLUTION_BAN_LUXURY", "name": "Ban Luxury",
                          "details": "A Luxury resource is banned." + OPINION, "call": {"tool": "order"},
                          "choices": [{"id": 5, "text": "Wine", "disabled": False, "details": OPINION.strip()}]}],
    "active_resolutions": [{"resolution_id": 1, "name": "Cultural Heritage Sites", "can_repeal": True,
                            "details": "Each World Wonder provides +3 Culture to its city." + OPINION}],
    "proposable_repeal": [{"resolution_id": 1, "name": "Cultural Heritage Sites", "call": {"tool": "order"},
                           "details": "Each World Wonder provides +3 Culture to its city." + OPINION},
                          {"resolution_id": 2, "name": "Not Among The Active", "details": "kept"}],
    "unavailable_enact": [{"resolution_type": "RESOLUTION_DIPLOMATIC_VICTORY", "name": "World Leader",
                           "details": "Designate a World Leader.\n\nMay not be proposed by a Civilization."
                                      "\n\nNot allowed by this game's options."},
                          {"resolution_type": "RESOLUTION_X", "name": "No Tooltip"}],
    "members": [{"player": 9, "civ": "Sweden", "delegates": 22,
                 "details": "Gustavus Adolphus of Sweden commands a total of 22 Delegates. Once in session, the amount "
                            "is fixed until the session ends.\n\u2022 4 from membership\n\nTheir top choices for the "
                            "current proposals:\n\u2022 Yea on ENACT: Ban Luxury: Pearls"},
                {"player": 0, "civ": "The Maya", "delegates": 1, "you": True,
                 "details": "Pacal of The Maya commands a total of 1 Delegate."},
                {"player": 3, "civ": "Assyria", "delegates": 4, "details": "A tooltip worded another way"}],
    "projects": [DONE, OPEN]}


class SummaryLeagueReadTests(unittest.TestCase):
    """The default league read (GitLab #191): what was said twice and what is history go, every fact stays."""

    def setUp(self):
        self.before = repr(BETWEEN)
        self.s = league_summary(BETWEEN)

    def test_the_full_read_is_untouched_and_the_summary_names_itself(self):
        self.assertEqual(repr(BETWEEN), self.before)
        self.assertEqual(self.s["detail"], "summary")
        self.assertIn("detail='full'", self.s["more"])
        self.assertEqual(self.s["active_effects"], ["Host: The Maya"])

    def test_the_grateful_and_angry_paragraphs_are_two_lists_on_a_row_and_on_a_choice(self):
        row = self.s["proposable_enact"][0]
        self.assertEqual(row["details"], "A Luxury resource is banned.")
        self.assertEqual(row["grateful_if_proposed"], ["India", "China"])
        self.assertEqual(row["angry_if_proposed"], ["Venice"])
        self.assertEqual(row["call"], {"tool": "order"})
        self.assertEqual(row["choices"], [{"id": 5, "text": "Wine", "disabled": False,
                                           "grateful_if_proposed": ["India", "China"], "angry_if_proposed": ["Venice"]}])

    def test_a_paragraph_that_is_not_a_heading_over_bullets_stays_as_it_was(self):
        odd = {"details": "What it does.\n\nCivilizations that would be angry if we proposed this: nobody we know"}
        self.assertEqual(league_summary({"ok": True, "votable": [odd]})["votable"], [odd])

    def test_a_repealable_row_leaves_its_details_to_the_active_row(self):
        self.assertEqual(self.s["proposable_repeal"][0],
                         {"resolution_id": 1, "name": "Cultural Heritage Sites", "call": {"tool": "order"}})
        self.assertEqual(self.s["proposable_repeal"][1]["details"], "kept", "no active row holds it")
        self.assertEqual(self.s["active_resolutions"][0]["details"], "Each World Wonder provides +3 Culture to its city.")
        self.assertEqual(self.s["active_resolutions"][0]["angry_if_proposed"], ["Venice"])

    def test_a_greyed_resolution_is_its_name_and_why(self):
        self.assertEqual(self.s["unavailable_enact"],
                         [{"resolution_type": "RESOLUTION_DIPLOMATIC_VICTORY", "name": "World Leader",
                           "why": "Not allowed by this game's options."},
                          {"resolution_type": "RESOLUTION_X", "name": "No Tooltip"}])

    def test_a_member_tooltip_loses_only_the_sentence_its_fields_say(self):
        sweden, maya, assyria = self.s["members"]
        self.assertEqual(sweden["details"], "\u2022 4 from membership\n\nTheir top choices for the current proposals:"
                                            "\n\u2022 Yea on ENACT: Ban Luxury: Pearls")
        self.assertEqual(maya, {"player": 0, "civ": "The Maya", "delegates": 1, "you": True})
        self.assertEqual(assyria["details"], "A tooltip worded another way")

    def test_a_finished_project_is_its_name_and_our_part_and_an_open_one_keeps_its_numbers(self):
        done, open_ = self.s["projects"]
        self.assertEqual(done, {"project": "LEAGUE_PROJECT_WORLD_FAIR", "name": "World's Fair",
                                "process": "PROCESS_WORLD_FAIR", "complete": True, "progress_percent": 107,
                                "our_contribution": 0, "our_tier": 0})
        self.assertEqual(open_, {k: v for k, v in OPEN.items() if k != "details"})

    def test_no_league_and_a_refusal_pass_through(self):
        for r in ({"ok": True, "has_league": False}, {"ok": False, "err": "x"}, None):
            self.assertIs(league_summary(r), r)

    def test_the_read_is_the_summary_unless_full_is_asked_for(self):
        class G(DiplomacyMixin):
            def h(self, *a, **k): return "x"
            def q(self, _): return {"ok": True, "has_league": True, "in_session": False, "members": [], "projects": [DONE]}
        self.assertEqual(G().league_status()["projects"], [DONE], "the library's own callers read it whole")
        self.assertNotIn("detail", G().league_status(detail="full"))
        for word, means in (("summary", "summary"), ("brief", "summary"), ("compact", "compact")):
            r = G().league_status(detail=word)
            self.assertEqual(r["detail"], means)
            self.assertNotIn("rewards", r["projects"][0])


class CompactLeagueReadTests(unittest.TestCase):
    def test_compact_drops_the_repeated_prose_and_keeps_every_id(self):
        r = {"ok": True, "in_session": False, "active_effects": "long text",
             "proposable_enact": [{"resolution_type": "RESOLUTION_BAN_LUXURY", "name": "Ban Luxury", "details": "once",
                                   "choices": [{"id": 5, "text": "Wine", "disabled": False, "details": "a paragraph"},
                                               {"id": 6, "text": "Gems", "disabled": True, "details": "a paragraph"}]}],
             "members": [{"player": 0, "civ": "Maya", "delegates": 4, "details": "Their interests are largely a mystery"}]}
        c = league_compact(r)
        self.assertEqual(c["proposable_enact"][0]["details"], "once")
        self.assertEqual(c["proposable_enact"][0]["choices"], [{"id": 5, "text": "Wine", "disabled": False},
                                                               {"id": 6, "text": "Gems", "disabled": True}])
        self.assertEqual(c["members"], [{"player": 0, "civ": "Maya", "delegates": 4}])
        self.assertNotIn("active_effects", c)
        self.assertEqual(c["detail"], "compact")
        self.assertIn("active_effects", r, "the full read is untouched")

    def test_compact_of_a_summary_has_no_opinion_lists_on_a_choice_and_no_pointer_to_more(self):
        c = league_compact(league_summary(BETWEEN))
        self.assertEqual(c["proposable_enact"][0]["choices"], [{"id": 5, "text": "Wine", "disabled": False}])
        self.assertEqual(c["proposable_enact"][0]["angry_if_proposed"], ["Venice"], "the resolution's own stay")
        self.assertEqual(c["detail"], "compact")
        self.assertNotIn("more", c)

    def test_a_choices_vote_row_says_what_choice_takes(self):
        r = {"ok": True, "in_session": True, "remaining_votes": 4,
             "votable": [{"resolution_id": 9, "direction": "enact", "choices": [{"id": 2, "text": "Maya"}]},
                         {"resolution_id": 10, "direction": "repeal", "yes_no": True}]}
        A.league_rows(r)
        self.assertIn("choices[].id", r["votable"][0]["choice_note"])
        self.assertNotIn("choice_note", r["votable"][1])


if __name__ == "__main__":
    unittest.main()
