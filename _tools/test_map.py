"""Run fotz_map.script and modxml_fotz_map.script under LuaJIT 2.0 against a stand-in for the
engine's map spots, with the page's own fotz_tab.script for the fights, and check the fighting on
the PDA map.

Checked: a marker for each level the page names a fight on (fotz_tab.fights), none where neither
side of the level's main fight holds a smart; the anchor (a smart either side holds with hostile
squads at it, else the side behind's, else the side ahead's); the hint (the page's sentence for the
level, then the factions there hostile to you, the most fighters first, four at most, and none
without fighters there) and the label ("A vs B", the main fight's sides), in the English table's
words; red where the fight is your side's; no marker ever saved (map_add_object_spot, never _ser);
the label on the marker's own widget, in its color, and none without a widget or the engine
function; a marker left alone while it's unchanged, taken off and put back when it changes or
another mod removed it, taken off when its level drops out; MCM's switch (off clears the map, on
rebuilds it from the last census); the map cleared as a game unloads; a label that fails is logged
and its marker stays; the DXML edit adds both spot types once to each map_spots file and to no
other file.

    python test_map.py            the real scripts
    python test_map.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(HERE, "..", "gamedata", "scripts")
ENG = os.path.join(HERE, "..", "gamedata", "configs", "text", "eng", "st_fotz.xml")
MODULES = ("fotz_map", "modxml_fotz_map", "fotz_tab")

#: name -> (text in the script, its broken replacement[, module]); each must make this test fail
MUTANTS = {
    "contested_ignored": ("            if contested[name] and (not best or name < best) then", "            if false then"),
    "behind_flipped": ("    if f.fa > f.fb then\n        behind, ahead = b, a", "    if f.fa < f.fb then\n        behind, ahead = b, a"),
    "no_fallback": ("    return behind[1] or ahead[1]", "    return behind[1]"),
    "anchor_counts_swapped": ("anchor({ a = a, b = b, fa = fx.n[a], fb = fx.n[b] }", "anchor({ a = a, b = b, fa = fx.n[b], fb = fx.n[a] }"),
    "yours_spot": ("spot = fx.yours and SPOT_YOURS or SPOT,", "spot = SPOT,"),
    "label_sides": ('{ a = P.faction_name(a), b = P.faction_name(b) }', '{ a = P.faction_name(b), b = P.faction_name(a) }'),
    "hostile_ignored": ("            if #foes > 0 then", "            if false then"),
    "hostile_empty_shown": ("            if #foes > 0 then", "            if true then"),
    "hostile_line": ("relation_registry.community_relation(side, f) <= -1000", "relation_registry.community_relation(side, f) < -1000"),
    "hostile_absent": ("if at and (at.fighters or 0) > 0 and", "if at and"),
    "hostile_order": ("            return x.n > y.n", "            return x.n < y.n"),
    "hostile_uncapped": ("fotz_tab.names_list(foes, HOSTILE_NAMES)", "fotz_tab.names_list(foes)"),
    "saved_spots": ("            level.map_add_object_spot(id, m.spot, m.hint)", "            level.map_add_object_spot_ser(id, m.spot, m.hint)"),
    "readd_always": ("        if not (m and m.spot == p.spot and m.hint == p.hint and m.label == p.label and has(id, p.spot)) then",
                     "        if true then"),
    "external_removal_missed": (" and m.label == p.label and has(id, p.spot)) then", " and m.label == p.label) then"),
    "hint_change_missed": (" and m.hint == p.hint and m.label", " and m.label"),
    "mcm_ignored": ('    return not (ui_mcm and ui_mcm.get("fotz/map") == false)', "    return true"),
    "net_destroy_kept": ('    RegisterScriptCallback("actor_on_net_destroy", clear)\n', ""),
    "label_unguarded": ("            local ok, made = pcall(label, m)", "            local ok, made = true, label(m)"),
    "no_static_check": ("    if not st then\n        return false\n    end\n", ""),
    "label_color": ("    w:SetTextColor(GetARGB(255, col[1], col[2], col[3]))\n", ""),
    "last_forgotten": ("    last = c or last", "    last = c"),
    "dxml_any_file": ('    if not string.match(name, "^ui[\\\\/]map_spots[_%d]*%.xml$") then', "    if false then",
                      "modxml_fotz_map"),
    "hint_newline": ('hint = table.concat(lines, "\\\\n")', 'hint = table.concat(lines, "\\n")'),
    "dxml_twice": ("        if #xml:query(spot) == 0 then", "        if true then", "modxml_fotz_map"),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end
MCM = {}
ui_mcm = { get = function(id) return MCM[id] end }
CALLBACKS = {}
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end
function GetARGB(a, r, g, b) return a .. "," .. r .. "," .. g .. "," .. b end

STR = { l02_garbage = "Garbage", l03_agroprom = "Agroprom", l04_darkvalley = "Dark Valley", l05_bar = "Bar",
        l06_rostok = "Rostok", l08_yantar = "Yantar" }
game = { translate_string = function(s) return STR[s] or s end }
NAMES = { dolg = "Duty", killer = "Mercenaries", bandit = "Bandits", army = "Military", stalker = "Loners",
          freedom = "Freedom", csky = "Clear Sky", ecolog = "Ecologists", monolith = "Monolith", renegade = "Renegades",
          greh = "Sin", isg = "UNISG" }
fotz_politics = { faction_name = function(f) return NAMES[f] or f end }
SIDE = "dolg"
-- how Duty stands with the others: hostile at -1000 and below
REL = { ["dolg>killer"] = -1500, ["dolg>bandit"] = -2000, ["dolg>monolith"] = -2000, ["dolg>freedom"] = -1000,
        ["dolg>renegade"] = -2000, ["dolg>greh"] = -2000 }
relation_registry = { community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end }
fotz_territory = { FRONT_MIN = 10, FRONTS = {} }
LEVEL = {}
fotz_census = { FACTIONS = { "stalker", "bandit", "csky", "dolg", "freedom", "killer", "army", "ecolog", "monolith",
                             "renegade", "greh", "isg" },
                level_of = function(se) return LEVEL[se.id] end }
SIMBOARD = { smarts_by_names = {} }
function smart(name, id, lv) SIMBOARD.smarts_by_names[name] = { id = id }; LEVEL[id] = lv end

-- the engine's map spots
SPOTS = {}
CALLS = { add = 0, remove = 0, ser = 0 }
STATIC = true
level = {
    map_add_object_spot = function(id, t, hint) CALLS.add = CALLS.add + 1; SPOTS[id .. "|" .. t] = hint end,
    map_add_object_spot_ser = function(id, t, hint) CALLS.ser = CALLS.ser + 1 end,
    map_remove_object_spot = function(id, t) CALLS.remove = CALLS.remove + 1; SPOTS[id .. "|" .. t] = nil end,
    map_has_object_spot = function(id, t) return SPOTS[id .. "|" .. t] and 1 or 0 end,
    map_get_object_spot_static = function(id, t)
        if STATIC and SPOTS[id .. "|" .. t] then return { spot = id .. "|" .. t } end
    end,
}
WINDOWS = {}
BROKEN = false
function CScriptXmlInit()
    local x = {}
    function x:ParseFile(f) self.file = f end
    function x:InitTextWnd(name, parent)
        if BROKEN then error("no such element") end
        local w = { name = name, parent = parent.spot }
        function w:SetText(s) self.text = s end
        function w:SetTextColor(c) self.color = c end
        WINDOWS[#WINDOWS + 1] = w
        return w
    end
    return x
end

-- the census's ground: Garbage (gar_c contested), Agroprom, Dark Valley, Rostok, Bar (bar_a contested)
smart("gar_a", 101, "l02_garbage"); smart("gar_b", 102, "l02_garbage"); smart("gar_c", 103, "l02_garbage")
smart("agr_a", 201, "l03_agroprom"); smart("agr_b", 202, "l03_agroprom")
smart("val_a", 301, "l04_darkvalley"); smart("ros_a", 401, "l06_rostok"); smart("bar_a", 501, "l05_bar")
CENSUS = { smarts = { gar_a = "dolg", gar_b = "bandit", gar_c = "dolg", agr_a = "dolg", agr_b = "killer",
                      val_a = "bandit", ros_a = "freedom", bar_a = "dolg" },
           contested = { "bar_a", "gar_c" } }
-- each faction's fighters on each level; a Mercenary entry on Rostok with none
function fighters()
    FIGHTERS = {
        l02_garbage = { dolg = 30, killer = 12, bandit = 14, stalker = 12, csky = 11, renegade = 3, monolith = 2, greh = 2 },
        l03_agroprom = { dolg = 10, killer = 30 },
        l04_darkvalley = { bandit = 5, army = 30, stalker = 4 },
        l06_rostok = { dolg = 12, freedom = 12, killer = 0 },
        l08_yantar = { ecolog = 6, monolith = 6 },
        l05_bar = { dolg = 3, killer = 4 } }
    counted()
end
function counted()
    CENSUS.factions = {}
    for lv, list in pairs(FIGHTERS) do
        for f, n in pairs(list) do
            CENSUS.factions[f] = CENSUS.factions[f] or { levels = {} }
            CENSUS.factions[f].levels[lv] = { fighters = n }
        end
    end
end
-- territory's fronts from those counts: every two hostile factions on a level
function fronts()
    fighters()
    fotz_territory.FRONTS = {
        { a = "dolg", b = "killer", level = "l02_garbage", fa = 30, fb = 12 },
        { a = "dolg", b = "bandit", level = "l02_garbage", fa = 30, fb = 14 },
        { a = "dolg", b = "monolith", level = "l02_garbage", fa = 30, fb = 2 },
        { a = "dolg", b = "renegade", level = "l02_garbage", fa = 30, fb = 3 },
        { a = "dolg", b = "greh", level = "l02_garbage", fa = 30, fb = 2 },
        { a = "stalker", b = "bandit", level = "l02_garbage", fa = 12, fb = 14 },
        { a = "csky", b = "killer", level = "l02_garbage", fa = 11, fb = 12 },
        { a = "dolg", b = "killer", level = "l03_agroprom", fa = 10, fb = 30 },
        { a = "bandit", b = "army", level = "l04_darkvalley", fa = 5, fb = 30 },
        { a = "stalker", b = "army", level = "l04_darkvalley", fa = 4, fb = 30 },
        { a = "dolg", b = "freedom", level = "l06_rostok", fa = 12, fb = 12 },
        { a = "ecolog", b = "monolith", level = "l08_yantar", fa = 6, fb = 6 },
        { a = "dolg", b = "killer", level = "l05_bar", fa = 3, fb = 4 } }
end
function front(lv, a, b)
    for _, f in ipairs(fotz_territory.FRONTS) do
        if f.level == lv and f.a == a and f.b == b then return f end
    end
end
fronts()
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


class World:
    def __init__(self, srcs):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(WORLD)
        root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
        for s in root.iter("string"):
            if s.get("id").startswith("st_fotz_"):
                self.g.STR[s.get("id")] = s.findtext("text")
        load = self.lua.eval("function(src, name) local env = setmetatable({}, { __index = _G }) "
                             "local f = assert(loadstring(src, name)) setfenv(f, env) f() return env end")
        # the page's script for the fights and their words, your side set here
        self.g.fotz_tab = load(srcs["fotz_tab"], "fotz_tab")
        self.lua.execute("fotz_tab.side = function() return SIDE end")
        self.dxml = load(srcs["modxml_fotz_map"], "modxml_fotz_map")
        self.env = load(srcs["fotz_map"], "fotz_map")
        self.env.on_game_start()

    def run(self, code):
        return self.lua.execute(code)

    def eval(self, code):
        return self.lua.eval(code)

    def spots(self):
        return dict(self.g.SPOTS.items())

    def calls(self):
        c = self.g.CALLS
        return c.add, c.remove, c.ser

    def windows(self):
        W = self.g.WINDOWS
        return [(W[i].name, W[i].parent, W[i].text, W[i].color) for i in range(1, len(W) + 1)]

    def log(self):
        return list(self.g.LOG.values())


# the UI breaks a hint's lines at the two characters \n, as the game's own map hints write them
GARBAGE_HINT = ("Garbage: your Duty winning, Bandits, Mercenaries and Renegades losing\\n"
                "Hostile to you here: Bandits, Mercenaries, Renegades and 2 more")
WANT = {
    "103|fotz_front_yours": GARBAGE_HINT,
    "201|fotz_front_yours": "Agroprom: Mercenaries winning, your Duty losing\\nHostile to you here: Mercenaries",
    "401|fotz_front_yours": "Rostok: your Duty and Freedom evenly matched\\nHostile to you here: Freedom",
    "301|fotz_front": "Dark Valley: Military in control, Bandits and Loners nearly gone\\nHostile to you here: Bandits",
}
RED, AMBER = "255,230,80,70", "255,238,196,112"


def markers(srcs):
    w = World(srcs)
    ms = w.env.markers(w.g.fotz_territory.FRONTS, w.g.CENSUS, "dolg")
    rows = [(ms[i].level, ms[i].smart, ms[i].spot, ms[i].label) for i in range(1, len(ms) + 1)]
    # Yantar's fight has no smart either side holds; Bar's is too small to name
    check(rows == [("l02_garbage", "gar_c", "fotz_front_yours", "Duty vs Bandits"),
                   ("l03_agroprom", "agr_a", "fotz_front_yours", "Mercenaries vs Duty"),
                   ("l06_rostok", "ros_a", "fotz_front_yours", "Duty vs Freedom"),
                   ("l04_darkvalley", "val_a", "fotz_front", "Military vs Bandits")],
          "markers %s" % rows)
    hints = {"%d|%s" % (ms[i].id, ms[i].spot): ms[i].hint for i in range(1, len(ms) + 1)}
    check(hints == WANT, "hints %s" % hints)
    # seen from the Military's side: Dark Valley is theirs and red, and no one is hostile to them
    w.run('SIDE = "army"')
    ms = w.env.markers(w.g.fotz_territory.FRONTS, w.g.CENSUS, "army")
    got = [(ms[i].spot, ms[i].hint) for i in range(1, len(ms) + 1)]
    check(got == [("fotz_front_yours", "Dark Valley: your Military in control, Bandits and Loners nearly gone"),
                  ("fotz_front", "Garbage: Duty winning, Bandits, Mercenaries and Renegades losing"),
                  ("fotz_front", "Agroprom: Mercenaries winning, Duty losing"),
                  ("fotz_front", "Rostok: Duty and Freedom evenly matched")], "the Military's %s" % got)


def update(srcs):
    w = World(srcs)
    check(w.env.update(w.g.CENSUS) == 4 and w.spots() == WANT, "the map %s" % w.spots())
    check(w.calls() == (4, 0, 0), "add, remove, saved: %s" % (w.calls(),))
    wins = w.windows()
    labels = sorted((p, t, c) for n, p, t, c in wins if n == "front_label")
    check(len(wins) == 8 and labels == [("103|fotz_front_yours", "Duty vs Bandits", RED),
                                        ("201|fotz_front_yours", "Mercenaries vs Duty", RED),
                                        ("301|fotz_front", "Military vs Bandits", AMBER),
                                        ("401|fotz_front_yours", "Duty vs Freedom", RED)],
          "labels %s" % labels)
    check(any("4 markers on the map, 4 labelled" in l for l in w.log()), "log %s" % w.log()[-1:])

    # the same census again: nothing moves
    w.env.update(w.g.CENSUS)
    check(w.calls() == (4, 0, 0) and len(w.windows()) == 8, "unchanged, but %s" % (w.calls(),))
    # Duty gains on Agroprom: only its marker is taken off and put back
    w.run('front("l03_agroprom", "dolg", "killer").fa = 20; FIGHTERS.l03_agroprom.dolg = 20; counted()')
    w.env.update(w.g.CENSUS)
    check(w.calls() == (5, 1, 0) and w.spots().get("201|fotz_front_yours")
          == "Agroprom: Mercenaries ahead, your Duty holding on\\nHostile to you here: Mercenaries",
          "Agroprom changed: %s %s" % (w.calls(), w.spots().get("201|fotz_front_yours")))
    # more of the Sin on Garbage: its hint changes, its label doesn't, and the marker is renewed
    w.run('front("l02_garbage", "dolg", "greh").fb = 5; FIGHTERS.l02_garbage.greh = 5; counted()')
    w.env.update(w.g.CENSUS)
    garbage = ("Garbage: your Duty winning, Bandits, Mercenaries and 2 more losing\\n"
               "Hostile to you here: Bandits, Mercenaries, Sin and 2 more")
    check(w.calls() == (6, 2, 0) and w.spots().get("103|fotz_front_yours") == garbage,
          "Garbage's hint changed: %s %s" % (w.calls(), w.spots().get("103|fotz_front_yours")))
    # another mod took Garbage's marker off: it goes back
    w.run('SPOTS["103|fotz_front_yours"] = nil')
    w.env.update(w.g.CENSUS)
    check(w.calls() == (7, 2, 0) and w.spots().get("103|fotz_front_yours") == garbage,
          "Garbage put back: %s" % (w.calls(),))
    # Dark Valley's fighting ends: its marker goes
    w.run("for i = #fotz_territory.FRONTS, 1, -1 do "
          "if fotz_territory.FRONTS[i].level == 'l04_darkvalley' then table.remove(fotz_territory.FRONTS, i) end end")
    w.env.update(w.g.CENSUS)
    check("301|fotz_front" not in w.spots() and len(w.spots()) == 3 and w.calls() == (7, 3, 0),
          "Dark Valley %s %s" % (w.spots(), w.calls()))

    # MCM: off clears the map, on rebuilds it from the last census
    w.run('MCM["fotz/map"] = false')
    w.g.CALLBACKS["on_option_change"]()
    check(w.spots() == {}, "off: %s" % w.spots())
    w.run('MCM["fotz/map"] = nil; fronts()')
    w.g.CALLBACKS["on_option_change"]()
    check(w.spots() == WANT, "on again: %s" % w.spots())
    # a game unloading takes every marker off
    w.g.CALLBACKS["actor_on_net_destroy"]()
    check(w.spots() == {} and w.calls()[2] == 0, "unloaded: %s, saved %d" % (w.spots(), w.calls()[2]))


def no_labels(srcs):
    # no widget for the marker, then no engine function: markers and hints, no labels, no errors
    w = World(srcs)
    w.run("STATIC = false")
    check(w.env.update(w.g.CENSUS) == 4 and w.windows() == [] and len(w.spots()) == 4, "no widget: %s" % w.windows())
    check(any("4 markers on the map, 0 labelled" in l for l in w.log())
          and not any("! the label" in l for l in w.log()), "log %s" % w.log())
    w = World(srcs)
    w.run("level.map_get_object_spot_static = nil")
    check(w.env.update(w.g.CENSUS) == 4 and w.windows() == [], "no function: %s" % w.windows())
    # a label that fails: logged, its marker stays
    w = World(srcs)
    w.run("BROKEN = true")
    check(w.env.update(w.g.CENSUS) == 4 and len(w.spots()) == 4, "broken labels: %s" % w.spots())
    check(sum("! the label at" in l for l in w.log()) == 4, "log %s" % w.log())


#: a DXML document as far as the edit reads it
FAKE_XML = """
function fake_xml(have)
    local x = { inserted = {}, have = have or {} }
    function x:query(q) return self.have[q] and { q } or {} end
    function x:insertFromXMLString(s)
        self.inserted[#self.inserted + 1] = s
        self.have[string.match(s, "^<([%w_]+)>")] = true
    end
    return x
end
"""


def dxml(srcs):
    w = World(srcs)
    w.run(FAKE_XML)
    edit = w.dxml.edit
    x = w.eval("fake_xml()")
    check(edit("ui\\map_spots.xml", x) is True and len(x.inserted) == 2, "map_spots.xml: %d inserts" % len(x.inserted))
    both = x.inserted[1] + x.inserted[2]
    check('<fotz_front><level_map spot="fotz_front_spot"/>' in both and '<fotz_front_yours>' in both
          and 'r="230" g="80" b="70">ui_pda2_attack_base2' in both and 'r="238" g="196" b="112"' in both
          and "mini_map" not in both, "the spot types: %s" % both)
    check(edit("ui\\map_spots.xml", x) is False and len(x.inserted) == 2, "added twice")
    for name, want in (("ui\\map_spots_16.xml", True), ("ui/map_spots_21.xml", True), ("ui\\map_spots_relations.xml", False),
                       ("ui\\pda.xml", False), ("ui\\map_spots_mp.xml", False)):
        y = w.eval("fake_xml()")
        check(edit(name, y) is want and len(y.inserted) == (2 if want else 0), "%s: %s" % (name, len(y.inserted)))


def strings(srcs):
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    want = set(re.findall(r'"(st_fotz_\w+)"', srcs["fotz_map"])) | {"ui_mcm_fotz_map", "ui_mcm_fotz_map_desc"}
    check(want <= have, "missing: %s" % sorted(want - have))


def run(srcs):
    strings(srcs)
    markers(srcs)
    update(srcs)
    no_labels(srcs)
    dxml(srcs)
    return "5 scenarios"


def main():
    srcs = {m: io.open(os.path.join(SCRIPTS_DIR, m + ".script"), encoding="utf-8").read() for m in MODULES}
    if len(sys.argv) > 1:
        name = sys.argv[1]
        m = MUTANTS[name]
        old, new, module = m[0], m[1], (m[2] if len(m) > 2 else "fotz_map")
        if srcs[module].count(old) != 1:
            print("MUTANT DOES NOT APPLY: %s (found %d times)" % (name, srcs[module].count(old)))
            return 2
        srcs[module] = srcs[module].replace(old, new)
    try:
        print("ok: " + run(srcs))
        return 0
    except Fail as e:
        print("FAIL: %s" % e)
        return 1
    except Exception as e:
        print("FAIL (error): %s: %s" % (type(e).__name__, " | ".join(str(e).splitlines())))
        return 1


if __name__ == "__main__":
    sys.exit(main())
