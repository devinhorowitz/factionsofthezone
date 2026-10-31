"""Run fotz_territory.script under LuaJIT 2.0 against a stand-in for the game's target scoring and
check the steer.

Checked: the multiplier from a level's fighters, within its bounds; the table from a census and the
wars in force (only smarts an enemy at war holds, not your faction's wars, not peace); the wrapper
raises and lowers a smart's score for the right squads and passes everything else through
(other factions, squads as targets, a 0 score, varargs); story squads, companions, Homestead's
garrisons and squads with a scripted target are left alone; MCM's switch and politics standing down
unwind it, but never another mod's wrapper over it; wrapping again doesn't weigh twice; the
census's log line and counters; the shipped config's numbers.

    python test_territory.py            the real script
    python test_territory.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import re
import sys

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(HERE, "..", "gamedata")
SCRIPT = os.path.join(GD, "scripts", "fotz_territory.script")
CONFIG = os.path.join(GD, "configs", "plugins", "fotz_politics.ltx")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "no_clamp": ("    return math.max(cfg.lo, math.min(cfg.hi, m))", "    return m"),
    "share_flipped": ("local m = 1 + cfg.k * (2 * (mine or 0) / total - 1)", "local m = 1 + cfg.k * (1 - 2 * (mine or 0) / total)"),
    "line_strict": ("if f ~= h and relation_registry.community_relation(f, h) <= ENEMIES then",
                    "if f ~= h and relation_registry.community_relation(f, h) < ENEMIES then"),
    "direction": ("if f ~= h and relation_registry.community_relation(f, h) <= ENEMIES then",
                  "if f ~= h and relation_registry.community_relation(h, f) <= ENEMIES then"),
    "no_front_check": ("local m = mine > 0 and multiplier(mine, fighters(c, holder, lv)) or 1",
                       "local m = multiplier(mine, fighters(c, holder, lv))"),
    "holder_side": ("local m = mine > 0 and multiplier(mine, fighters(c, holder, lv)) or 1",
                    "local m = mine > 0 and multiplier(fighters(c, holder, lv), mine) or 1"),
    "story": ("e = get_object_story_id(id) ~= nil or (comp", "e = (comp"),
    "companions": ("or (comp ~= nil and comp[id] ~= nil) or garrison[id] == true", "or garrison[id] == true"),
    "garrisons": ("or (comp ~= nil and comp[id] ~= nil) or garrison[id] == true", "or (comp ~= nil and comp[id] ~= nil)"),
    "scripted": ("    return e or squad.scripted_target ~= nil", "    return e"),
    "off_steers": ("    if not on then\n        return prior\n    end\n    STATS.calls", "    STATS.calls"),
    "mcm_ignored": ('    if ui_mcm and ui_mcm.get("fotz/territory") == false then', "    if false then"),
    "warfare_ignored": ("    return not (IsWarfare and IsWarfare())", "    return true"),
    "unwrap_theirs": ("    if wrapper and simulation_objects and simulation_objects.evaluate_prior == wrapper then",
                      "    if wrapper and simulation_objects then"),
    "wrap_twice": ("    if wrapper then\n        return true\n    end\n    orig", "    orig"),
    "varargs": ("local prior = orig(target, squad, ...)", "local prior = orig(target, squad)"),
    "stats_kept": ("    STATS.calls, STATS.raised, STATS.lowered = 0, 0, 0\n", ""),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end
INI = {}
function ini_file() return { r_float_ex = function(_, s, k) return INI[s] and INI[s][k] end } end
MCM = {}
ui_mcm = { get = function(id) return MCM[id] end }
CALLBACKS = {}
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end

-- relations, as the game has them now; Warfare mode
REL = {}
relation_registry = { community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end }
function war(a, b) REL[a .. ">" .. b] = -1500; REL[b .. ">" .. a] = -1500 end
WARFARE = false
function IsWarfare() return WARFARE end

-- the census: smarts by name, their levels, listeners
LEVEL = {}
LISTENERS = {}
fotz_census = { FACTIONS = { "stalker", "bandit", "csky", "dolg", "freedom", "killer", "army", "ecolog",
                               "monolith", "renegade", "greh", "isg" },
                level_of = function(se) return LEVEL[se.id] end,
                listen = function(fn) LISTENERS[#LISTENERS + 1] = fn end }
SIMBOARD = { smarts_by_names = {} }
function smart(name, id, level) SIMBOARD.smarts_by_names[name] = { id = id }; LEVEL[id] = level end

STORY = {}
function get_object_story_id(id) return STORY[id] end
axr_companions = { companion_squads = {} }
stalker_camp_builder = { rival_camps = {} }

-- the game's scoring, as G.A.M.M.A. Economy leaves it: a fixed score per target, 0 for "no"
BASE = {}
ARGS = 0
function base_prior(target, squad, ...) ARGS = select("#", ...) return BASE[target.id] or 10 end
simulation_objects = { evaluate_prior = base_prior }
function score(target_id, faction, squad_id, scripted)
    return simulation_objects.evaluate_prior({ id = target_id },
        { id = squad_id or 900, player_id = faction, scripted_target = scripted })
end
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


class World:
    def __init__(self, src, setup=""):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(WORLD)
        self.lua.execute('INI.territory = { k = 0.5, lo = 0.6, hi = 1.5 }')
        self.lua.execute(setup)
        self.env = self.lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                                 "local f = assert(loadstring(src, 'fotz_territory')) setfenv(f, env) f() return env end")(src)
        self.env.on_game_start()

    def run(self, code):
        return self.lua.execute(code)

    def eval(self, code):
        return self.lua.eval(code)

    def census(self, c):
        for i in range(1, len(self.g.LISTENERS) + 1):
            self.g.LISTENERS[i](self.eval(c))

    def log(self):
        return list(self.g.LOG.values())


#: a census: Duty and the Mercenaries at war; killer holds s1 (Garbage, Duty 30 to 10) and s4
#: (Agroprom, Duty 10 to 30); dolg holds s2 (Agroprom); freedom holds s3 (Garbage, no war);
#: wolves (your faction) at war with bandits, who hold s5
CENSUS = """{ date = "2012-05-02 08:00",
    smarts = { s1 = "killer", s2 = "dolg", s3 = "freedom", s4 = "killer", s5 = "bandit", s6 = "killer" },
    factions = {
        dolg = { levels = { l02_garbage = { fighters = 30 }, l03_agroprom = { fighters = 10 } } },
        killer = { levels = { l02_garbage = { fighters = 10 }, l03_agroprom = { fighters = 30 }, l07_military = { fighters = 40 } } },
        freedom = { levels = { l02_garbage = { fighters = 20 } } },
        csky = { levels = { l02_garbage = { fighters = 60 } } },
        bandit = { levels = { l02_garbage = { fighters = 5 } } },
        army = { levels = { l02_garbage = { fighters = 15 } } } } }"""
SETUP = """
smart("s1", 101, "l02_garbage"); smart("s2", 102, "l03_agroprom"); smart("s3", 103, "l02_garbage")
smart("s4", 104, "l03_agroprom"); smart("s5", 105, "l02_garbage")
-- s6: the Mercenaries' on the Army Warehouses, where Duty has no one: not a front
smart("s6", 106, "l07_military")
war("dolg", "killer"); war("bandit", "fotz_own")
-- a truce isn't a war: Clear Sky (stronger on Garbage) isn't steered at Freedom's s3
REL["csky>freedom"], REL["freedom>csky"] = -600, -600
-- the line itself is enmity, and one-sided: the Military are enemies of the Bandits (s5) at
-- exactly -1000, the Bandits don't count the Military as enemies
REL["army>bandit"], REL["bandit>army"] = -1000, 0
"""


def multiplier(src):
    w = World(src)
    m = w.env.multiplier
    got = [m(30, 10), m(10, 30), m(0, 10), m(10, 0), m(0, 0), m(20, 20)]
    check(got == [1.25, 0.75, 0.6, 1.5, 1, 1], "multipliers %s" % got)


def steer(src):
    w = World(src, SETUP)
    w.census(CENSUS)
    S = w.env.STEER
    check(S["dolg"][101] == 1.25 and S["dolg"][104] == 0.75, "Duty on s1 %s, s4 %s" % (S["dolg"][101], S["dolg"][104]))
    check(S["dolg"][106] is None, "Duty weighed s6, on a level it has no one on: %s" % S["dolg"][106])
    check(S["killer"][102] == 1.25 and S["killer"][101] is None, "the Mercenaries on s2 %s, on their own s1 %s"
          % (S["killer"][102], S["killer"][101]))
    check(S["freedom"] is None and S["fotz_own"] is None and S["bandit"] is None and S["csky"] is None,
          "steered without a war of their own: %s" % [k for k in ("freedom", "fotz_own", "bandit", "csky")
                                                      if S[k] is not None])
    check(S["army"] is not None and S["army"][105] == 1.25, "the Military at the line, toward the Bandits' s5: %s"
          % (S["army"] and S["army"][105]))
    # the scores: up, down, through
    got = [w.eval('score(101, "dolg")'), w.eval('score(104, "dolg")'), w.eval('score(101, "freedom")'),
           w.eval('score(103, "dolg")'), w.eval('score(900, "dolg")')]
    check(got == [12.5, 7.5, 10, 10, 10], "scores %s" % got)
    w.run("BASE[101] = 0")
    check(w.eval('score(101, "dolg")') == 0, "a 0 score was raised")
    w.run("BASE[101] = nil")
    w.eval('simulation_objects.evaluate_prior')({"id": 101}, w.eval("{ id = 1, player_id = 'dolg' }"), 1, 2)
    check(w.g.ARGS == 2, "the wrapper passed on %d extra arguments, not 2" % w.g.ARGS)
    log = [l for l in w.log() if l.startswith("[fotz-territory] 2012-05-02")]
    check(log and "4 smarts weighed for 3 factions (steering)" in log[0], "log %s" % log)
    # raised: s1 for Duty, its 0 score, and the varargs call; lowered: s4
    check(w.env.STATS.raised == 3 and w.env.STATS.lowered == 1, "counted %s raised, %s lowered"
          % (w.env.STATS.raised, w.env.STATS.lowered))
    w.census(CENSUS)
    log = [l for l in w.log() if l.startswith("[fotz-territory] 2012-05-02")]
    check(", 3 raised, 1 lowered" in log[1] and w.env.STATS.raised == 0, "the next census's line: %s" % log[1])
    return w


def left_alone(src):
    w = World(src, SETUP + """
