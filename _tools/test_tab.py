"""Run fotz_tab.script's page() under LuaJIT 2.0 on top of the real politics engine (test_politics'
world), and check what the Factions tab shows.

Checked: your side without a faction (your own) and with one (yours, all twelve factions); each
row's standing in words and colors, an event in force before the lines at -1000 and 1000; how far
politics moved a pair, "never changes" for fixed pairs and factions; the census's ground and
fighters; the war log, newest first, six at most, with its dates; the fronts (territory's, from the
last census), your side's first, then the biggest, five at most, the bigger side named first;
members (the dead apart, near or away, five then "and N more"); why politics stands down; Restore
relations; every string exists.
The page's layout (ui_fotz_tab.script) is checked in game.

    python test_tab.py            the real script
    python test_tab.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import sys

import test_politics as TP

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(HERE, "..", "gamedata", "scripts")
#: the scripts the tab is made of, by module name; a mutant names its module when it isn't fotz_tab
MODULES = ("fotz_tab", "z_fotz_mac", "modxml_fotz_tab", "fotz_mcm", "fotz_territory")
SCRIPT = os.path.join(SCRIPTS_DIR, "fotz_tab.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "band_line": ("    if rel <= -1000 then", "    if rel < -1000 then"),
    "event_first": ('    if kind == "war" or kind == "truce" or kind == "alliance" then', "    if false then"),
    "log_order": ("for i = #h, math.max(1, #h - LOG_LINES + 1), -1 do", "for i = 1, math.min(#h, LOG_LINES) do"),
    "log_cap": ("for i = #h, math.max(1, #h - LOG_LINES + 1), -1 do", "for i = #h, 1, -1 do"),
    "dead_counted": ("        for _, m in pairs(F.members) do\n            if not m.dead then",
                     "        for _, m in pairs(F.members) do\n            if true then"),
    "member_state": ('local state = it.m.dead and "dead" or (level.object_by_id(it.id) and "near" or "away")',
                     'local state = "near"'),
    "member_cap": ("        if i > MEMBER_LINES then", "        if false then"),
    "side": ("    return F and fotz_politics.OWN or get_actor_true_community()", "    return get_actor_true_community()"),
    "held": ("        if holder == f then", "        if true then"),
    "status": ('p.status = why and text("st_fotz_tab_down_" .. why) or text("st_fotz_tab_in_charge")',
               'p.status = text("st_fotz_tab_in_charge")'),
    "date": ('return m and (dd .. "." .. m) or tostring(d or "")', 'return tostring(d or "")'),
    "drift_shown": ('change = d ~= 0 and text("st_fotz_tab_change", { n = signed(d) }) or ""', 'change = ""'),
    "leader_alive": ("    if se and (se.alive == nil or se:alive()) then", "    if se then"),
    "leader_trader": ("    if se and (se.alive == nil or se:alive()) then", "    if se and se:alive() then"),
    "leader_gone": ("local name = se and se:character_name() or (fp.leader_name and game.translate_string(fp.leader_name))",
                    "local name = se and se:character_name()"),
    "trend_sign": ('return t > 0 and "up" or "down"', 'return t > 0 and "down" or "up"'),
    "event_split": ('event = event_line(ev) or ""', 'event = ""'),
    "no_mac_no_tab": ('    return not z_fotz_mac.available() or (ui_mcm ~= nil and ui_mcm.get("fotz/pda_tab") == true)',
                      '    return ui_mcm ~= nil and ui_mcm.get("fotz/pda_tab") == true'),
    "mac_tab_always": ('    return not z_fotz_mac.available() or (ui_mcm ~= nil and ui_mcm.get("fotz/pda_tab") == true)',
                       "    return true"),
    "tab_keeps_tile": ("            TAB = id\n            z_fotz_mac.remove_tile()\n", "            TAB = id\n"),
    "refused_no_tile": ('            log("! no Factions tab: %s", tostring(id))\n            z_fotz_mac.add_tile()\n',
                        '            log("! no Factions tab: %s", tostring(id))\n'),
    "gone_stays": ('                m:SetActiveSubdialog("eptTasks")', "                m:SetActiveSubdialog(gone)"),
    "tile_section": ("        tab = modxml_fotz_tab.SECTION,     -- the parked section the page opens in",
                     '        tab = "eptLauncher",', "z_fotz_mac"),
    "tile_twice": ("    if tiled or not available() then", "    if not available() then", "z_fotz_mac"),
    "dxml_twice": ('    if #xml:query("tab > button[id=" .. SECTION .. "]") > 0 then\n        return false\n    end\n', "",
                   "modxml_fotz_tab"),
    "dxml_no_caption": ('    if not (tab and xml:query("caption_static")[1]) then', "    if not tab then", "modxml_fotz_tab"),
    "dxml_any_file": ('    if not string.match(name, "^ui[\\\\/]pda[%w_]*%.xml$") then', "    if false then", "modxml_fotz_tab"),
    "mcm_option_always": ("    if z_fotz_mac and z_fotz_mac.available() then", "    if true then", "fotz_mcm"),
    "fronts_not_mine_first": ("        local list = (f.a == side or f.b == side) and mine or rest", "        local list = rest"),
    "fronts_uncapped": ("            if #out >= FRONT_LINES then", "            if false then"),
    "front_as_listed": ("            if nb > na then", "            if false then"),
    "fronts_no_none": ('        out[1] = text("st_fotz_tab_fronts_none")', "        out[1] = nil"),
}

FACTIONS = ("stalker", "bandit", "csky", "dolg", "freedom", "killer", "army", "ecolog", "monolith",
            "renegade", "greh", "isg")


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


class Tab:
    """The politics world, with the tab's script loaded beside it."""

    def __init__(self, srcs, pre=None, m_data=None, mac=False):
        self.p = TP.World(io.open(TP.SCRIPT, encoding="utf-8").read(), anchors=TP.DK_ANCHORS, pre=pre, m_data=m_data)
        lua, g = self.p.lua, self.p.g
        g.fotz_politics = self.p.env
        lua.execute("fotz_census.FACTIONS = { %s }" % ", ".join('"%s"' % f for f in FACTIONS))
        lua.execute("NEAR = {}; level = { object_by_id = function(id) return NEAR[id] end }")
        # the game's faction leaders: Voronin alive, Dushman dead, Kuznetsov gone from the alife
        lua.execute("""
faction_expansions = { faction = {
    stalker = { leader = "esc_m_trader", leader_name = "st_sid" },
    dolg = { leader = "bar_dolg_leader", leader_name = "st_voronin" },
    killer = { leader = "cit_merc_leader", leader_name = "st_dushman" },
    army = { leader = "agr_colonel", leader_name = "st_kuznetsov" } } }
STR["st_kuznetsov"] = "Kuznetsov"
LEADERS = { bar_dolg_leader = { name = "Voronin", alive = true }, cit_merc_leader = { name = "Dushman", alive = false } }
function get_story_se_object(id)
    -- Sidorovich is a trader: his server object has no alive()
    if id == "esc_m_trader" then
        return { character_name = function() return "Sidorovich" end }
    end
    local l = LEADERS[id]
    return l and { character_name = function() return l.name end, alive = function() return l.alive end }
end
""")
        lua.execute("function CreateTimeEvent() end")
        # Modded Exes' tab registry, the PDA window, and Mod App Creator when `mac`
        lua.execute("""
REG, UNREG, REFUSE = {}, {}, false
pda_dynamic_tabs = {
    register = function(caption, fn) assert(not REFUSE, "refused") REG[#REG + 1] = caption; PAGE_FN = fn; return "ept_dynamic_1" end,
    unregister = function(id) UNREG[#UNREG + 1] = id; return true end }
MENU = nil
ActorMenu = { get_pda_menu = function() return MENU end }
function pda_menu(section)
    MENU = { section = section, went = {} }
    function MENU:GetActiveSection() return self.section end
    function MENU:SetActiveSubdialog(s) self.went[#self.went + 1] = s; self.section = s end
    return MENU
end
""")
        if mac:
            lua.execute("""
APPS, REMOVED, ADDS = {}, {}, 0
mac_mcm = { add_app = function(id, data) ADDS = ADDS + 1; APPS[id] = data end,
            remove_app = function(id) REMOVED[#REMOVED + 1] = id; APPS[id] = nil end }
""")
        load = lua.eval("function(src, name) local env = setmetatable({}, { __index = _G }) "
                        "local f = assert(loadstring(src, name)) setfenv(f, env) f() return env end")
        g = self.p.g
        for name in ("modxml_fotz_tab", "z_fotz_mac", "fotz_mcm", "fotz_territory"):
            g[name] = load(srcs[name], name)
        self.env = load(srcs["fotz_tab"], "fotz_tab")
        g.fotz_tab = self.env
        self.env.on_game_start()

    def run(self, code):
        return self.p.lua.execute(code)

    def page(self):
        return self.env.page()

    def census(self, smarts, fighters):
        c = self.p.lua.eval("{ date = DATE .. ' 08:00', smarts = {}, fronts = {}, factions = {} }")
        for k, v in smarts.items():
            c.smarts[k] = v
        for f, n in fighters.items():
            c.factions[f] = self.p.lua.eval("{ fighters = %d }" % n)
        for i in range(1, len(self.p.g.LISTENERS) + 1):
            self.p.g.LISTENERS[i](c)


