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
census after a load; an error there doesn't stop the steer. Your faction's footprint: squads hostile
to your members drawn to the levels they're on, by steps and nearness, up to the cap or MCM's
slider (not by the dead or a member with no level); worked out again between censuses; the steer's
exemptions; the page's list. The consequences: the strain only toward factions politics has a pair
of yours with, none listed while it stands down, companions not settled; goodwill only for a
faction's stalker, not your member's; the ground before the first census; MCM's defaults agree.

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
    "stats_kept": ("    STATS.calls, STATS.raised, STATS.lowered, STATS.drawn = 0, 0, 0, 0\n", ""),
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
    # your faction's footprint (0.6.0)
    "foot_everyone": ("if hates_you or (m.mother and rel(e, m.mother) <= ENEMIES) then", "if true then"),
    "foot_not_you": ("        local hates_you = rel(e, own) <= ENEMIES", "        local hates_you = false"),
    "foot_far_as_near": ("draw = draw + m.w * P.nearness(m.lv, lv)", "draw = draw + m.w"),
    "foot_no_neighbors": ("                if at == lv or P.nearness(at, lv) >= cfg.reach then", "                if at == lv then"),
    "foot_reach_all": ("                if at == lv or P.nearness(at, lv) >= cfg.reach then", "                if true then"),
    "foot_absent": ("            if (l.fighters or 0) > 0 then\n                present[#present + 1] = lv",
                    "            if true then\n                present[#present + 1] = lv"),
    "foot_slider_scale": ("        return math.max(0, v / 100)", "        return math.max(0, v)"),
    "foot_dead": ("        local lv = not m.dead and P.member_level(id)\n        if lv then\n            list[#list + 1]",
                  "        local lv = P.member_level(id)\n        if lv then\n            list[#list + 1]"),
    # a member with no level (their server object gone) isn't drawn on (2026-11-07 sweep, M2)
    "foot_no_level": ("        if lv then\n            list[#list + 1] = { lv = lv", "        if true then\n            list[#list + 1] = { lv = lv"),
    "foot_no_timer": ("    next_foot = now + FOOT_MS\n    update_footprint()\n", "    next_foot = now + FOOT_MS\n"),
    "infl_mutants": ("            if is[f] then", "            if true then"),
    "infl_held_only": ("                out[lv][f] = k / n", "                out[lv][f] = 1"),
    "enc_from_holder": ("        if m.mother ~= f then", "        if true then"),
    "enc_ally": ("            if n > 0 and rel(f, own) < FRIENDS and has_pair(f) then", "            if n > 0 and has_pair(f) then"),
    "enc_by_share": ("                out[f] = (out[f] or 0) - cap * fotz_perks.share(n) * s", "                out[f] = (out[f] or 0) - cap * fotz_perks.share(n)"),
    "enc_uncapped": ("        out[f] = math.max(-cap, v)", "        out[f] = v"),
    "enc_no_slider": ('    local cap = slider("encroach_max", cfg.encroach)', "    local cap = cfg.encroach"),
    "inst_enemies": ("        if f ~= v and rel(f, v) > ENEMIES then", "        if f ~= v then"),
    "inst_own": ("        if f ~= v and rel(f, v) > ENEMIES then", "        if rel(f, v) > ENEMIES then"),
    "inst_anyone": ("    if yours and not (F and F.members[victim:id()]) then", "    if not (F and F.members[victim:id()]) then"),
    "inst_silent": ("        yours = owner ~= nil and owner:id() == AC_ID", "        yours = false"),
    "inst_unfounded": ("    if not (F and per > 0 and factions()[v]) then", "    if not (per > 0 and factions()[v]) then"),
    "inst_prefix": ("    local v, n = strip(victim_comm), 0", "    local v, n = victim_comm, 0"),
    "strain_here_any": ("        if outsiders(by_level[here], f) > 0 and relation_registry", "        if relation_registry"),
    "foot_update_unguarded": ("    local ok, n = pcall(footprint, last_census)", "    local ok, n = true, footprint(last_census)"),
    "foot_any_target": ("SIMBOARD and SIMBOARD.smarts and SIMBOARD.smarts[target.id] and fotz_census.level_of(target) or false",
                        "fotz_census.level_of(target) or false"),
    "foot_left_alone": ("    if (m == nil and fm == nil) or left_alone(squad) then", "    if m == nil and fm == nil then"),
    "foot_shown_off": ("    local out = {}\n    if not on then\n        return out\n    end\n", "    local out = {}\n"),
    "foot_unguarded": ("    local ok2, drawn = pcall(footprint, c)", "    local ok2, drawn = true, footprint(c)"),
    # the 2026-11-07 sweep: the strain only where politics has a pair of yours, and not while it
    # stands down (C1); only a faction's stalker costs goodwill (C2); companions don't settle (C4);
    # the ground before the first census after a load (C5)
    "strain_no_pair": ("            if n > 0 and rel(f, own) < FRIENDS and has_pair(f) then",
                       "            if n > 0 and rel(f, own) < FRIENDS then"),
    "strain_here_no_pair": ("                and has_pair(f) then", "                then"),
    "strain_here_down": ("    if P and P.standing_down and P.standing_down() then\n        return out",
                         "    if false then\n        return out"),
    "inst_any_victim": ("    if not (F and per > 0 and factions()[v]) then", "    if not (F and per > 0) then"),
    "inst_members": ("    if yours and not (F and F.members[victim:id()]) then", "    if yours then"),
    "strain_companions": ('m.via ~= "companion" and ', ""),
    "strain_now_companions": (" and not (FF.is_companion and FF.is_companion(id))", ""),
    "ground_none_before": ("    if t == nil and not last_census and fotz_census.level_ground then", "    if false then"),
    "ground_after_census": ("    if t == nil and not last_census and", "    if t == nil and"),
    "ground_uncached": ("        INFLUENCE[lv] = t\n", ""),
    "ground_unguarded": ("        local ok, l = pcall(fotz_census.level_ground, lv)",
                         "        local ok, l = true, fotz_census.level_ground(lv)"),
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
-- your faction's pairs: none with a faction whose relations never change (NO_PAIR); standing down
NO_PAIR = { monolith = true, greh = true, isg = true, renegade = true }
DOWN = nil
fotz_politics = {
    OWN = "fotz_own",
    say = function(level, id, voice, fields)
        NEWS[#NEWS + 1] = { level = level, id = id, voice = voice, b = fields.b, place = fields.place }
        return true
    end,
    faction_name = function(f) return "N:" .. f end,
    pair_of = function(x, y) if x == "fotz_own" and not NO_PAIR[y] then return { key = y .. "/fotz_own" } end end,
    standing_down = function() return DOWN end }
-- the PDA map's fronts, updated from each census
MAPPED = {}
fotz_map = { update = function(c) MAPPED[#MAPPED + 1] = c.date end }
SIMBOARD = { smarts_by_names = {}, smarts = {} }
function smart(name, id, level) SIMBOARD.smarts_by_names[name] = { id = id }; SIMBOARD.smarts[id] = {}; LEVEL[id] = level end
NOW = 0
function time_global() return NOW end
HERE = "l02_garbage"
level = { name = function() return HERE end }

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


#: your faction: four members from Duty on Garbage, two from the Ecologists on Agroprom, one dead
#: and one from Duty whose server object is gone (no level); the perks' helpers as stand-ins: a
#: step each, half as near off their level (half on an unknown one), a straight share of 10
FOOT_SETUP = SETUP + """
war("freedom", "dolg")
fotz_faction = { F = { members = {
    [1] = { mother = "dolg" }, [2] = { mother = "dolg" }, [3] = { mother = "actor_dolg" }, [4] = { mother = "dolg" },
    [5] = { mother = "ecolog" }, [6] = { mother = "ecolog" }, [7] = { mother = "dolg", dead = true },
    [8] = { mother = "dolg" } } } }
MEMBER_LV = { [1] = "l02_garbage", [2] = "l02_garbage", [3] = "l02_garbage", [4] = "l02_garbage",
              [5] = "l03_agroprom", [6] = "l03_agroprom", [7] = "l02_garbage" }
-- Garbage and Agroprom are neighbors (0.5); the Army Warehouses are far from both (0.2)
NEAR = { ["l02_garbage>l03_agroprom"] = 0.5, ["l03_agroprom>l02_garbage"] = 0.5 }
fotz_perks = { member_level = function(id) return MEMBER_LV[id] end, weight_of = function(id) return 1 end,
               nearness = function(a, b) if not (a and b) then return 0.5 end return a == b and 1 or NEAR[a .. ">" .. b] or 0.2 end,
               share = function(w) return math.min(1, w / 10) end }
-- a squad as a target, sitting on Garbage
LEVEL[900] = "l02_garbage"
"""
#: the ground: on Garbage, Duty holds 6 of 10 smarts and the Mercenaries 2; on Agroprom the
#: Mercenaries hold 4 of 8 and all of the Army Warehouses; mutants hold some too, and aren't a faction
GROUND = """levels = { l02_garbage = { smarts = 10, held = { dolg = 6, killer = 2, monster = 1 } },
           l03_agroprom = { smarts = 8, held = { killer = 4 } }, l07_military = { smarts = 4, held = { killer = 4 } } }"""
#: the census, with Freedom also counted on the Army Warehouses with no one there
FOOT_CENSUS = CENSUS.replace("freedom = { levels = { l02_garbage = { fighters = 20 } } }",
                             "freedom = { levels = { l02_garbage = { fighters = 20 }, l07_military = { fighters = 0 } } }")
#: the same, with the ground held
GROUND_CENSUS = FOOT_CENSUS.replace('{ date = "2012-05-02 08:00",', '{ date = "2012-05-02 08:00", ' + GROUND + ',')
#: goodwill toward you, you, and a stalker (id 77) to kill
KILLS = """
GW = {}
relation_registry.change_community_goodwill = function(f, id, d) assert(id == AC_ID) GW[f] = (GW[f] or 0) + d end
AC_ID = 0
ACTOR = { id = function() return 0 end }
function IsStalker(o) return o and o.stalker end
function npc(comm) return { stalker = true, id = function() return 77 end, character_community = function() return comm end } end
"""


def consequences(src):
    """your members settled on others' ground strain your pair with each holder a day, by their steps
    (members who came from the holder don't count) and the holder's share, up to the cap; an ally
    doesn't mind; a stalker you kill on a faction's ground costs its goodwill unless it's at war with
    the victim's faction or the victim is its own; MCM's sliders; the page's list where you are"""
    w = World(src, FOOT_SETUP + KILLS)
    w.census(GROUND_CENSUS)
    inf = w.env.INFLUENCE
    check((inf["l02_garbage"]["dolg"], inf["l02_garbage"]["killer"], inf["l02_garbage"]["monster"], inf["l03_agroprom"]["killer"])
          == (0.6, 0.2, None, 0.5), "the ground: %s" % dict(inf["l02_garbage"]))
    # encroachment: on Garbage, Duty holds 0.6, but your four there came from Duty: no strain from
    # Duty; the Mercenaries hold 0.2 and see four outsiders; on Agroprom they hold 0.5 and see two
    enc = w.env.encroachment(w.eval(GROUND_CENSUS))
    got = {f: enc[f] for f in ("dolg", "killer", "freedom")}
    want = {"dolg": None, "killer": -(40 * 0.4 * 0.2 + 40 * 0.2 * 0.5), "freedom": None}
    check(got["dolg"] is None and got["freedom"] is None and abs(got["killer"] - want["killer"]) < 1e-9,
          "the strain: %s, not %s" % (got, want))
    # an ally doesn't mind
    w.run('REL["killer>fotz_own"] = 1000')
    check(w.env.encroachment(w.eval(GROUND_CENSUS))["killer"] is None, "an ally strained")
    w.run('REL["killer>fotz_own"] = 0')
    # the cap, and MCM's slider
    w.run('for i = 10, 30 do fotz_faction.F.members[i] = { mother = "ecolog" }; MEMBER_LV[i] = "l07_military" end')
    check(w.env.encroachment(w.eval(GROUND_CENSUS))["killer"] == -40, "the cap: %s" % w.env.encroachment(w.eval(GROUND_CENSUS))["killer"])
    w.run('MCM["fotz/encroach_max"] = 10')
    check(w.env.encroachment(w.eval(GROUND_CENSUS))["killer"] == -10, "the slider at 10")
    w.run('MCM["fotz/encroach_max"] = 0')
    check(next(iter(w.env.encroachment(w.eval(GROUND_CENSUS)).keys()), None) is None, "a strain with the slider at 0")
    w.run('MCM["fotz/encroach_max"] = nil')
    # the page: where you are (Garbage), the Mercenaries; not Duty
    s = w.env.strained_here()
    check([s[i].f for i in range(1, len(s) + 1)] == ["killer"], "strained here: %s" % [s[i].f for i in range(1, len(s) + 1)])
    # instigation: a Loner you kill on Garbage costs Duty 9 (15 x 0.6) and the Mercenaries 3 (15 x 0.2)
    kill = w.eval("function(comm, killer) CALLBACKS.npc_on_death_callback(npc(comm), killer) end")
    kill("stalker", w.g.ACTOR)
    check((w.eval("GW.dolg"), w.eval("GW.killer")) == (-9, -3), "a Loner killed: %s, %s" % (w.eval("GW.dolg"), w.eval("GW.killer")))
    # Freedom, at war with Duty: only the Mercenaries mind; a Duty man: only the Mercenaries; Mercs: only Duty...
    # and the Mercenaries are at war with Duty: killing a Duty man costs them nothing
    w.run("GW = {}")
    kill("freedom", w.g.ACTOR)
    kill("actor_dolg", w.g.ACTOR)
    check((w.eval("GW.dolg"), w.eval("GW.killer")) == (None, -3), "Freedom and Duty killed: %s, %s" % (w.eval("GW.dolg"), w.eval("GW.killer")))
    # someone else's kill, or a silent kill of yours (the weapon's owner)
    w.run("GW = {}")
    kill("stalker", w.eval("npc('bandit')"))
    check(w.eval("GW.dolg") is None, "someone else's kill cost you")
    kill("stalker", w.eval("{ id = function() return 5 end, parent = function() return ACTOR end }"))
    check(w.eval("GW.dolg") == -9, "a silent kill of yours: %s" % w.eval("GW.dolg"))
    # the slider; no faction
    w.run('GW = {}; MCM["fotz/instigate_max"] = 0')
    kill("stalker", w.g.ACTOR)
    check(w.eval("GW.dolg") is None, "a kill cost goodwill with the slider at 0")
    w.run('MCM["fotz/instigate_max"] = nil; fotz_faction.F = nil')
    kill("stalker", w.g.ACTOR)
    check(w.eval("GW.dolg") is None, "a kill cost goodwill without a faction")
    check(any("on dolg's ground" in l for l in w.log()), "no log line")


#: the ground, the Monolith also holding one of Garbage's smarts
SCOPE_CENSUS = GROUND_CENSUS.replace("held = { dolg = 6, killer = 2, monster = 1 }",
                                     "held = { dolg = 6, killer = 2, monster = 1, monolith = 1 }")
#: a level's ground counted on demand (fotz_census.level_ground), and how often it was asked
LEVEL_GROUND = """
GROUND_CALLS = 0
fotz_census.level_ground = function(lv)
    GROUND_CALLS = GROUND_CALLS + 1
    if lv == "l02_garbage" then return { smarts = 10, held = { dolg = 6, killer = 2, monster = 1 } } end
    return { smarts = 3, held = {} }
end
"""


def kill_fn(w):
    return w.eval("function(comm) CALLBACKS.npc_on_death_callback(npc(comm), ACTOR) end")


def names(lst):
    return [lst[i].f for i in range(1, len(lst) + 1)]


def ground_before_census(src):
    """before the first census after a load (a level change is one), a kill counts the level's
    ground there and then, once (the page's strain list too); after the census its word holds, even
    for a level it found no ground on; the count failing is logged and costs nothing else"""
    w = World(src, FOOT_SETUP + KILLS + LEVEL_GROUND)
    kill = kill_fn(w)
    kill("stalker")
    check((w.eval("GW.dolg"), w.eval("GW.killer")) == (-9, -3),
          "a kill before the census: %s, %s" % (w.eval("GW.dolg"), w.eval("GW.killer")))
    kill("stalker")
    check(names(w.env.strained_here()) == ["killer"], "strained before the census: %s" % names(w.env.strained_here()))
    check(w.eval("GW.dolg") == -18 and w.g.GROUND_CALLS == 1, "a second kill: %s, the ground counted %s times"
          % (w.eval("GW.dolg"), w.g.GROUND_CALLS))
    w.census(SCOPE_CENSUS)
    w.run('GW = {}; HERE = "l04_darkvalley"')
    kill("stalker")
    check(w.g.GROUND_CALLS == 1 and w.eval("next(GW)") is None, "after the census: counted %s times, %s"
          % (w.g.GROUND_CALLS, w.eval("GW.dolg")))
    w = World(src, FOOT_SETUP + KILLS + "fotz_census.level_ground = function() error('no board') end")
    kill = kill_fn(w)
    kill("stalker")
    check(w.eval("next(GW)") is None and any("! the ground on l02_garbage" in l for l in w.log()),
          "a failed count: %s" % w.log()[-2:])


def strain_scope(src):
    """the strain only toward a faction politics has a pair of yours with: not the Monolith, nor the
    Mercenaries when your old faction's relation with them is fixed; none listed while politics
    stands down (it applies none)"""
    w = World(src, FOOT_SETUP + KILLS)
    w.census(SCOPE_CENSUS)
    enc = w.env.encroachment(w.eval(SCOPE_CENSUS))
    check(enc["monolith"] is None and enc["killer"] is not None, "the strain: %s" % dict(enc.items()))
    check(names(w.env.strained_here()) == ["killer"], "strained here: %s" % names(w.env.strained_here()))
    w.run("NO_PAIR.killer = true")
    check(w.env.encroachment(w.eval(SCOPE_CENSUS))["killer"] is None and names(w.env.strained_here()) == [],
          "strained without a pair: %s" % names(w.env.strained_here()))
    w.run('NO_PAIR.killer = nil; DOWN = "turned off in MCM"')
    check(names(w.env.strained_here()) == [], "strained while politics stands down: %s" % names(w.env.strained_here()))


def strain_companions(src):
    """your companions don't count as settled: two Duty men on the Army Warehouses, one joined as a
    companion, one a settler following you now, don't strain the Mercenaries there, nor are they
    listed; the footprint still counts them"""
    w = World(src, FOOT_SETUP + KILLS)
    w.census(SCOPE_CENSUS)
    before = w.env.encroachment(w.eval(SCOPE_CENSUS))["killer"]
    w.run('fotz_faction.F.members[40] = { mother = "dolg", via = "companion" }; MEMBER_LV[40] = "l07_military"')
    w.run('fotz_faction.F.members[41] = { mother = "dolg", via = "settler" }; MEMBER_LV[41] = "l07_military"')
    w.run("fotz_faction.is_companion = function(id) return id == 41 end")
    after = w.env.encroachment(w.eval(SCOPE_CENSUS))["killer"]
    check(abs(after - before) < 1e-9, "companions strained: %s, not %s" % (after, before))
    w.run('HERE = "l07_military"')
    check(names(w.env.strained_here()) == [], "companions strained here: %s" % names(w.env.strained_here()))
    w.census(SCOPE_CENSUS)
    check(abs(w.env.FOOT["killer"]["l07_military"] - 1.14) < 1e-9, "the footprint left out companions: %s"
          % w.env.FOOT["killer"]["l07_military"])


def instigation_scope(src):
    """only a faction's stalker costs goodwill: not an arena fighter, a zombie, or one of yours (in
    yours, or still in their old faction); a prefixed faction still counts"""
    w = World(src, FOOT_SETUP + KILLS)
    kill = kill_fn(w)
    w.census(SCOPE_CENSUS)
    for comm in ("arena_enemy", "zombied", "fotz_own"):
        kill(comm)
    w.run('fotz_faction.F.members[77] = { mother = "stalker" }')
    kill("stalker")
    check(w.eval("next(GW)") is None, "goodwill for a non-faction or a member: %s" % dict(w.g.GW.items()))
    w.run("fotz_faction.F.members[77] = nil")
    kill("actor_stalker")
    check((w.eval("GW.dolg"), w.eval("GW.killer")) == (-9, -3), "a Loner killed: %s, %s"
          % (w.eval("GW.dolg"), w.eval("GW.killer")))


def footprint(src):
    """your faction's footprint: the factions hostile to your members (all of them for a faction at
    war with yours, else those who came from a faction it's at war with) are drawn to levels they're
    on, by the members' steps and nearness, up to the cap; nothing for the dead, without a faction or
    with the slider at 0; the steer's exemptions; worked out again between censuses; the page's
    list"""
    w = World(src, FOOT_SETUP)
    w.census(FOOT_CENSUS)
    F = w.env.FOOT
    got = {(e, lv): F[e][lv] for e in ("freedom", "killer", "bandit", "army", "dolg", "csky")
           if F[e] for lv in ("l02_garbage", "l03_agroprom", "l07_military") if F[e][lv]}
    want = {("freedom", "l02_garbage"): 1.2,                     # four Duty members on Garbage ...
            ("freedom", "l03_agroprom"): 1.1,                    # ... and next door, from Garbage's squads
            ("killer", "l02_garbage"): 1.2, ("killer", "l03_agroprom"): 1.1, ("killer", "l07_military"): 1.04,
            ("bandit", "l02_garbage"): 1.25,                     # at war with yours: all six, two of them half
            ("bandit", "l03_agroprom"): 1.2}                     # next door: the two there whole, four half
    check(set(got) == set(want) and all(abs(got[k] - want[k]) < 1e-9 for k in want), "the pull: %s" % got)
    # the scores: Freedom's squads to Garbage; the Mercenaries to Duty's s2 on Agroprom, steered and drawn
    got = [w.eval('score(103, "freedom")'), w.eval('score(102, "killer")'), w.eval('score(103, "army")'),
           w.eval('score(900, "freedom")')]
    check(all(abs(a - b) < 1e-9 for a, b in zip(got, [12, 13.75, 10, 10])), "scores %s" % got)
    w.run('STORY[901] = "story_squad"')
    check(w.eval('score(103, "freedom", 901)') == 10, "a story squad drawn")
    log = [l for l in w.log() if "your footprint draws on" in l]
    check(log and "your footprint draws on 7 levels" in log[0], "log %s" % log)
    # the page's list where you are: the strongest first
    here = w.env.drawn_here()
    check([here[i].f for i in range(1, len(here) + 1)][0] == "bandit" and len(here) == 3, "drawn here: %s"
          % [here[i].f for i in range(1, len(here) + 1)])
    # between censuses: a member leaves, and the pull follows on the next look
    w.run('fotz_faction.F.members[4] = nil; NOW = 31000')
    w.run('for _, fn in pairs(CALLBACKS) do end')
    w.g.CALLBACKS["actor_on_update"]()
    check(w.env.FOOT["freedom"]["l02_garbage"] == 1.15, "after a member left: %s" % w.env.FOOT["freedom"]["l02_garbage"])
    # MCM's slider, in percent
    w.run('MCM["fotz/footprint_max"] = 100')
    w.census(FOOT_CENSUS)
    check(abs(w.env.FOOT["freedom"]["l02_garbage"] - 1.3) < 1e-9, "the slider at 100: %s" % w.env.FOOT["freedom"]["l02_garbage"])
    w.run('MCM["fotz/footprint_max"] = 0')
    w.census(FOOT_CENSUS)
    check(next(iter(w.env.FOOT.keys()), None) is None, "drawn with the slider at 0")
    # the steer off: nothing shown
    w.run('MCM["fotz/footprint_max"] = nil')
    w.census(FOOT_CENSUS)
    w.run('MCM["fotz/territory"] = false')
    w.census(FOOT_CENSUS)
    check(len(w.env.drawn_here()) == 0, "shown with the steer off")
    # no faction: nothing
    w = World(src, FOOT_SETUP + "fotz_faction.F = nil")
    w.census(FOOT_CENSUS)
    check(next(iter(w.env.FOOT.keys()), None) is None, "drawn without a faction")
    # a footprint that fails doesn't stop the census
    w = World(src, FOOT_SETUP + "fotz_perks.member_level = function() error('boom') end")
    w.census(FOOT_CENSUS)
    check(any("! the footprint" in l for l in w.log()) and w.env.STEER["dolg"] is not None, "a failing footprint")
    # and between censuses: logged, not raised
    w.run("NOW = 31000")
    w.g.CALLBACKS["actor_on_update"]()
    check(w.env.update_footprint() == 0, "a failing footprint between censuses")


def shipped_config(src):
    text = open(CONFIG, encoding="utf-8").read()
    sec = re.search(r"(?ms)^\[territory\](.*?)(^\[|\Z)", text).group(1)
    vals = {k: float(v) for k, v in re.findall(r"(?m)^(\w+)\s*=\s*([-\d.]+)", sec)}
    check(vals == {"k": 0.5, "lo": 0.6, "hi": 1.5, "footprint": 0.5, "footprint_reach": 0.4, "encroach": 40,
                   "instigate": 15},
          "the shipped [territory]: %s" % vals)
    c = World(src).env.cfg
    check((vals["footprint"], vals["footprint_reach"], vals["encroach"], vals["instigate"])
          == (c.footprint, c.reach, c.encroach, c.instigate),
          "the script's defaults: %s, %s, %s, %s" % (c.footprint, c.reach, c.encroach, c.instigate))
    check(vals["lo"] < 1 < vals["hi"], "the bounds don't straddle 1")
    # with MCM its sliders set these (MCM returns a slider's own default): the defaults agree
    mcm = open(os.path.join(GD, "scripts", "fotz_mcm.script"), encoding="utf-8").read()
    defs = {k: float(v) for k, v in re.findall(r'id = "(\w+_max)",[^}]*\bdef = ([-\d.]+)', mcm)}
    got = (defs.get("footprint_max"), defs.get("encroach_max"), defs.get("instigate_max"))
    check(got == (vals["footprint"] * 100, vals["encroach"], vals["instigate"]), "MCM's slider defaults: %s" % (got,))
    check(re.search(r"(?m)^;.*MCM.*slider", sec), "the [territory] comments don't say MCM's sliders set these")


def run(src):
    multiplier(src)
    steer(src)
    left_alone(src)
    switch(src)
    fronts(src)
    footprint(src)
    consequences(src)
    ground_before_census(src)
    strain_scope(src)
    strain_companions(src)
    instigation_scope(src)
    shipped_config(src)
    return "12 scenarios"


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
