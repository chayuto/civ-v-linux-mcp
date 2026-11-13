"""Where a unit can end this turn's move: the tactical view's `reach` (2026-11-13).

A human selecting a unit sees every plot it can reach this turn lit up; the view gave the six neighbours only, so an
agent planning a two-move step guessed the second one. The engine's pathfinder is closed to Lua (GeneratePath NYI,
Plot:MovementCost crashes the game), so `reach` walks step_cost.lua's one-step rule outward, most moves left first.
These tests pin the walk on the tactical view's mocked 8 x 5 wrapped map (tests/test_tactical_view.py WORLD), unit at
(2,2): NE (2,3), E (3,2), SE (2,1), SW (1,1), W (1,2), NW (1,3). Beyond them: (0,2) touches W alone, (4,2) touches E
alone, (3,3) touches NE and E.
"""
import unittest

import test_mcp_safety as support
from test_tactical_step_cost import COSTS
from test_tactical_view import WORLD


HELPERS = r"""
function reach_of(v)
  local by = {}
  for _, r in ipairs(v.reach.plots or {}) do by[r[1] .. ',' .. r[2]] = r[3] end
  return by
end
function view() return H.tactical_view(1, 0, 2, 'summary') end
"""


class ReachTests(unittest.TestCase):
    run_lua = support.LuaRuntimeTests.run_lua

    def setUp(self):
        support.LuaRuntimeTests.setUp(self)
        self.run_lua(WORLD)
        self.run_lua(COSTS)
        self.run_lua(HELPERS)

    def test_open_ground_is_every_plot_within_the_moves(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)                              -- a Warrior with 2 moves
        local v = view()
        local by = reach_of(v)
        assert(v.reach.moves == 2 and v.reach.next_turn == nil and v.reach.capped == nil, H.json(v.reach))
        assert(#v.reach.plots == 18, 'six neighbours and the twelve behind them: ' .. #v.reach.plots)
        for _, n in ipairs(v.neighbors) do
          assert(by[n.x .. ',' .. n.y] == n.left, 'a neighbour reads as its own row does: ' .. H.json(n))
        end
        assert(by['0,2'] == 0 and by['4,2'] == 0 and by['3,3'] == 0, 'the second ring arrives with none: ' .. H.json(by))
        assert(by['2,2'] == nil, 'the plot it stands on is not a destination')
        assert(by['5,2'] == nil, 'three steps away')
        assert(v.reach.plots[1][3] == 1 and v.reach.plots[18][3] == 0, 'nearest first')
        assert(H.json(v.reach):find('%[1,2,1%]'), 'a row is [x, y, moves left]: ' .. H.json(v.reach))
        """)

    def test_zone_of_control_ends_the_move_along_the_way(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2, { moves = 4 })
        u.MaxMoves = function() return 240 end
        local by = reach_of(view())
        assert(by['4,3'] == 1, 'three open steps with four moves: ' .. tostring(by['4,3']))
        unit(7, 63, 2, 4, 2)                             -- a Brute at (4,2): next to (3,2), (3,3) and (4,3)
        by = reach_of(view())
        assert(by['4,2'] == nil, 'a plot an enemy holds is an attack, not a destination')
        assert(by['3,2'] == 3, 'stepping next to it from outside its reach costs the terrain: ' .. tostring(by['3,2']))
        assert(by['3,3'] == 2, 'reached from NE, which the Brute does not touch: ' .. tostring(by['3,3']))
        assert(by['4,3'] == 0, 'from (3,3) to (4,3) is one zone-of-control plot to another: ' .. tostring(by['4,3']))
        """)

    def test_a_neighbour_says_what_the_order_does_when_the_pathfinder_goes_around(self):
        """Live combat-lab t266: a Musketman's E neighbour read left 0 under a Warrior's zone of control, reach said
        0.67 by the road behind, and the move order arrived with 0.67 -- the engine paths around."""
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2, { moves = 3 })
        u.MaxMoves = function() return 180 end
        unit(7, 63, 2, 3, 2)                             -- a Brute on E: NE (2,3) and SE (2,1) are in its reach
        local v = view()
        local by, ne = reach_of(v), nil
        for _, n in ipairs(v.neighbors) do if n.dir == 'NE' then ne = n end end
        assert(by['2,3'] == 1, 'by NW (1,3), which the Brute does not touch: ' .. tostring(by['2,3']))
        assert(ne.left == 1 and ne.cost == 2 and ne.detour == true, H.json(ne))
        assert(ne.zoc and ne.zoc.id == 7, 'the direct step is still explained: ' .. H.json(ne))
        for _, n in ipairs(v.neighbors) do
          if n.dir == 'W' then assert(n.detour == nil and n.left == 2, 'a plain step is not a detour: ' .. H.json(n)) end
        end
        """)

    def test_a_river_crossing_spends_every_move(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        P['2,2'].o.w_of_river = true                     -- the river on the unit's east edge
        local by = reach_of(view())
        assert(by['3,2'] == 0, 'across the river with nothing left: ' .. tostring(by['3,2']))
        assert(by['4,2'] == nil, '(4,2) lies behind E alone: ' .. tostring(by['4,2']))
        assert(by['0,2'] == 0, 'the other side is untouched')
        """)

    def test_my_own_unit_is_passed_through_but_not_a_place_to_stop(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        unit(2, 0, 1, 1, 2)                              -- my other Warrior on W
        local v = view()
        local by = reach_of(v)
        assert(by['1,2'] == nil, 'one combat unit per tile: ' .. H.json(by))
        assert(by['0,2'] == 0, 'the plot behind it is reached through it: ' .. H.json(by))
        assert(#v.reach.plots == 17)
        """)

    def test_closed_borders_and_unrevealed_plots_are_not_walked(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        P['1,2'].o.owner = 3                             -- Persia's land, no open borders
        local by = reach_of(view())
        assert(by['1,2'] == nil and by['0,2'] == nil, 'closed borders: ' .. H.json(by))
        P['1,2'].o.owner = nil
        P['1,2'].o.revealed = false
        by = reach_of(view())
        assert(by['1,2'] == nil and by['0,2'] == nil, 'never through a plot that was never seen: ' .. H.json(by))
        """)

    def test_a_fogged_plot_is_priced_as_last_seen_and_named(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        plot(1, 2, { fog = true })                       -- live reads on it raise
        local v = view()
        local by = reach_of(v)
        assert(by['1,2'] == 1 and by['0,2'] == 0, H.json(by))
        assert(#v.reach.fogged == 1 and v.reach.fogged[1][1] == 1 and v.reach.fogged[1][2] == 2, H.json(v.reach.fogged))
        """)

    def test_embarking_ends_the_move_and_a_unit_that_cannot_embark_stays_ashore(self):
        self.run_lua("""
        unit(1, 0, 1, 2, 2)
        plot(1, 2, { water = true }); plot(0, 2, { water = true })
        local by = reach_of(view())
        assert(by['1,2'] == nil and by['0,2'] == nil, 'no Optics: ' .. H.json(by))
        Teams[0].CanEmbark = function() return true end
        by = reach_of(view())
        assert(by['1,2'] == 0, 'embarking spends every move: ' .. tostring(by['1,2']))
        assert(by['0,2'] == nil, 'so the water behind it is next turn: ' .. tostring(by['0,2']))
        """)

    def test_two_embarked_units_never_share_a_plot(self):
        """Live combat-lab t266: reach listed the water plot a Worker had embarked onto for an Infantry; the engine
        counts every embarked unit as one class and left the Infantry where it stood."""
        self.run_lua("""
        Teams[0].CanEmbark = function() return true end
        local u = unit(1, 0, 1, 2, 2)
        plot(1, 2, { water = true })
        GameInfo.Units[4].Description = 'Worker'
        unit(9, 0, 4, 1, 2, { civilian = true })         -- my Worker, embarked on W
        local by = reach_of(view())
        assert(by['1,2'] == nil, 'a civilian afloat keeps a combat unit out: ' .. H.json(by))
        local r = H.move_refusal(u, P['1,2'], 0, true)
        assert(r and r.err:find('embarked WORKER 9', 1, true) and r.blocking_unit.id == 9, H.json(r))
        assert(H.move_refusal(u, P['1,2'], 0, true, true) == nil, 'passing through it is fine')
        plot(1, 2)                                       -- the same pair on land shares the plot
        unit(9, 0, 4, 1, 2, { civilian = true })
        assert(H.move_refusal(u, P['1,2'], 0, true) == nil)
        """)

    def test_deep_ocean_needs_the_tech(self):
        self.run_lua("""
        GameInfoTypes.TERRAIN_OCEAN = 2
        GameInfo.Terrains[2] = { Type = 'TERRAIN_OCEAN', Movement = 1 }
        local techs = { { ID = 7, EmbarkedAllWaterPassage = true } }
        GameInfo.Technologies = function() local i = 0; return function() i = i + 1; return techs[i] end end
        GameInfo.UnitPromotions = function() return function() return nil end end
        Teams[0].CanEmbark = function() return true end
        Teams[0].IsHasTech = function() return false end
        local u = unit(1, 0, 1, 2, 2)
        u.IsEmbarked = function() return true end
        plot(2, 2, { water = true }).o.units = { u }
        plot(1, 2, { water = true })
        plot(3, 2, { water = true }).GetTerrainType = function() return 2 end
        local by = reach_of(view())
        assert(by['1,2'] == 1, 'coast: ' .. H.json(by))
        assert(by['3,2'] == nil, 'ocean before Astronomy: ' .. H.json(by))
        Teams[0].IsHasTech = function(_, t) return t == 7 end
        by = reach_of(view())
        assert(by['3,2'] == 1, 'ocean with it: ' .. H.json(by))
        """)

    def test_no_moves_left_reads_next_turn_and_a_trade_unit_reads_nothing(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2, { moves = 0 })
        local v = view()
        assert(v.reach.next_turn == true and v.reach.moves == 2 and #v.reach.plots == 18, H.json(v.reach))
        u.IsTrade = function() return true end
        assert(view().reach == nil, 'a caravan follows its route')
        """)

    def test_the_distance_cap_is_said(self):
        self.run_lua("""
        local u = unit(1, 0, 1, 2, 2, { moves = 9 })
        u.MaxMoves = function() return 540 end
        local v = view()
        assert(#v.reach.plots == 39 and v.reach.capped == nil, 'the whole 8 x 5 map lies within six plots: ' .. #v.reach.plots)
        Map.PlotDistance = function(...) return hexdist(...) * 2 end   -- every plot twice as far: the ring is at 3
        v = view()
        local by = reach_of(v)
        assert(v.reach.capped == true, 'the walk stopped at the ring and says so: ' .. H.json(v.reach))
        assert(by['5,2'] == 6 and by['6,2'] == nil, 'three steps in, four out: ' .. H.json(by))
        """)


if __name__ == "__main__":
    unittest.main()
