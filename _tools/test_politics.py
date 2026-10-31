"""Run fotz_politics.script under LuaJIT 2.0 against a stateful relation matrix and check what it does.

Scenarios: kills lead to a war, quiet days to a truce, and the truce holds the line; ground taken
and fronts name a war's cause and voice, with the news levels; a common enemy makes an alliance
that lapses once the enemy is gone; each reason to stand down puts the game's relations back;
a relation another mod changed becomes the new start; a save and load rebuild the same matrix;
offline kills pass through the wrapper; the player's kills, silent kills and ignored kills; the
caps; and the shipped config's pairs.

    python test_politics.py            the real script
    python test_politics.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(HERE, "..", "gamedata")
SCRIPT = os.path.join(GD, "scripts", "fotz_politics.script")
REAL_CONFIG = os.path.join(GD, "configs", "plugins", "fotz_politics.ltx")
ENG = os.path.join(GD, "configs", "text", "eng", "st_fotz.xml")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "budget": ("local move = clamp(pending, -cfg.daily_budget, cfg.daily_budget)", "local move = pending"),
    "no_recover": ("        d = d - d * cfg.recover\n", "        d = d\n"),
    "recover_at_war": ('if not (ev and ev.kind == "war") then', "if true then"),
    "truce_hold": ("d = math.max(d, ENEMIES + 1 - base)", "d = d"),
    "truce_damp": ("        move = move / 2\n", "        move = move\n"),
    "quiet": (">= cfg.quiet_days", ">= 0"),
    "min_war": ("days_between(ev.since, day) >= cfg.min_war_days", "true"),
    "fixed_pairs": ("if not fixed_pair[a .. \"/\" .. b] then", "if true then"),
    "fixed_factions": ("if not fixed[f] then", "if true then"),
    "actor_rows": ('{ "actor_" .. a, b }, { b, "actor_" .. a },', ""),
    "anchor_shift": ("anchor[k] = live - (written[k] - anchor[k])", "anchor[k] = anchor[k]"),
    "dynamic": ('if ui_options and ui_options.get("alife/general/dynamic_relations") then', "if false then"),
    "dfrc": ("if dynamic_faction_relations_customizer then", "if false then"),
    "fluid": ("if game_relations and game_relations.faction_cares then", "if false then"),
    "warfare": ("if IsWarfare and IsWarfare() then", "if false then"),
    "warfare_flag": ("if IsWarfare and IsWarfare() then", "if _G.WARFARE then"),
    "off_keeps": ("local d = on and (state().drift[p.key] or 0) or 0", "local d = state().drift[p.key] or 0"),
    "player_weight": ("if killer:id() == AC_ID then\n        comm, weight = get_actor_true_community(), cfg.player_kill",
                      "if killer:id() == AC_ID then\n        comm, weight = get_actor_true_community(), nil"),
    "silent_kill": ("if owner and owner:id() == AC_ID then", "if false then"),
    "rank_weight": ("(cfg.rank_weight[rank] or 1)", "1"),
    "forward": ("        return orig(...)\n", "        return orig()\n"),
    "ground_voice": ('note(t, p, "ground", cfg.ground, smart, was,', 'note(t, p, "ground", cfg.ground, smart, now,'),
    "common_either": ("at_war(p.a, f) and at_war(p.b, f)", "at_war(p.a, f) or at_war(p.b, f)"),
    "no_lapse": ('elseif ev and ev.kind == "alliance" and after < FRIENDS then',
                 'elseif ev and ev.kind == "alliance" and false then'),
    "same_day": ("    if st.day == day then\n        return\n    end\n", ""),
    "first_ticks": ("if first or not active() then", "if not active() then"),
    "any_version": ('if type(d) == "table" and d.v == SAVE_VERSION then', 'if type(d) == "table" then'),
    "news_level": ('if lv == "off" or (level == "all" and lv ~= "all") then', 'if lv == "off" then'),
    "news_cap": ("if shown < 3 and say(", "if say("),
    "pending_cap": ("clamp((st.pending[k] or 0) + g.delta, -cfg.pending_max, cfg.pending_max)",
                    "(st.pending[k] or 0) + g.delta"),
    "lo_cap": ("d = clamp(d + move, p.lo, p.hi)", "d = d + move"),
    "string_id": ('"st_fotz_news_alliance_plain"', '"st_fotz_news_alliance_plane"'),
    "news_unlogged": ('        log("news: %s", text)\n', ""),
    "base_names": ("    local s = game.translate_string(id)\n", "    local s = id\n"),
}

TEST_CONFIG = """
[politics]
kill = -10
player_kill = 0.5
ground = -150
front = -40
common_enemy = 60
recover = 0.1
daily_budget = 400
pending_max = 1500
limit = 4750
min_war_days = 3
quiet_days = 2
max_war_days = 14
truce_relation = -600
truce_days = 5
history = 50
[rank_weight]
novice = 1
veteran = 2
[caps]
default = -3000, 2500
[fixed_factions]
monolith
greh
isg
renegade
[fixed_pairs]
pair_1 = army,bandit
pair_10 = dolg,freedom
"""

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end
WRITES = {}
REL = {}
relation_registry = {
    community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end,
    set_community_relation = function(a, b, v) WRITES[#WRITES + 1] = a .. ">" .. b; REL[a .. ">" .. b] = v end,
}
MCM = {}
ui_mcm = { get = function(id) return MCM[id] end }
OPT = {}
ui_options = { get = function(id) return OPT[id] end }
NEWS = {}
news_manager = { send_tip = function(actor, text, timeout, sender, showtime) NEWS[#NEWS + 1] = sender .. "|" .. text end }
-- the base game's own names, singular for some: Factions shows its own group names
NAMES = { dolg = "Duty", freedom = "Freedom", killer = "Mercenary", csky = "Clear Sky", stalker = "Free stalkers",
          bandit = "Bandit", army = "Military", ecolog = "Ecologist" }
STR = {}
game = { translate_string = function(id) return NAMES[id] or STR[id] or id end }
db = { actor = {} }
AC_ID = 0
function IsStalker(o) return o ~= nil and o.stalker == true end
ACTOR_COMM = "dolg"
function get_actor_true_community() return ACTOR_COMM end
ranks = { get_obj_rank_name = function(o) return o.rank end, get_se_obj_rank_name = function(se) return se.rank end }
function alife_character_community(se) return se.comm end
OFFLINE_CALLS = {}
game_relations = { offline_npc_on_death = function(...)
    OFFLINE_CALLS[#OFFLINE_CALLS + 1] = select("#", ...)
    return "orig"
end }
DATE = "2012-05-01"
LISTENERS = {}
fotz_census = { game_date = function() return DATE .. " 08:00" end,
                listen = function(fn) LISTENERS[#LISTENERS + 1] = fn end }
SIMBOARD = { smarts_by_names = setmetatable({}, { __index = function(_, k) return k end }) }
smart_terrain = { get_smart_terrain_name = function(se) return "Place " .. se end }
CALLBACKS = {}
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end
function ini_file(path)
    local ini = {}
    function ini:section_exist(s) return INI[s] ~= nil end
    function ini:line_count(s) return #(INI[s] or {}) end
    function ini:r_line(s, i) local l = INI[s][i + 1] return true, l[1], l[2] end
    function ini:r_float_ex(s, k)
        for _, l in ipairs(INI[s] or {}) do if l[1] == k then return tonumber(l[2]) end end
    end
    return ini
end

ACTOR = { stalker = false, id = function() return 0 end, parent = function() return nil end }
function npc(comm, rank)
    return { stalker = true, comm = comm, rank = rank, id = function() return 500 end,
             character_community = function(self) return self.comm end, parent = function() return nil end }
end
function kill(victim, killer, rank, n)
    for i = 1, n or 1 do
        CALLBACKS.npc_on_death_callback(npc(victim, rank or "novice"), killer == "actor" and ACTOR or npc(killer, "novice"))
    end
end
function day(d, smarts, fronts)
    DATE = d
    local c = { date = d .. " 08:00", smarts = smarts or {}, fronts = fronts or {} }
    for _, fn in ipairs(LISTENERS) do fn(c) end
end
-- a value as Lua source, as a save would carry it to the next game
function dump(v)
    local ty = type(v)
    if ty == "table" then
        local out = {}
        for k, x in pairs(v) do
            out[#out + 1] = "[" .. dump(k) .. "] = " .. dump(x)
        end
        return "{ " .. table.concat(out, ", ") .. " }"
    elseif ty == "string" then
        return string.format("%q", v)
    elseif ty == "number" then
        return string.format("%.17g", v)
    end
    return tostring(v)
end
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def parse_ltx(text):
    """[(section, [(key, value)])] in file order, comments dropped."""
    out, cur = [], None
    for line in text.splitlines():
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^\[([^\]]+)\]", line)
        if m:
            cur = (m.group(1), [])
            out.append(cur)
        elif "=" in line:
            k, v = line.split("=", 1)
            cur[1].append((k.strip(), v.strip()))
        else:
            cur[1].append((line, ""))
    return out


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def ini_lua(text):
    parts = []
    for sec, rows in parse_ltx(text):
        parts.append("[%s] = { %s }" % (lua_str(sec), ", ".join("{ %s, %s }" % (lua_str(k), lua_str(v)) for k, v in rows)))
    return "INI = { " + ", ".join(parts) + " }"


def strings_lua():
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    return "\n".join("STR[%s] = %s" % (lua_str(s.get("id")), lua_str(s.findtext("text"))) for s in root.iter("string"))


class World:
    def __init__(self, src, config=TEST_CONFIG, anchors=None, m_data=None, pre=None):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(WORLD)
        if pre:
            self.lua.execute(pre)
        self.lua.execute(ini_lua(config))
        self.lua.execute(strings_lua())
        for k, v in (anchors or {}).items():
            self.g.REL[k] = v
        self.env = self.lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                                 "local f = assert(loadstring(src, 'fotz_politics')) setfenv(f, env) f() return env end")(src)
        self.env.on_game_start()
        self.cb = self.g.CALLBACKS
        self.cb["load_state"](self.lua.eval(m_data or "{}"))
        self.cb["actor_on_first_update"]()

    def run(self, code):
        return self.lua.execute(code)

    def rel(self, cell):
        return self.g.REL[cell] or 0

    def drift(self, key):
        return self.env.S.drift[key]

    def pending(self, key):
        return self.env.S.pending[key]

    def event(self, key):
        ev = self.env.S.events[key]
        return ev and ev.kind

    def history(self):
        h = self.env.S.history
        return [h[i].kind for i in range(1, len(h) + 1)]

    def news(self):
        return list(self.g.NEWS.values())

    def log(self):
        return list(self.g.LOG.values())


CELLS = ["dolg>killer", "killer>dolg", "actor_dolg>killer", "killer>actor_dolg", "dolg>actor_killer", "actor_killer>dolg"]
DK_ANCHORS = {"dolg>killer": 0, "killer>dolg": 0, "actor_dolg>killer": 100, "killer>actor_dolg": 100,
              "dolg>actor_killer": -50, "actor_killer>dolg": -50}


def war_and_truce(src):
    w = World(src, anchors=DK_ANCHORS)
    check(len(w.g.WRITES) == 0, "the first load wrote cells with nothing to change")
    w.run('kill("dolg", "killer", "veteran", 5)')
    w.run('day("2012-05-01")')
    check(w.drift("dolg/killer") is None and w.pending("dolg/killer") is None, "the first census moved a pair")
    w.run('day("2012-05-01")')
    w.run('kill("dolg", "killer", "veteran", 60)')
    check(w.env.S.kills["dolg/killer"] == 120, "kills weighed %s" % w.env.S.kills["dolg/killer"])
    w.run('day("2012-05-02")')
    check(w.drift("dolg/killer") == -400 and w.pending("dolg/killer") == -800,
          "day 2: drift %s, pending %s" % (w.drift("dolg/killer"), w.pending("dolg/killer")))
    got = {c: w.rel(c) for c in CELLS}
    want = {c: DK_ANCHORS[c] - 400 for c in CELLS}
    check(got == want, "the cells %s, not %s" % (got, want))
    w.run('day("2012-05-02")')
    check(w.drift("dolg/killer") == -400, "a second census the same day moved the pair")
    w.run('day("2012-05-03")')
    check(w.drift("dolg/killer") == -760, "day 3: drift %s" % w.drift("dolg/killer"))
    w.run('day("2012-05-04")')
    check(w.drift("dolg/killer") == -1084 and w.event("dolg/killer") == "war",
          "day 4: drift %s, event %s" % (w.drift("dolg/killer"), w.event("dolg/killer")))
    news = w.news()
    check(news == ["dolg|Duty: Too many of ours have died at the hands of Mercenaries. From today we are at war with them."],
          "war news %s" % news)
    check("[fotz-politics] news: Duty: Too many of ours have died at the hands of Mercenaries. From today we are at war "
          "with them." in w.log(), "the news wasn't logged")
    for d in ("05", "06"):
        w.run('day("2012-05-%s")' % d)
        check(w.event("dolg/killer") == "war" and w.drift("dolg/killer") == -1084,
              "day %s: %s, drift %s" % (d, w.event("dolg/killer"), w.drift("dolg/killer")))
    w.run('day("2012-05-07")')
    check(w.event("dolg/killer") == "truce" and w.drift("dolg/killer") == -600,
          "day 7: %s, drift %s" % (w.event("dolg/killer"), w.drift("dolg/killer")))
    check(w.news()[-1] == "dolg|Duty: The line with Mercenaries has gone quiet. We hold our fire, for now.",
          "truce news %s" % w.news()[-1])
    # fighting goes on through the truce: it counts half, and the truce holds the line above -1000
    w.run('day("2012-05-08")')
    w.run('kill("killer", "dolg", "veteran", 100)')
    w.run('day("2012-05-09")')
    check(w.drift("dolg/killer") == -686 and w.pending("dolg/killer") == -1100,
          "truce day 9: drift %s, pending %s" % (w.drift("dolg/killer"), w.pending("dolg/killer")))
    for d in (10, 11, 12):
        w.run('kill("killer", "dolg", "veteran", 100)')
        w.run('day("2012-05-%02d")' % d)
    check(w.drift("dolg/killer") == -999 and w.event("dolg/killer") is None,
          "day 12: drift %s, event %s" % (w.drift("dolg/killer"), w.event("dolg/killer")))
    kinds = w.history()
    check(kinds == ["war", "war_over", "truce", "truce_over"], "history %s" % kinds)
    check(all("%" not in l for l in w.log()), "a %% reached the log")
    check(not any(c.startswith("dolg>freedom") or "monolith" in c for c in w.g.WRITES.values()),
          "a fixed pair or faction was written")
    return w


def ground_and_news(src):
    w = World(src)
    w.run('MCM["fotz/news"] = "all"')
    w.run('day("2012-05-01", { s1 = "freedom", s2 = "freedom", s3 = "freedom", s4 = "freedom", s5 = "freedom", s6 = "freedom", s9 = "dolg" })')
    w.run('day("2012-05-02", { s1 = "killer", s2 = "killer", s3 = "killer", s4 = "killer", s5 = "killer", s6 = "freedom", s9 = "freedom" },'
          ' { ["freedom/killer"] = { n = 2, at = "s7" } })')
    check(w.drift("freedom/killer") == -400 and w.pending("freedom/killer") == -430,
          "day 2: drift %s, pending %s" % (w.drift("freedom/killer"), w.pending("freedom/killer")))
    check(w.drift("dolg/freedom") is None, "a fixed pair moved")
    check(w.news() == ["killer|Mercenaries: We took Place s1 from Freedom.",
                       "killer|Mercenaries: We took Place s2 from Freedom.",
                       "killer|Mercenaries: We took Place s3 from Freedom."], "ground news %s" % w.news())
    w.run('day("2012-05-03", { s1 = "killer", s2 = "killer", s3 = "killer", s4 = "killer", s5 = "killer", s6 = "freedom" },'
          ' { ["freedom/killer"] = { n = 5, at = "s7" } })')
    w.run('day("2012-05-04", { s1 = "killer", s2 = "killer", s3 = "killer", s4 = "killer", s5 = "killer", s6 = "killer" },'
          ' { ["freedom/killer"] = { n = 5, at = "s7" } })')
    check(w.event("freedom/killer") == "war", "no war on day 4: drift %s" % w.drift("freedom/killer"))
    check(w.news()[3:] == ["freedom|Freedom: Mercenaries took Place s6 from us. From today we are at war with them.",
                           "killer|Mercenaries: We took Place s6 from Freedom."], "day 4 news %s" % w.news()[3:])
    w.run('MCM["fotz/news"] = "events"')
    w.run('day("2012-05-05", { s1 = "killer", s2 = "killer", s3 = "killer", s4 = "killer", s5 = "freedom", s6 = "killer" })')
    check(len(w.news()) == 5, "ground news at the events level: %s" % w.news()[5:])
    w.run('MCM["fotz/news"] = "off"')
    w.run('day("2012-05-12")')
    check(w.event("freedom/killer") == "truce" and len(w.news()) == 5, "news with the news off: %s" % w.news()[5:])


def alliance(src):
    anchors = {"csky>dolg": 900, "dolg>csky": 900}
    m = """{ fotz = { v = 1, day = "2012-05-09",
        events = { ["dolg/killer"] = { kind = "war", since = "2012-05-01", a = "dolg", b = "killer" },
                   ["csky/killer"] = { kind = "war", since = "2012-05-01", a = "csky", b = "killer" } },
        drift = { ["dolg/killer"] = -1100, ["csky/killer"] = -1100 },
        last_fight = { ["dolg/killer"] = "2012-05-09", ["csky/killer"] = "2012-05-09" } } }"""
    w = World(src, anchors=anchors, m_data=m)
    check(w.rel("dolg>killer") == -1100 and w.rel("killer>actor_csky") == -1100, "the saved drift wasn't applied")
    fronts = '{ ["dolg/killer"] = { n = 1, at = "x" }, ["csky/killer"] = { n = 1, at = "y" } }'
    w.run('day("2012-05-10", {}, %s)' % fronts)
    check(w.drift("csky/dolg") == 60, "day 10: drift %s" % w.drift("csky/dolg"))
    w.run('day("2012-05-11", {}, %s)' % fronts)
    check(w.event("csky/dolg") == "alliance" and w.drift("csky/dolg") == 114,
          "day 11: %s, drift %s" % (w.event("csky/dolg"), w.drift("csky/dolg")))
    check(w.news()[-1] == "csky|Clear Sky: We stand with Duty against Mercenaries. Treat them as friends.",
          "alliance news %s" % w.news()[-1])
    check(w.drift("csky/stalker") is None, "a pair with one side at war got pressure")
    lapsed = None
    for d in range(12, 31):
        w.run('day("2012-05-%02d")' % d)
        if w.event("csky/dolg") != "alliance":
            lapsed = d
            break
    check(lapsed == 20, "the alliance lapsed on day %s" % lapsed)
    check(w.news()[-1] == "csky|Clear Sky: Our alliance with Duty is over.", "lapse news %s" % w.news()[-1])
    check(w.event("dolg/killer") == "truce" or w.event("dolg/killer") is None, "the war didn't end")


def stand_down(src):
    m = '{ fotz = { v = 1, day = "2012-05-09", drift = { ["dolg/killer"] = -500 } } }'
    # the base warfare.script sets _G.WARFARE true at every start and false on its first update,
    # after Factions' first update: outside Warfare mode the load still applies the drift
    w = World(src, anchors=DK_ANCHORS, m_data=m, pre="WARFARE = true; function IsWarfare() return false end")
    check(w.rel("dolg>killer") == -500, "outside Warfare mode, with _G.WARFARE still set, the load applied %s"
          % w.rel("dolg>killer"))
    w = World(src, anchors=DK_ANCHORS, m_data=m)
    check({c: w.rel(c) for c in CELLS} == {c: DK_ANCHORS[c] - 500 for c in CELLS}, "the load didn't apply the drift")
    switches = [('OPT["alife/general/dynamic_relations"] = true', 'OPT["alife/general/dynamic_relations"] = nil'),
                ('MCM["fotz/politics"] = false', 'MCM["fotz/politics"] = nil'),
                ("dynamic_faction_relations_customizer = {}", "dynamic_faction_relations_customizer = nil"),
                ("game_relations.faction_cares = function() end", "game_relations.faction_cares = nil"),
                ("function IsWarfare() return true end", "IsWarfare = nil")]
    for on, off in switches:
        w.run(on)
        w.cb["on_option_change"]()
        check({c: w.rel(c) for c in CELLS} == DK_ANCHORS, "standing down (%s) left %s" % (on, {c: w.rel(c) for c in CELLS}))
        w.run('kill("dolg", "killer", "veteran", 3)')
        check(w.env.S.kills["dolg/killer"] is None, "a kill counted while standing down (%s)" % on)
        w.run(off)
        w.cb["on_option_change"]()
        check(w.rel("dolg>killer") == -500, "back on (%s): %s" % (on, w.rel("dolg>killer")))
    check(any("standing down: Warfare mode is on" in l for l in w.log()), "the stand-down wasn't logged")
    # something else sets a cell: its value is the new start
    w.run('REL["dolg>killer"] = 2000')
    w.cb["on_option_change"]()
    w.run('day("2012-05-10")')
    check(w.rel("dolg>killer") == 2050 and w.rel("killer>dolg") == -450,
          "after another mod's change: %s, %s" % (w.rel("dolg>killer"), w.rel("killer>dolg")))


def save_and_load(src, w):
    before = {c: w.rel(c) for c in CELLS}
    m = w.lua.eval("{}")
    w.cb["save_state"](m)
    w2 = World(src, anchors=DK_ANCHORS, m_data=w.lua.eval("dump")(m))
    after = {c: w2.rel(c) for c in CELLS}
    check(after == before, "a load rebuilt %s, not %s" % (after, before))
    check(w2.history() == ["war", "war_over", "truce", "truce_over"], "history lost: %s" % w2.history())
    w3 = World(src, anchors=DK_ANCHORS, m_data='{ fotz = { v = 99, drift = { ["dolg/killer"] = -900 } } }')
    check(w3.rel("dolg>killer") == 0 and any("starting over" in l for l in w3.log()),
          "a save of another version was read")


def kills(src):
    w = World(src)
    r = w.lua.eval('function() return game_relations.offline_npc_on_death({ comm = "killer", rank = "veteran" },'
                   ' { comm = "dolg", rank = "novice" }, "extra") end')()
    check(r == "orig" and w.g.OFFLINE_CALLS[1] == 3, "the wrapper returned %s, passed %s args" % (r, w.g.OFFLINE_CALLS[1]))
    check(w.env.S.kills["dolg/killer"] == 2, "the offline kill weighed %s" % w.env.S.kills["dolg/killer"])
    w.run('kill("killer", "actor", "novice", 1)')
    check(w.env.S.kills["dolg/killer"] == 2.5, "the player's kill: %s" % w.env.S.kills["dolg/killer"])
    w.run('CALLBACKS.npc_on_death_callback(npc("killer", "novice"), { stalker = false, id = function() return 9 end,'
          ' parent = function() return ACTOR end })')
    check(w.env.S.kills["dolg/killer"] == 3, "the silent kill: %s" % w.env.S.kills["dolg/killer"])
    w.run('CALLBACKS.npc_on_death_callback(npc("killer", "novice"), { stalker = false, id = function() return 9 end,'
          ' parent = function() return nil end })')
    w.run('kill("dolg", "freedom", "veteran", 4)')
    w.run('CALLBACKS.npc_on_death_callback({ stalker = false }, npc("dolg", "novice"))')
    check(w.env.S.kills["dolg/killer"] == 3 and w.env.S.kills["dolg/freedom"] is None,
          "ignored kills counted: %s" % dict(w.env.S.kills.items()))


def caps(src):
    w = World(src)
    w.run('day("2012-05-01")')
    low = 0
    for d in range(2, 20):
        w.run('kill("army", "killer", "veteran", 60)')
        w.run('day("2012-05-%02d", {}, { ["army/killer"] = { n = 1, at = "z" } })' % d)
        low = min(low, w.drift("army/killer") or 0)
        check(abs(w.pending("army/killer") or 0) <= 1500, "pending %s" % w.pending("army/killer"))
    check(low == -3000, "the lowest drift was %s" % low)


def real_config(src):
    w = World(src, config=open(REAL_CONFIG, encoding="utf-8").read())
    keys = sorted(p.key for p in w.env.PAIRS.values())
    want = ["army/csky", "army/freedom", "army/killer", "bandit/ecolog", "bandit/freedom", "bandit/killer",
            "csky/dolg", "csky/ecolog", "csky/freedom", "csky/killer", "csky/stalker", "dolg/killer",
            "ecolog/freedom", "ecolog/killer", "freedom/killer", "killer/stalker"]
    check(keys == want, "the shipped config's pairs: %s" % keys)
    c = w.env.cfg
    check(c.rank_weight["legend"] == 4 and c.max_war_days == 14 and c.caps["default"][1] == -3000,
          "the shipped config read wrong")


def strings(src):
    """Every news id the script can build, and every MCM option's label, is in the English table."""
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    want = set(re.findall(r'"(st_fotz_news_\w+)"', src)) - {"st_fotz_news_war_"}
    want |= {"st_fotz_news_war_" + c for c in ("kills", "ground", "front")}
    mcm = open(os.path.join(GD, "scripts", "fotz_mcm.script"), encoding="utf-8").read()
    for opt in re.findall(r'id = "(\w+)", type = "(?:check|list)"', mcm):
        want |= {"ui_mcm_fotz_" + opt, "ui_mcm_fotz_" + opt + "_desc"}
    want |= {"ui_mcm_lst_" + k for k in re.findall(r'\{ "\w+", "(fotz_news_\w+)" \}', mcm)}
    check(len(want) == 17, "%d string ids were looked for, not 17" % len(want))
    want |= {"st_fotz_faction_" + f for f in ("stalker", "bandit", "csky", "dolg", "freedom", "killer", "army",
                                              "ecolog", "monolith", "renegade", "greh", "isg")}
    missing = sorted(want - have)
    check(not missing, "string ids missing from the English table: %s" % missing)


def run(src):
    strings(src)
    w = war_and_truce(src)
    ground_and_news(src)
    alliance(src)
    stand_down(src)
    save_and_load(src, w)
    kills(src)
    caps(src)
    real_config(src)
    return "8 scenarios, 16 pairs from the shipped config"


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
        print("FAIL (error): %s: %s" % (type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