STORY[901] = "esc_story_squad"
axr_companions.companion_squads[902] = true
stalker_camp_builder.rival_camps.camp_a = { squad_id = 903 }
""")
    w.census(CENSUS)
    got = [w.eval('score(101, "dolg", %d)' % i) for i in (901, 902, 903)]
    got.append(w.eval('score(101, "dolg", 904, "some_smart")'))
    got.append(w.eval('score(101, "dolg", 905)'))
    check(got == [10, 10, 10, 10, 12.5], "story, companion, garrison, scripted, ordinary: %s" % got)


def switch(src):
    w = World(src, SETUP)
    w.census(CENSUS)
    w.run('MCM["fotz/territory"] = false')
    w.cb = w.g.CALLBACKS
    w.cb["on_option_change"]()
    check(w.eval("simulation_objects.evaluate_prior == base_prior"), "MCM off left the wrapper in place")
    w.run('MCM["fotz/territory"] = nil')
    w.cb["on_option_change"]()
    check(w.eval('score(101, "dolg")') == 12.5, "back on, not steering")
    # Warfare mode runs the squads: the steer stands down
    w.run("WARFARE = true")
    w.cb["on_option_change"]()
    check(w.eval("simulation_objects.evaluate_prior == base_prior") and w.eval('score(101, "dolg")') == 10,
          "steering in Warfare mode")
    w.run("WARFARE = false")
    w.cb["on_option_change"]()
    # another mod wraps over ours: turning off leaves both in place and ours passes through;
    # turning on again doesn't wrap twice
    w.run("""
