"""Run fotz_census.script under LuaJIT 2.0 against a small made-up alife and check what it writes.

The world: eleven squads on two levels and six smarts, with relations that make Bandits and Loners
enemies. Checked: the counts per faction (squads, fighters, tiers, ranks, levels, story squads),
which faction holds each smart and which are contested, the relations and goodwill read, the
JSON (it parses, keys sorted, strings escaped), the daily schedule (the wait after a load, one
census a day, the MCM switch), that an error stays inside the census, and that nothing is written
to the world.

    python test_census.py            the real script
    python test_census.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import json
import os
import shutil
import sys
import tempfile

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "gamedata", "scripts", "fotz_census.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "any_assigned": ("return ok and reached == true", "return true"),
    "unguarded_reach": ("local ok, reached = pcall(function() return s.smrt:am_i_reached(sq) end)",
                        "local ok, reached = true, s.smrt:am_i_reached(sq)"),
    "monster_holds": ('if f ~= "monster" and n > 0', "if n > 0"),
    "always_contested": ("if game_relations.is_factions_enemies(names[i], names[j]) then", "if true then"),
    "tie": ("p[f] > p[best]", "p[f] >= p[best]"),
    "no_wait": ("FIRST_MS = 30000", "FIRST_MS = 0"),
    "every_check": ("if day ~= last_day then", "if true then"),
    "cause": ('local cause = last_day and "day" or "load"', 'local cause = "load"'),
    "unguarded": ("        run(cause)\n", "        take(cause)\n"),
    "always_on": ("return v ~= false", "return true"),
    "story": ("if get_object_story_id(id) then", "if not get_object_story_id(id) then"),
    "monster_ranks": ("if IsStalker(nil, se:clsid()) then", "if true then"),
    "self_relation": ("            if a ~= b then\n", "            if true then\n"),
    "toward_actor": ("community_relation(a, actor_comm)", "community_relation(actor_comm, a)"),
    "unsorted": ("        table.sort(keys)\n", ""),
    "quote": ("if ch == '\"' then return '\\\\\"' end", "if ch == '\"' then return '\"' end"),
    "overwrite": ('io.open(path(), "a")', 'io.open(path(), "w")'),
    "no_front_count": ("                fr.n = fr.n + 1\n", ""),
    "listeners_need_log": ("if not (enabled() or #LISTENERS > 0) then", "if not enabled() then"),
    "write_when_off": ("        if enabled() then\n            local f = assert",
                       "        if true then\n            local f = assert"),
}

WORLD = r"""
LOG = {}
-- the game's printf: it fills %s only, through a function
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end