def rows(p):
    return {p.rows[i].faction: p.rows[i] for i in range(1, len(p.rows) + 1)}


def lines(t):
    return [t[i] for i in range(1, len(t) + 1)]


def your_own(srcs):
    t = Tab(srcs)
    p = t.page()
    r = rows(p)
    check(p.leading is False and p.side == "dolg" and p.title == "Duty", "side %s, title %s" % (p.side, p.title))
    check(p.subtitle.startswith("You lead no faction"), "subtitle %s" % p.subtitle)
    check(len(r) == 11 and "dolg" not in r, "rows: %s" % sorted(r))
    check(p.status == "Relations change as the factions fight.", "status %s" % p.status)
    check(p.icon == "ui_mm_faction_dolg" and r["killer"].icon == "ui_mm_faction_killer", "icons")
    check(r["freedom"].change == "never changes" and r["monolith"].change == "never changes",
          "fixed: %s, %s" % (r["freedom"].change, r["monolith"].change))
    check(r["killer"].standing == "Neutral (0)" and r["killer"].change == "", "killer at start: %s / %s" % (r["killer"].standing, r["killer"].change))
    check(lines(p.log) == ["Nothing yet: wars, truces and alliances show here."], "empty log %s" % lines(p.log))
    check(p.members is None, "members without a faction")

    # a war, the census, and the lines at -1000 and 1000
    t.run('REL["dolg>bandit"] = -1000; REL["dolg>csky"] = 1000; REL["dolg>army"] = 999')
    t.p.env.S.events["dolg/killer"] = t.p.lua.eval('{ kind = "war", since = "2012-05-03", a = "dolg", b = "killer" }')
    t.p.env.S.drift["dolg/killer"] = -1200
    t.p.env.apply()
    t.census({"a": "killer", "b": "killer", "c": "dolg"}, {"killer": 40})
    r = rows(t.page())
    check(r["killer"].standing == "At war (-1200)" and r["killer"].band == "war", "killer: %s" % r["killer"].standing)
    check(r["killer"].change == "-1200 since the start", "killer change: %s" % r["killer"].change)
    check(r["killer"].detail == "Dushman (dead) · holds 2 · 40 fighters", "killer detail: %r" % r["killer"].detail)
    check(r["killer"].event == "at war since 03.05" and r["bandit"].event == "", "events: %r, %r" % (r["killer"].event, r["bandit"].event))
    check(r["army"].detail.startswith("Kuznetsov (dead)"), "a leader gone from the alife: %r" % r["army"].detail)
    check(r["bandit"].standing == "Enemies (-1000)" and r["csky"].standing == "Friends (+1000)" and r["army"].band == "neutral",
          "lines: %s, %s, %s" % (r["bandit"].standing, r["csky"].standing, r["army"].standing))
    check(list(r["killer"].color.values()) == [230, 80, 70], "war color %s" % list(r["killer"].color.values()))
    check(r["stalker"].detail == "Sidorovich · holds 0 · 0 fighters", "a trader leading, a faction with nothing: %r"
          % r["stalker"].detail)

    # which way politics moved each pair on its last day
    t.p.env.S.trend["dolg/killer"] = -360
    t.p.env.S.trend["bandit/dolg"] = 120
    r = rows(t.page())
    check(r["killer"].trend == "down" and r["bandit"].trend == "up" and r["csky"].trend is None,
          "trends %s %s %s" % (r["killer"].trend, r["bandit"].trend, r["csky"].trend))

    # the war log: newest first, six at most
    for i in range(12):
        t.p.env.S.history[len(t.p.env.S.history) + 1] = t.p.lua.eval(
            '{ kind = "war", a = "dolg", b = "killer", day = "2012-05-%02d" }' % (i + 1))
    t.p.env.S.history[len(t.p.env.S.history) + 1] = t.p.lua.eval('{ kind = "truce", a = "dolg", b = "killer", day = "2012-05-20" }')
    log = lines(t.page().log)
    check(len(log) == 6 and log[0] == "20.05  Truce: Duty and Mercenaries" and log[1] == "12.05  War: Duty and Mercenaries",
          "log %s" % log)

    # the fronts, from territory's last census: Duty's first, then the biggest; five at most
    check(lines(t.page().fronts) == ["None: no two factions at war share a level."], "no fronts: %s" % lines(t.page().fronts))
    t.run("""
STR.l02_garbage, STR.l03_agroprom, STR.l04_darkvalley = "Garbage", "Agroprom", "Dark Valley"
fotz_territory.FRONTS = {
    { a = "bandit", b = "army", level = "l02_garbage", fa = 5, fb = 40 },
    { a = "csky", b = "freedom", level = "l03_agroprom", fa = 20, fb = 18 },
    { a = "dolg", b = "killer", level = "l03_agroprom", fa = 10, fb = 26 },
    { a = "stalker", b = "bandit", level = "l02_garbage", fa = 12, fb = 12 },
    { a = "ecolog", b = "monolith", level = "l04_darkvalley", fa = 3, fb = 20 },
    { a = "freedom", b = "dolg", level = "l04_darkvalley", fa = 9, fb = 6 },
    { a = "army", b = "killer", level = "l04_darkvalley", fa = 2, fb = 3 } }
""")
    fr = lines(t.page().fronts)
    check(fr == ["Agroprom: Mercenaries 26, Duty 10", "Dark Valley: Freedom 9, Duty 6", "Garbage: Military 40, Bandits 5",
                 "Agroprom: Clear Sky 20, Freedom 18", "Garbage: Loners 12, Bandits 12"], "fronts %s" % fr)

    # standing down says why
    t.run('MCM["fotz/politics"] = false')
    check(t.page().status == "Relations stand still: turned off in MCM.", "off: %s" % t.page().status)
    t.run('MCM["fotz/politics"] = nil; OPT["alife/general/dynamic_relations"] = true')
    check(t.page().status == "Relations are left to the base game's dynamic relations.", "dynamic: %s" % t.page().status)
    return t