local under = simulation_objects.evaluate_prior
THEIRS = function(target, squad, ...) return under(target, squad, ...) end
simulation_objects.evaluate_prior = THEIRS
""")
    w.run('MCM["fotz/territory"] = false')
    w.cb["on_option_change"]()
    check(w.eval("simulation_objects.evaluate_prior == THEIRS") and w.eval('score(101, "dolg")') == 10,
          "off under another mod's wrapper")
    w.run('MCM["fotz/territory"] = nil')
    w.cb["on_option_change"]()
    check(w.eval("simulation_objects.evaluate_prior == THEIRS") and w.eval('score(101, "dolg")') == 12.5,
          "back on under another mod's wrapper: %s" % w.eval('score(101, "dolg")'))


def shipped_config(src):
    text = open(CONFIG, encoding="utf-8").read()
    sec = re.search(r"(?ms)^\[territory\](.*?)(^\[|\Z)", text).group(1)
    vals = {k: float(v) for k, v in re.findall(r"(?m)^(\w+)\s*=\s*([-\d.]+)", sec)}
    check(vals == {"k": 0.5, "lo": 0.6, "hi": 1.5}, "the shipped [territory]: %s" % vals)
    check(vals["lo"] < 1 < vals["hi"], "the bounds don't straddle 1")


def run(src):
    multiplier(src)
    steer(src)
    left_alone(src)
    switch(src)
    shipped_config(src)
    return "5 scenarios"


def main():
    src = io.open(SCRIPT, encoding="utf-8").read()
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
        print("FAIL (error): %s: %s" % (type(e).__name__, " | ".join(str(e).splitlines())))
        return 1


if __name__ == "__main__":
    sys.exit(main())
