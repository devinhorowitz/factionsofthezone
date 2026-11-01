"""Run fotz_territory.script under LuaJIT 2.0 against a stand-in for the game's target scoring and
check the steer.

Checked: the multiplier from a level's fighters, within its bounds; the table from a census and the
wars in force (only smarts an enemy at war holds, not your faction's wars, not peace); the wrapper
raises and lowers a smart's score for the right squads and passes everything else through
(other factions, squads as targets, a 0 score, varargs); story squads, companions, Homestead's
garrisons and squads with a scripted target are left alone, and squads other mods claim (add_owner,
AlifePlus's registry, Homestead's held squads; a claim that fails counts, and is logged once);
MCM's switch and politics standing down
unwind it, but never another mod's wrapper over it; wrapping again doesn't weigh twice; the
census's log line and counters; the shipped config's numbers. The fronts: each enemy pair's shared
levels, the biggest first; the upper hand at two thirds; news when a side newly takes it on a front
that was there last census and is big enough, two a day, the biggest first, none from the first
census after a load; an error there doesn't stop the steer.

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
    "front_one_way": ("            if relation_registry.community_relation(a, b) <= ENEMIES\n"
                      "                or relation_registry.community_relation(b, a) <= ENEMIES then",
                      "            if relation_registry.community_relation(a, b) <= ENEMIES then"),
    "front_alone": ("                    if fa > 0 and fb > 0 then", "                    if fa > 0 then"),
    "front_sort": ("            return x.fa + x.fb > y.fa + y.fb", "            return x.fa + x.fb < y.fa + y.fb"),
    "upper_strict": ("    if f.fa >= UPPER * total then", "    if f.fa > UPPER * total then"),
    "upper_b": ("    elseif f.fb >= UPPER * total then\n        return f.b, f.a\n", ""),
    "news_on_load": ("if was ~= nil and win and was ~= win", "if win and was ~= win"),
    "news_same": ("if was ~= nil and win and was ~= win", "if was ~= nil and win"),
    "news_small": ("and f.fa + f.fb >= FRONT_MIN and said < NEWS_PER_DAY", "and said < NEWS_PER_DAY"),
    "news_uncapped": ("and f.fa + f.fb >= FRONT_MIN and said < NEWS_PER_DAY", "and f.fa + f.fb >= FRONT_MIN"),
    "news_uncounted": ("                said = said + 1\n", ""),
    "news_loser": ("{ b = P.faction_name(lose), place", "{ b = P.faction_name(win), place"),
    "fronts_unguarded": ("    local ok, err = pcall(take_fronts, c)", "    local ok, err = true, take_fronts(c)"),
    "claims_ignored": ("    return e or squad.scripted_target ~= nil or owner_of(squad) ~= nil",
                       "    return e or squad.scripted_target ~= nil"),
    "failed_claim_steers": ("        if mine or not ok then", "        if ok and mine then"),
    "failed_claim_logged_always": ("        if not ok and not failed[name] then", "        if not ok then"),
    "alifeplus_ignored": ("    local ap = ap_api\n", "    local ap = nil\n"),
    "alifeplus_unguarded": ("        local _, name = pcall(ap.get_owner, squad)", "        local name = ap.get_owner(squad)"),
    "claim_kept": ("    owners[name] = nil\n", ""),
    "bad_claim_taken": ('    if type(name) ~= "string" or type(fn) ~= "function" then', "    if false then"),
    "homestead_held_ignored": ("    local hs = stalker_camp_builder\n", "    local hs = nil\n"),
    "homestead_failure_steers": ("        if held or not ok then", "        if ok and held then"),
    "never_counted": ("    COUNTED = true\n", ""),
    "map_not_updated": ("        ok, err = pcall(fotz_map.update, c)\n", "        ok, err = true, nil\n"),
    "map_unguarded": ("        ok, err = pcall(fotz_map.update, c)\n", "        ok, err = true, fotz_map.update(c)\n"),
    "ctz_ignored": ("    if squad.ctz_campaign_owned then\n        return \"ctz\"\n    end\n", ""),
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
-- politics' news and names, and the game's own names for levels
NEWS = {}
game = { translate_string = function(s) return "T:" .. s end }
fotz_politics = {
    say = function(level, id, voice, fields)
        NEWS[#NEWS + 1] = { level = level, id = id, voice = voice, b = fields.b, place = fields.place }
        return true
    end,
    faction_name = function(f) return "N:" .. f end }
-- the PDA map's fronts, updated from each census
MAPPED = {}
fotz_map = { update = function(c) MAPPED[#MAPPED + 1] = c.date end }
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
    check(log and "08:00: 3 fronts; 4 smarts weighed for 3 factions (steering)" in log[0], "log %s" % log)
    # raised: s1 for Duty, its 0 score, and the varargs call; lowered: s4
    check(w.env.STATS.raised == 3 and w.env.STATS.lowered == 1, "counted %s raised, %s lowered"
          % (w.env.STATS.raised, w.env.STATS.lowered))
    w.census(CENSUS)
    log = [l for l in w.log() if l.startswith("[fotz-territory] 2012-05-02")]
    check(", 3 raised, 1 lowered" in log[1] and w.env.STATS.raised == 0, "the next census's line: %s" % log[1])
    check(list(w.g.MAPPED.values()) == ["2012-05-02 08:00"] * 2, "the map updated %s" % list(w.g.MAPPED.values()))
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

    # squads other mods claim: through add_owner, through AlifePlus's registry, and a claim that
    # fails (left alone, logged once); a claim removed lets the steer back in
    env = w.env
    check(env.add_owner("theirs", w.eval("function(sq) return sq.id == 906 end")) is True
          and env.add_owner("broken", w.eval('function(sq) if sq.id == 908 then error("no such field") end end')) is True
          and env.add_owner(None, w.eval("function() return true end")) is False, "add_owner's answers")
    w.run('ap_api = { get_owner = function(sq) if sq.id == 909 then error("bad squad") end '
          'return sq.id == 907 and "warfare" or nil end }')
    # Homestead's own check: its camps, reinforcements and convoys
    w.run('function stalker_camp_builder.is_held_squad(sq) if sq.id == 911 then error("no camp") end return sq.id == 910 end')
    got = [w.eval('score(101, "dolg", %d)' % i) for i in (906, 907, 908, 908, 909, 910, 911, 905)]
    check(got == [10, 10, 10, 10, 10, 10, 10, 12.5],
          "claimed by add_owner, by AlifePlus, failing twice, AlifePlus failing, Homestead's, Homestead "
          "failing, ordinary: %s" % got)
    # Capture the Zone's campaign squads, marked on the squad
    ctz = w.eval("simulation_objects.evaluate_prior")({"id": 101}, w.eval("{ id = 912, player_id = 'dolg', ctz_campaign_owned = true }"))
    check(ctz == 10 and env.owner_of(w.eval("{ id = 912, ctz_campaign_owned = true }")) == "ctz",
          "a CtZ campaign squad: %s" % ctz)
    fails = [l for l in w.log() if "broken's claim failed" in l]
    check(len(fails) == 1, "the failed claim logged %d times" % len(fails))
    check(env.owner_of(w.eval("{ id = 907 }")) == "warfare" and env.owner_of(w.eval("{ id = 905 }")) is None,
          "owner_of: %s, %s" % (env.owner_of(w.eval("{ id = 907 }")), env.owner_of(w.eval("{ id = 905 }"))))
    env.remove_owner("theirs")
    w.run("ap_api = nil")
    got = [w.eval('score(101, "dolg", %d)' % i) for i in (906, 907)]
    check(got == [12.5, 12.5], "after the claims went: %s" % got)


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


def census_of(levels, date="2012-05-02 08:00"):
    """A census from {level: {faction: fighters}}, holding no smarts."""
    fac = {}
    for lv, by in levels.items():
        for f, n in by.items():
            fac.setdefault(f, {})[lv] = n
    body = ", ".join("%s = { levels = { %s } }" % (f, ", ".join("%s = { fighters = %d }" % (lv, n)
                                                                for lv, n in sorted(lvs.items())))
                     for f, lvs in sorted(fac.items()))
    return '{ date = "%s", smarts = {}, factions = { %s } }' % (date, body)


def front_list(w):
    F = w.env.FRONTS
    return [(F[i].a, F[i].b, F[i].level, F[i].fa, F[i].fb) for i in range(1, len(F) + 1)]


def news(w):
    N = w.g.NEWS
    return [(N[i].level, N[i].id, N[i].voice, N[i].b, N[i].place) for i in range(1, len(N) + 1)]


def upper(win, lose, place):
    return ("all", "st_fotz_news_front_upper", win, "N:" + lose, "T:" + place)


def fronts(src):
    w = World(src, SETUP)
    lead = w.env.leader
    check(w.env.COUNTED is False, "counted before a census")

    def side(fa, fb):
        r = lead(w.eval('{ a = "x", b = "y", fa = %d, fb = %d }' % (fa, fb)))
        return r[0] if isinstance(r, tuple) else r
    got = [side(20, 10), side(10, 20), side(19, 11), side(11, 19), side(15, 15)]
    check(got == ["x", "y", None, None, None], "the upper hand at two thirds: %s" % got)

    # Duty and the Mercenaries at war both ways; the Military enemies of the Bandits one way only;
    # Clear Sky and Freedom in a truce; Duty alone on Rostok, the Mercenaries alone on the Warehouses
    c1 = {"l02_garbage": {"dolg": 30, "killer": 10, "bandit": 5, "army": 15, "csky": 20, "freedom": 20},
          "l03_agroprom": {"dolg": 10, "killer": 30}, "l06_rostok": {"dolg": 20}, "l07_military": {"killer": 40}}
    w.census(census_of(c1))
    check(w.env.COUNTED is True, "not counted after a census")
    got = front_list(w)
    check(got == [("dolg", "killer", "l02_garbage", 30, 10), ("dolg", "killer", "l03_agroprom", 10, 30),
                  ("bandit", "army", "l02_garbage", 5, 15)], "the fronts %s" % got)
    check(news(w) == [], "news from the first census after a load: %s" % news(w))

    # Garbage evens out, a small close front opens on Dark Valley: nothing newly taken
    c2 = dict(c1, l02_garbage=dict(c1["l02_garbage"], dolg=20, killer=20),
              l04_darkvalley={"dolg": 2, "killer": 3})
    w.census(census_of(c2))
    check(news(w) == [], "news without a side newly ahead: %s" % news(w))

    # the Mercenaries take Garbage, Duty takes Agroprom, the Bandits overtake the Military: two
    # a day, the biggest first
    c3 = dict(c2, l02_garbage=dict(c1["l02_garbage"], dolg=10, killer=30, bandit=15, army=5),
              l03_agroprom={"dolg": 30, "killer": 10}, l04_darkvalley={"dolg": 1, "killer": 6})
    w.census(census_of(c3))
    check(news(w) == [upper("killer", "dolg", "l02_garbage"), upper("dolg", "killer", "l03_agroprom")],
          "the day's news %s" % news(w))

    # Duty takes Dark Valley, too small for news; a new front on the Bar already won isn't news
    c4 = dict(c3, l04_darkvalley={"dolg": 6, "killer": 1}, l05_bar={"dolg": 30, "killer": 5})
    w.census(census_of(c4))
    check(len(news(w)) == 2, "news of a small or a new front: %s" % news(w)[2:])

    # the Military take Garbage back from the Bandits, ahead since the day the news ran out
    c5 = dict(c4, l02_garbage=dict(c3["l02_garbage"], bandit=5, army=15))
    w.census(census_of(c5))
    check(news(w)[2:] == [upper("army", "bandit", "l02_garbage")], "the Military's news %s" % news(w)[2:])

    # the news failing doesn't stop the steer
    w = World(src, SETUP)
    w.run('fotz_politics.say = function() error("no news today") end')
    w.run('fotz_map.update = function() error("no map today") end')
    w.census(census_of(c1))
    w.census(census_of(c3).replace("smarts = {}", 'smarts = { s1 = "killer" }'))
    check(w.env.STEER["dolg"] is not None and any("! fronts:" in l for l in w.log())
          and any("! the map:" in l for l in w.log()),
          "after the news and the map failed: steer %s, log %s" % (w.env.STEER["dolg"], w.log()[-3:]))


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
    fronts(src)
    shipped_config(src)
    return "6 scenarios"


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