def yours(srcs):
    t = Tab(srcs, pre=TP.led_lua() + """
fotz_faction.F.members = { [501] = { name = "Vaska", mother = "stalker", joined = "2012-05-01" },
                           [502] = { name = "Oleg", mother = "dolg", joined = "2012-05-01", dead = true },
                           [503] = { name = "Fedya", mother = "csky", joined = "2012-05-02" } }
NEAR = { [501] = {} }
""")
    t.run("NEAR = { [501] = {} }")
    p = t.page()
    r = rows(p)
    check(p.leading is True and p.side == "fotz_own" and p.title == "Wolves", "side %s, title %s" % (p.side, p.title))
    check(p.subtitle == "Your faction · founded 01.05 · came from: Duty · members: 2", "subtitle %r" % p.subtitle)
    check(p.icon == "ui_mm_faction_dolg" and len(r) == 12, "icon %s, %d rows" % (p.icon, len(r)))
    check(r["killer"].standing == "Neutral (-200)" and r["killer"].change == "", "killer: %s / %s" % (r["killer"].standing, r["killer"].change))
    check(r["monolith"].change == "never changes", "monolith: %s" % r["monolith"].change)
    check(r["dolg"].detail == "Voronin", "a living leader: %r" % r["dolg"].detail)
    check(lines(p.members) == ["Fedya (Clear Sky), away", "Oleg (Duty), dead", "Vaska (Loners), with you"],
          "members %s" % lines(p.members))

    # more than five
    t.run("for i = 1, 10 do fotz_faction.F.members[600 + i] = { name = 'Zed ' .. string.char(64 + i), mother = 'stalker' } end")
    m = lines(t.page().members)
    check(len(m) == 6 and m[-1] == "and 8 more", "six lines, the last 'and 8 more': %s" % m)
    return t