WRITES = {}
local function wrote(name) return function() WRITES[#WRITES + 1] = name end end
REL = {}
GW = { dolg = 300, bandit = -1200 }
relation_registry = {
    community_relation = function(a, b) return REL[a .. "/" .. b] or 0 end,
    community_goodwill = function(f, id) return id == AC_ID and GW[f] or 0 end,
    set_community_relation = wrote("set_community_relation"),
    set_community_goodwill = wrote("set_community_goodwill"),
    change_community_goodwill = wrote("change_community_goodwill"),
}
REL["bandit/stalker"] = -1500
REL["stalker/bandit"] = -1500
REL["dolg/actor_stalker"] = 700
REL["actor_stalker/dolg"] = -50
game_relations = {
    is_factions_enemies = function(a, b) return relation_registry.community_relation(a, b) <= -1000 end,
}

AC_ID = 0
CLS_STALKER, CLS_MONSTER = 1, 2
function IsStalker(_, cls) return cls == CLS_STALKER end
ranks = { get_se_obj_rank_name = function(se) return se:rank() < 300 and "novice" or "veteran" end }
STORY = {}
function get_object_story_id(id) return STORY[id] end

OBJ = {}
LEVELS = { [1] = "l05_bar", [2] = "l01_escape" }
GV_LEVEL = { [10] = 1, [11] = 1, [12] = 1, [13] = 1, [14] = 1, [20] = 2, [21] = 2, [22] = 2 }
function alife()
    return { object = function(_, id) return OBJ[id] end, level_name = function(_, lid) return LEVELS[lid] end }
end
function game_graph()
    return { vertex = function(_, gv) return { level_id = function() return GV_LEVEL[gv] end } end }
end
DATE = { 2012, 5, 14, 8, 0 }
game = { get_game_time = function()
    return { get = function() return DATE[1], DATE[2], DATE[3], DATE[4], DATE[5], 0, 0 end }
end }
db = { actor = { character_community = function() return "actor_stalker" end } }
NOW = 0
function time_global() return NOW end
MCM = {}
ui_mcm = { get = function(id) return MCM[id] end }
CALLBACKS = {}
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end
function getFS() return { update_path = function(_, root, file) return OUTDIR .. "/" .. file end } end

SIMBOARD = { squads = {}, smarts = {} }
local function npc(id, rank, cls)
    OBJ[id] = { id = id, rank = function() return rank end, clsid = function() return cls or CLS_STALKER end }
end
-- every squad as after a load: current_action and current_target_id are nil (they aren't saved)
local function squad(id, comm, section, gv, members, smart)
    local sq = { id = id, comm = comm, section = section, m_game_vertex_id = gv, members = members,
                 smart_id = smart }
    function sq:get_squad_community() return self.comm end
    function sq:section_name() return self.section end
    function sq:squad_members()
        local i = 0
        return function()
            i = i + 1
            local m = self.members[i]
            if m then return (i % 2 == 0) and { id = m, object = OBJ[m] } or { id = m } end
        end
    end
    OBJ[id] = sq
    SIMBOARD.squads[id] = true
end
-- a smart's arrival test, by game vertex (the real one also accepts a squad within arrive_dist)
local function smart(id, name, gv, broken)
    local s = { id = id, m_game_vertex_id = gv, nm = name }
    function s:name() return self.nm end
    function s:am_i_reached(sq)
        if broken then error("am_i_reached broke") end
        return sq.m_game_vertex_id == self.m_game_vertex_id
    end
    OBJ[id] = s
    SIMBOARD.smarts[id] = { smrt = s, squads = {}, population = 0 }
end

smart(100, "bar_dolg_general", 11)
smart(101, "bar_zastava", 12)
smart(102, "bar_lair", 13)
smart(103, "bar_visitors", 14)
smart(104, 'esc_"odd"\\name', 21)
smart(105, "esc_broken", 22, true)

-- Duty, at 100: 3 fighters
npc(11, 500) npc(12, 500) npc(13, 100)
squad(10, "dolg", "duty_sim_squad_veteran", 11, { 11, 12, 13 }, 100)
-- Freedom, assigned to 100 and on its way: it doesn't hold it, though it outnumbers Duty
npc(21, 100) npc(22, 100) npc(23, 100) npc(24, 100)
squad(20, "freedom", "freedom_sim_squad_advanced", 10, { 21, 22, 23, 24 }, 100)
-- Loners (2) and Bandits (3) both at 101: enemies, so it's contested; the Bandits hold it
npc(31, 100) npc(32, 400)
squad(30, "stalker", "stalker_sim_squad_novice", 12, { 31, 32 }, 101)
npc(41, 100) npc(42, 100) npc(43, 100)
squad(40, "bandit", "bandit_sim_squad_novice", 12, { 41, 42, 43 }, 101)
-- mutants at 102: they hold nothing, and have no stalker ranks
npc(51, 900, CLS_MONSTER) npc(52, 900, CLS_MONSTER)
squad(50, "monster", "simulation_dog", 13, { 51, 52 }, 102)
-- an army story squad on another level, assigned to a smart the board doesn't know
npc(61, 600)
squad(60, "army", "army_special_squad", 20, { 61 }, 777)
STORY[60] = "esc_army_story"
-- Duty (2) and Freedom (2), neutral, both at 103: a tie goes to "dolg", not contested
npc(71, 100) npc(72, 100)
squad(70, "dolg", "duty_sim_squad_novice", 14, { 71, 72 }, 103)
npc(81, 100) npc(82, 100)
squad(80, "freedom", "freedom_sim_squad_novice", 14, { 81, 82 }, 103)
-- Loners at 104 (a name to escape); one member already gone from the alife
npc(91, 100)
squad(90, "stalker", "stalker_sim_squad_advanced", 21, { 91, 99 }, 104)
-- a released squad still in the board's list
SIMBOARD.squads[999] = true
-- Mercenaries standing at 103 but assigned to 104: they hold neither
npc(111, 100)
squad(110, "killer", "merc_sim_squad_novice", 14, { 111 }, 104)
-- Ecologists at a smart whose arrival test throws: not counted there, and the census goes on
npc(121, 100)
squad(120, "ecolog", "ecolog_sim_squad_novice", 22, { 121 }, 105)

function snapshot()
    local t = {}
    for id, o in pairs(OBJ) do
        local s = {}
        for k, v in pairs(o) do
            if type(v) ~= "function" and type(v) ~= "table" then s[#s + 1] = k .. "=" .. tostring(v) end
        end
        table.sort(s)
        t[#t + 1] = id .. ":" .. table.concat(s, ",")
    end
    table.sort(t)
    return table.concat(t, ";")
end
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def sorted_everywhere(pairs_list):
    keys = [k for k, _ in pairs_list]
    if keys != sorted(keys):
        raise Fail("keys out of order: %s" % keys)
    return dict(pairs_list)


def run(src):
    out = tempfile.mkdtemp(prefix="fotz_census_")
    try:
        lua = L.LuaRuntime(unpack_returned_tuples=True)
        g = lua.globals()
        g.OUTDIR = out.replace("\\", "/")
        lua.execute(WORLD)
        env = lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                       "local f = assert(loadstring(src, 'fotz_census')) setfenv(f, env) f() return env end")(src)
        before = g.snapshot()
        path = os.path.join(out, "fotz_census.jsonl")

        def lines():
            if not os.path.exists(path):
                return []
            return [l for l in io.open(path, encoding="utf-8").read().splitlines() if l]

        # the schedule: nothing until 30 s after the first update, then one census a day
        env.on_game_start()
        cb = g.CALLBACKS
        g.NOW = 1000
        cb["actor_on_first_update"]()
        for now in (5000, 20000, 30999):
            g.NOW = now
            cb["actor_on_update"]()
        check(lines() == [], "a census ran before the wait after the load was over")
        g.NOW = 31000
        cb["actor_on_update"]()
        check(len(lines()) == 1, "no census after the wait (%d lines)" % len(lines()))
        for now in (36000, 41000, 90000):
            g.NOW = now
            cb["actor_on_update"]()
        check(len(lines()) == 1, "a second census on the same day (%d lines)" % len(lines()))
        g.DATE[3] = 15
        g.NOW = 95000
        cb["actor_on_update"]()
        check(len(lines()) == 2, "no census on the next day (%d lines)" % len(lines()))
        g.MCM["fotz/census"] = False
        g.DATE[3] = 16
        g.NOW = 100000
        cb["actor_on_update"]()
        check(len(lines()) == 2, "a census with the MCM switch off")
        g.MCM["fotz/census"] = None

        first = json.loads(lines()[0], object_pairs_hook=sorted_everywhere)
        second = json.loads(lines()[1], object_pairs_hook=sorted_everywhere)
        check(first["cause"] == "load" and second["cause"] == "day",
              "causes %s, %s" % (first["cause"], second["cause"]))
        check(first["date"] == "2012-05-14 08:00" and second["date"] == "2012-05-15 08:00",
              "dates %s, %s" % (first["date"], second["date"]))
        c = first
        f = c["factions"]
        check(sorted(f) == ["army", "bandit", "dolg", "ecolog", "freedom", "killer", "monster", "stalker"],
              "factions %s" % sorted(f))
        check(f["dolg"]["squads"] == 2 and f["dolg"]["fighters"] == 5, "Duty %s" % f["dolg"])
        check(f["dolg"]["tiers"] == {"veteran": 1, "novice": 1}, "Duty's tiers %s" % f["dolg"]["tiers"])
        check(f["dolg"]["ranks"] == {"veteran": 2, "novice": 3}, "Duty's ranks %s" % f["dolg"]["ranks"])
        check(f["stalker"]["fighters"] == 3, "the Loners count a gone member: %s" % f["stalker"])
        check(f["stalker"]["levels"] == {"l05_bar": {"squads": 1, "fighters": 2},
                                         "l01_escape": {"squads": 1, "fighters": 1}},
              "Loners' levels %s" % f["stalker"]["levels"])
        check(f["monster"]["ranks"] == {} and f["monster"]["fighters"] == 2, "mutants %s" % f["monster"])
        check(f["army"]["story"] == 1 and f["army"]["tiers"] == {"other": 1}, "the army squad %s" % f["army"])
        check(sum(e["story"] for e in f.values()) == 1, "story squads %s" % {k: e["story"] for k, e in f.items()})
        check(c["smarts"] == {"bar_dolg_general": "dolg", "bar_zastava": "bandit", "bar_visitors": "dolg",
                              'esc_"odd"\\name': "stalker"}, "holders %s" % c["smarts"])
        check(c["contested"] == ["bar_zastava"], "contested %s" % c["contested"])
        check(c["fronts"] == {"bandit/stalker": {"n": 1, "at": "bar_zastava"}}, "fronts %s" % c["fronts"])
        check(c["held"] == 4, "held %s" % c["held"])
        check(c["levels"]["l05_bar"] == {"smarts": 4, "held": {"dolg": 2, "bandit": 1}, "contested": 1},
              "the Bar %s" % c["levels"]["l05_bar"])
        check(c["levels"]["l01_escape"] == {"smarts": 2, "held": {"stalker": 1}, "contested": 0},
              "Cordon %s" % c["levels"]["l01_escape"])
        r = c["relations"]
        check(len(r) == 12 and all(len(row) == 11 and a not in row for a, row in r.items()),
              "the relations table isn't 12 x 11")
        check(r["bandit"]["stalker"] == -1500 and r["dolg"]["freedom"] == 0, "relations %s" % r["bandit"])
        check(c["goodwill"]["dolg"] == 300 and c["goodwill"]["bandit"] == -1200, "goodwill %s" % c["goodwill"])
        check(c["actor"] == "actor_stalker" and c["toward_actor"]["dolg"] == 700,
              "toward the actor %s" % c["toward_actor"])

        # the same world counted twice reads the same, but for the clocks
        a = json.loads(env.to_json(env.take("x")))
        b = json.loads(env.to_json(env.take("x")))
        for d in (a, b):
            d.pop("real"), d.pop("ms")
        check(a == b, "two censuses of one world differ")

        # with the log off, a listener still gets each census, and nothing is written
        lua.execute("GOT = {}")
        env.listen(lua.eval("function(c) GOT[#GOT + 1] = c.date end"))
        g.MCM["fotz/census"] = False
        g.DATE[3] = 16
        g.NOW = 105000
        cb["actor_on_update"]()
        check(list(g.GOT.values()) == ["2012-05-16 08:00"], "the listener got %s" % list(g.GOT.values()))
        check(len(lines()) == 2, "a census was written with the log off")
        g.MCM["fotz/census"] = None

        # an error stays inside the census: logged, nothing written, nothing thrown
        g.OBJ[10].get_squad_community = lua.eval("function() error('boom') end")
        g.DATE[3] = 17
        g.NOW = 110000
        cb["actor_on_update"]()
        check(len(lines()) == 2, "a failed census wrote a line")
        check(any(l.startswith("! [fotz-census]") and "boom" in l for l in g.LOG.values()),
              "the error wasn't logged")

        log = list(g.LOG.values())
        check(sum(l.startswith("[fotz-census] ") for l in log) == 3, "summary lines: %s" % log)
        check(all("%" not in l for l in log), "a %% reached the log: %s" % log)
        check("2012-05-14 08:00 (load): 11 squads, 22 fighters, 4 smarts held, 1 contested" in log[0],
              "summary %s" % log[0])
        check(len(g.WRITES) == 0, "the census wrote to the world: %s" % list(g.WRITES.values()))
        check(g.snapshot() == before, "the census changed a squad or smart")
        return "compared 8 factions, 6 smarts, 132 relations, 4 censuses"
    finally:
        shutil.rmtree(out, ignore_errors=True)


def main():
    src = io.open(SCRIPT, encoding="latin-1").read()
    if len(sys.argv) > 1:
        name = sys.argv[1]
        old, new = MUTANTS[name]
        if src.count(old) != 1:
            print("MUTANT DOES NOT APPLY: %s (found %d times)" % (name, src.count(old)))
            return 2
        src = src.replace(old, new)
    try:
        print("ok: " + run(src))
        return 0
    except Fail as e:
        print("FAIL: %s" % e)
        return 1
    except Exception as e:
        print("FAIL (error): %s: %s" % (type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
