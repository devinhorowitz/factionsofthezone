"""Run fotz_api.script, the hooks other mods rely on (docs/HOOKS.md), under LuaJIT 2.0 against
stand-ins for Factions' own scripts and the game's callbacks, and check its contract.

Checked: VERSION, and the four callbacks declared as it loads; a send reaches every handler, a
handler's error is logged and kept inside the send, and a name it never declared isn't sent; the
census as other mods get it (its date, cause, holders, contested smarts and each faction's squads,
fighters and fighters by level, and nothing else), sent after it's kept, so a handler that changes
it changes nothing; the reads: who holds what (the save's holders before the first census), what's
contested, a faction's smarts and strength, the fronts and who leads each, where a pair stands
(its start without the drift while politics runs, the live value while it stands down), the events
in force by date, the history newest first, the last census, your faction with its living members;
active and why not; every table handed out a copy; the nudges passed to politics, and refused, or
neutral, without it.

    python test_api.py            the real script
    python test_api.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import sys

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "gamedata", "scripts", "fotz_api.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "undeclared": ("        AddScriptCallback(name)\n", ""),
    "send_unguarded": ("local ok, err = pcall(SendScriptCallback, name, t)", "local ok, err = true, SendScriptCallback(name, t)"),
    "send_any": ("    if not declared[name] then\n        return false\n    end\n", ""),
    "census_shared": ("smarts = copy(c.smarts or {}), contested", "smarts = c.smarts or {}, contested"),
    "census_view_reused": ('    local view = census_view(c)\n    send("fotz_on_census", view)', '    send("fotz_on_census", LAST)'),
    "levels_raw": ("            levels[lv] = at.fighters or 0\n", "            levels[lv] = at\n"),
    "holder_no_fallback": ("    local g = p and p.S and p.S.ground\n", "    local g = nil\n"),
    "strength_shared": ("    return e and copy(e) or nil\n", "    return e\n"),
    "fronts_no_leader": ("local win = T.leader and T.leader(f) or nil", "local win = nil"),
    "pair_start_down": ("start = on and live - drift or live", "start = live - drift"),
    "pair_event_shared": ("event = event_view(st.events and st.events[pr.key]) }", "event = st.events and st.events[pr.key] }"),
    "events_unsorted": ('return (x.since or "") .. x.a .. x.b < (y.since or "") .. y.a .. y.b',
                        'return (x.since or "") .. x.a .. x.b > (y.since or "") .. y.a .. y.b'),
    "history_oldest_first": ("for i = #h, math.max(1, #h - (tonumber(n) or #h) + 1), -1 do",
                             "for i = math.max(1, #h - (tonumber(n) or #h) + 1), #h do"),
    "history_shared": ("        out[#out + 1] = copy(h[i])\n", "        out[#out + 1] = h[i]\n"),
    "own_counts_dead": ("        if not m.dead then\n", "        if true then\n"),
    "own_unfounded": ("    if not (F and F.base) then\n", "    if not F then\n"),
    "active_down": ("    return why == nil, why\n", "    return true, why\n"),
    "contested_any": ("    return LAST ~= nil and LAST.contested_set[smart] == true\n", "    return LAST ~= nil\n"),
    "sides_shared": ("    return copy(p and p.SIDES or {})\n", "    return p and p.SIDES or {}\n"),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end
-- the game's callbacks (_g.script): declared names, and a send that calls every handler unguarded
ADDED = {}
function AddScriptCallback(name) ADDED[#ADDED + 1] = name end
HANDLERS = {}
SENDS = {}
function SendScriptCallback(name, t)
    SENDS[#SENDS + 1] = name
    for _, fn in ipairs(HANDLERS[name] or {}) do fn(t) end
end
REL = { ["killer>dolg"] = -1400, ["dolg>killer"] = -1300 }
relation_registry = { community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end }
DOWN = nil
POLITICS = {
    SIDES = { "dolg", "killer", "fotz_own" },
    S = { ground = { s1 = "dolg", s2 = "killer", s3 = "dolg" },
          drift = { ["dolg/killer"] = -400 }, pending = { ["dolg/killer"] = -300 }, trend = { ["dolg/killer"] = -100 },
          events = { ["dolg/killer"] = { kind = "war", a = "dolg", b = "killer", since = "2012-05-04", cause = "ground",
                                         at = "s1", voice = "dolg" },
                     ["bandit/stalker"] = { kind = "truce", a = "bandit", b = "stalker", since = "2012-05-02",
                                            ["until"] = "2012-05-07", voice = "bandit" } },
          history = { { kind = "war", a = "bandit", b = "stalker", day = "2012-05-01" },
                      { kind = "war_over", a = "bandit", b = "stalker", day = "2012-05-02", since = "2012-05-01" },
                      { kind = "truce", a = "bandit", b = "stalker", day = "2012-05-02" } } },
    standing_down = function() return DOWN end,
    faction_name = function(f) return "N:" .. f end,
    place_name = function(s) return "P:" .. s end,
    pair_of = function(x, y)
        local a, b = x, y
        if b < a then a, b = b, a end
        local k = a .. "/" .. b
        if k == "dolg/killer" or k == "bandit/stalker" then return { key = k, a = a, b = b } end
    end,
    grievance = function(a, b, amount, opts) GRIEF = { a, b, amount, opts and opts.at } return true end,
    set_place = function(s, w) PLACED = { s, w } return true end,
    clear_place = function(s) return s == "s1" end,
    place_weight = function(s) return s == "s1" and 2 or 1 end,
}
fotz_politics = POLITICS
fotz_territory = {
    FRONTS = { { level = "l02_garbage", a = "dolg", b = "killer", fa = 30, fb = 10 },
               { level = "l03_agroprom", a = "dolg", b = "killer", fa = 15, fb = 15 } },
    leader = function(f)
        if f.fa >= 2 / 3 * (f.fa + f.fb) then return f.a, f.b elseif f.fb >= 2 / 3 * (f.fa + f.fb) then return f.b, f.a end
    end }
fotz_faction = { F = { uid = "u1", name = "Wolves", mother = "dolg", founded = "2012-05-01", base = {},
                       members = { [5] = { name = "a" }, [6] = { name = "b", dead = true }, [7] = { name = "c" } } } }
CENSUS = { v = "1.0.0", cause = "day", date = "2012-05-05 08:00", real = "x", ms = 3,
           smarts = { s1 = "killer", s2 = "killer", s4 = "freedom" }, contested = { "s2" },
           fronts = { ["dolg/killer"] = { n = 1, at = "s2", smarts = { "s2" } } }, relations = { dolg = {} },
           factions = { dolg = { squads = 2, fighters = 9, story = 0, tiers = {}, ranks = {},
                                 levels = { l02_garbage = { squads = 2, fighters = 9 } } } } }
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def py(v):
    """A Lua value as Python: a table with keys 1..n as a list, any other as a dict."""
    if L.lua_type(v) != "table":
        return v
    keys = list(v.keys())
    if keys and sorted(k for k in keys if isinstance(k, int)) == list(range(1, len(keys) + 1)):
        return [py(v[i]) for i in range(1, len(keys) + 1)]
    return {k: py(v[k]) for k in keys}


def run(src):
    lua = L.LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    lua.execute(WORLD)
    env = lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                   "local f = assert(loadstring(src, 'fotz_api')) setfenv(f, env) f() return env end")(src)
    names = ["fotz_on_census", "fotz_on_ground_taken", "fotz_on_front_shift", "fotz_on_politics"]
    check(env.VERSION == 1, "VERSION %s" % env.VERSION)
    check(py(g.ADDED) == names, "declared at load: %s" % py(g.ADDED))

    # before the first census: who holds what from the save, nothing else yet
    check(env.holder("s1") == "dolg" and py(env.held("dolg")) == ["s1", "s3"], "the save's holders: %s, %s"
          % (env.holder("s1"), py(env.held("dolg"))))
    check(env.strength("dolg") is None and env.census() is None and env.contested("s2") is False,
          "a census before the first one")

    # the census: sent after it's kept, so a handler that changes it changes nothing
    lua.execute("HANDLERS.fotz_on_census = { function(t) GOT = t; t.smarts.s1 = 'bandit'; t.factions.dolg.fighters = 0 end }")
    env.on_census(g.CENSUS)
    got = py(g.GOT)
    check(got == {"date": "2012-05-05 08:00", "cause": "day", "smarts": {"s1": "bandit", "s2": "killer", "s4": "freedom"},
                  "contested": ["s2"], "factions": {"dolg": {"squads": 2, "fighters": 0, "levels": {"l02_garbage": 9}}}},
          "the census sent: %s" % got)
    check(env.holder("s1") == "killer" and env.holder("s3") is None and py(env.held("killer")) == ["s1", "s2"],
          "holders after the census: %s, %s, %s" % (env.holder("s1"), env.holder("s3"), py(env.held("killer"))))
    check(env.contested("s2") is True and env.contested("s1") is False, "contested")
    st = env.strength("dolg")
    check(py(st) == {"squads": 2, "fighters": 9, "levels": {"l02_garbage": 9}}, "strength %s" % py(st))
    st.fighters = 1
    check(env.strength("dolg").fighters == 9 and env.strength("killer") is None, "strength isn't a copy")
    c = env.census()
    check(py(c) == {"date": "2012-05-05 08:00", "cause": "day", "smarts": {"s1": "killer", "s2": "killer", "s4": "freedom"},
                    "contested": ["s2"], "factions": {"dolg": {"squads": 2, "fighters": 9, "levels": {"l02_garbage": 9}}}},
          "the last census: %s" % py(c))

    # a send: every handler; a handler's error logged and kept inside; never a name not declared
    check(env.send("fotz_on_bogus", lua.eval("{}")) is False and "fotz_on_bogus" not in py(g.SENDS),
          "a name never declared was sent")
    lua.execute("HANDLERS.fotz_on_politics = { function() error('a bad mod') end }")
    check(env.send("fotz_on_politics", lua.eval("{}")) is False, "a failing handler's send said it worked")
    check(any("! a fotz_on_politics handler failed" in l and "a bad mod" in l for l in g.LOG.values()),
          "a failing handler wasn't logged: %s" % py(g.LOG))

    # politics running, or standing down, and why
    check(env.active() == (True, None), "active %s" % (env.active(),))
    g.DOWN = "Warfare mode is on"
    check(env.active() == (False, "Warfare mode is on"), "standing down: %s" % (env.active(),))

    # where a pair stands: the start without the drift while politics runs, the live value while
    # it stands down; nil for a pair Factions never moves; its event a copy
    p = py(env.pair("killer", "dolg"))
    check(p["relation"] == -1400 and p["start"] == -1400 and p["drift"] == -400, "a pair while standing down: %s" % p)
    g.DOWN = None
    p = env.pair("killer", "dolg")
    check(py(p) == {"relation": -1400, "start": -1000, "drift": -400, "pending": -300, "trend": -100,
                    "event": {"kind": "war", "a": "dolg", "b": "killer", "since": "2012-05-04", "cause": "ground",
                              "at": "s1", "voice": "dolg"}}, "a pair: %s" % py(p))
    p.event.kind = "x"
    check(env.pair("dolg", "killer").event.kind == "war" and env.pair("dolg", "freedom") is None, "a pair's event isn't a copy")

    # events by date, history newest first, every one a copy
    ev = py(env.events())
    check([(e["kind"], e["since"]) for e in ev] == [("truce", "2012-05-02"), ("war", "2012-05-04")]
          and ev[0].get("until") == "2012-05-07", "events %s" % ev)
    h = env.history(2)
    check([e["kind"] for e in py(h)] == ["truce", "war_over"] and len(py(env.history())) == 3, "history %s" % py(h))
    h[1].kind = "x"
    check(env.history(1)[1].kind == "truce", "the history isn't a copy")

    # sides (a copy), names, places, fronts with their leaders
    s = env.sides()
    s[1] = "x"
    check(py(env.sides()) == ["dolg", "killer", "fotz_own"], "sides %s" % py(env.sides()))
    check(env.name("dolg") == "N:dolg" and env.place_name("s1") == "P:s1", "names")
    f = py(env.fronts())
    check(f == [{"level": "l02_garbage", "a": "dolg", "b": "killer", "fa": 30, "fb": 10, "leader": "dolg"},
                {"level": "l03_agroprom", "a": "dolg", "b": "killer", "fa": 15, "fb": 15}], "fronts %s" % f)

    # your faction, with its living members; none before founding
    check(py(env.own()) == {"id": "u1", "name": "Wolves", "mother": "dolg", "founded": "2012-05-01", "members": 2},
          "your faction %s" % py(env.own()))
    lua.execute("fotz_faction.F.base = nil")
    check(env.own() is None, "a faction without its founding relations")

    # the nudges reach politics; without it they're refused, or neutral
    check(env.grievance("dolg", "killer", -500, lua.eval('{ at = "s1" }')) is True
          and py(g.GRIEF) == ["dolg", "killer", -500, "s1"], "a grievance %s" % py(g.GRIEF))
    check(env.set_place("s2", 3) is True and py(g.PLACED) == ["s2", 3] and env.clear_place("s1") is True
          and env.clear_place("s2") is False and env.place_weight("s1") == 2, "places")
    lua.execute("fotz_politics = nil")
    check(env.grievance("dolg", "killer", -500) is False and env.set_place("s2", 3) is False
          and env.place_weight("s1") == 1 and env.active() == (False, "Factions isn't loaded")
          and env.pair("dolg", "killer") is None, "without politics")
    return "VERSION 1, 4 callbacks, 15 reads, 4 nudges"


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