def restore(srcs):
    t = Tab(srcs)
    t.run('day("2012-05-01")')
    t.run('kill("dolg", "killer", "veteran", 60)')
    t.run('day("2012-05-02")')
    check(t.p.drift("dolg/killer") == -400, "a drift to restore: %s" % t.p.drift("dolg/killer"))
    t.p.env.restore()
    check(t.p.drift("dolg/killer") is None and t.p.pending("dolg/killer") is None, "restore left drift or pressure")
    check(all(t.p.rel(c) == TP.DK_ANCHORS[c] for c in TP.CELLS), "restore didn't write the starts back")
    check(lines(t.page().log)[0] == "02.05  Relations restored to their start", "log %s" % lines(t.page().log))


def strings(srcs):
    import re
    import xml.etree.ElementTree as ET
    root = ET.fromstring(open(TP.ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    ui = io.open(os.path.join(HERE, "..", "gamedata", "scripts", "ui_fotz_tab.script"), encoding="utf-8").read()
    # whole ids; the prefixes the script builds ids from are listed below in full
    want = {w for w in re.findall(r'"(st_fotz_tab\w*)"', srcs["fotz_tab"] + ui + srcs["z_fotz_mac"]) if not w.endswith("_")}
    for b in ("war", "enemies", "truce", "neutral", "friends", "alliance"):
        want.add("st_fotz_tab_band_" + b)
    for k in ("war", "war_over", "truce", "truce_over", "alliance", "alliance_over", "restored"):
        want.add("st_fotz_tab_log_" + k)
    for k in ("war_since", "truce_until", "alliance_since"):
        want.add("st_fotz_tab_" + k)
    for s in ("near", "away", "dead"):
        want.add("st_fotz_tab_member_" + s)
    for d in ("off", "dynamic", "warfare", "dfrc", "fluid"):
        want.add("st_fotz_tab_down_" + d)
    want |= {"ui_mcm_fotz_tab_key", "ui_mcm_fotz_tab_key_desc", "ui_mcm_fotz_pda_tab", "ui_mcm_fotz_pda_tab_desc"}
    missing = sorted(want - have)
    check(not missing, "missing from the English table: %s" % missing)
    return len(want)


def ways_in(srcs):
    # without Mod App Creator: the page's own tab, no tile
    t = Tab(srcs)
    t.env.sync()
    check(list(t.p.g.REG.values()) == ["st_fotz_tab"] and t.env.section() == "ept_dynamic_1",
          "without MAC: registered %s, section %s" % (list(t.p.g.REG.values()), t.env.section()))
    check(t.env.back_to_launcher() is False, "Back to a launcher without MAC")

    # with MAC: the tile, until MCM asks for the tab
    t = Tab(srcs, mac=True)
    t.env.sync()
    app = t.p.g.APPS["fotz"]
    check(len(t.p.g.REG) == 0 and app is not None, "with MAC: registered %s, tile %s" % (len(t.p.g.REG), app))
    same_fn = t.p.lua.eval("function() return APPS.fotz.func == fotz_tab.page_ui end")()
    check(app.tab == "eptFactions" and app.texture == "fotz_app" and app.name == "st_fotz_tab" and same_fn,
          "the tile: %s %s %s" % (app.tab, app.texture, app.name))
    check(t.env.section() == "eptFactions" and t.env.back_to_launcher() is True, "tiled: section %s" % t.env.section())
    t.env.sync()
    check(t.p.g.ADDS == 1, "a second sync gave MAC the tile again (%d adds)" % t.p.g.ADDS)
    t.run('MCM["fotz/pda_tab"] = true; pda_menu("eptTasks")')
    t.env.sync()
    check(list(t.p.g.REG.values()) == ["st_fotz_tab"] and t.p.g.APPS["fotz"] is None and list(t.p.g.REMOVED.values()) == ["fotz"],
          "the option on: tab %s, tile %s" % (list(t.p.g.REG.values()), t.p.g.APPS["fotz"]))
    check(t.p.g.MENU.section == "eptTasks", "the PDA left its page for %s" % t.p.g.MENU.section)
    # off again while the page is open in its tab: the tile comes back, the PDA goes to Tasks
    t.run('MCM["fotz/pda_tab"] = false; pda_menu("ept_dynamic_1")')
    t.env.sync()
    check(list(t.p.g.UNREG.values()) == ["ept_dynamic_1"] and t.p.g.APPS["fotz"] is not None,
          "the option off: unregistered %s, tile %s" % (list(t.p.g.UNREG.values()), t.p.g.APPS["fotz"]))
    check(t.p.g.MENU.section == "eptTasks", "the PDA stayed on a tab that's gone: %s" % t.p.g.MENU.section)

    # a tab the registry refuses leaves the tile
    t = Tab(srcs, mac=True)
    t.run('MCM["fotz/pda_tab"] = true; REFUSE = true')
    t.env.sync()
    check(t.p.g.APPS["fotz"] is not None and t.env.section() == "eptFactions", "refused: no tile")


#: a DXML document as far as the edit reads it
FAKE_XML = """
function fake_xml(has_tab, has_caption)
    local x = { inserted = {} }
    function x:query(q)
        if q == "tab" then return has_tab and { "TAB" } or {} end
        if q == "caption_static" then return has_caption and { "CAP" } or {} end
        if string.find(q, "eptFactions", 1, true) then return #self.inserted > 0 and { "BTN" } or {} end
        return {}
    end
    function x:insertFromXMLString(s, parent) self.inserted[#self.inserted + 1] = { s = s, parent = parent } end
    return x
end
"""


def parked(srcs):
    t = Tab(srcs)
    t.run(FAKE_XML)
    edit = t.p.g.modxml_fotz_tab.edit
    x = t.p.lua.eval("fake_xml(true, true)")
    check(edit("ui\\pda_16.xml", x) is True and edit("ui\\pda_16.xml", x) is False and len(x.inserted) == 1,
          "the button went in %d times" % len(x.inserted))
    b = x.inserted[1]
    check('id="eptFactions"' in b.s and 'width="0"' in b.s and 'x="1000"' in b.s and b.parent == "TAB",
          "the button: %s" % b.s)
    for name, args in (("ui\\pda.xml", (True, False)), ("ui\\pda_apps_16.xml", (True, False)),
                       ("ui\\ui_actor_menu.xml", (True, True)), ("gameplay\\dialogs.xml", (True, True))):
        y = t.p.lua.eval("fake_xml(%s, %s)" % tuple("true" if a else "false" for a in args))
        check(edit(name, y) is False and len(y.inserted) == 0, "a button in %s" % name)


def mcm_option(srcs):
    t = Tab(srcs)
    ids = [g.id for g in t.p.g.fotz_mcm.on_mcm_load().gr.values()]
    check("pda_tab" not in ids, "the tab option without MAC")
    t = Tab(srcs, mac=True)
    ids = [g.id for g in t.p.g.fotz_mcm.on_mcm_load().gr.values()]
    check("pda_tab" in ids and ids[-1] == "about" and ids.index("pda_tab") == ids.index("tab_key") + 1,
          "with MAC, the options: %s" % ids)


def run(srcs):
    n = strings(srcs)
    your_own(srcs)
    yours(srcs)
    restore(srcs)
    ways_in(srcs)
    parked(srcs)
    mcm_option(srcs)
    return "6 scenarios, %d strings" % n


def main():
    srcs = {m: io.open(os.path.join(SCRIPTS_DIR, m + ".script"), encoding="utf-8").read() for m in MODULES}
    if len(sys.argv) > 1:
        name = sys.argv[1]
        m = MUTANTS[name]
        old, new, module = m[0], m[1], (m[2] if len(m) > 2 else "fotz_tab")
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
