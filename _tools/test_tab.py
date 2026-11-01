"""Run fotz_tab.script's page() under LuaJIT 2.0 on top of the real politics engine (test_politics'
world), and check what the Factions tab shows.

Checked: your side without a faction (your own) and with one (yours, every faction whose relation
can change); a row only for a faction whose relation with your side can change, its standing in
words (an event in force before the lines at -1000 and 1000), its color, which way it went on
politics' last day in words, its leader, the event holding it; the factions that never change in a
line for each standing, permanent enemies first; lists as a sentence gives them, and "N more" past a
cap; the war log, newest first, four at most, with its dates; where the fighting is (territory's
fronts at the last census): a sentence a level about your side when it fights there, else the
strongest side, against every enemy there, with its verdict from the share of the two biggest, the
stragglers left out, evenly matched naming the two biggest, your side named as yours, your side's levels first, four at most; the wait and
none lines; members (the dead apart, near or away, five then "and N more"); why politics stands
down; Restore relations; the button to the PDA's Relations tab; every string exists.
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
MODULES = ("fotz_tab", "z_fotz_mac", "modxml_fotz_tab", "fotz_mcm", "fotz_territory", "fotz_patch")
SCRIPT = os.path.join(SCRIPTS_DIR, "fotz_tab.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "band_line": ("    if rel <= -1000 then", "    if rel < -1000 then"),
    "event_first": ('    if kind == "war" or kind == "truce" or kind == "alliance" then', "    if false then"),
    "log_order": ("for i = #h, math.max(1, #h - LOG_LINES + 1), -1 do", "for i = 1, math.min(#h, LOG_LINES) do"),
    "log_cap": ("for i = #h, math.max(1, #h - LOG_LINES + 1), -1 do", "for i = #h, 1, -1 do"),
    "dead_counted": ("        for _, m in pairs(F.members) do\n            if not m.dead then",
                     "        for _, m in pairs(F.members) do\n            if true then"),
    # settler loyalty on the page (0.5.0)
    "near_unlimited": ("        if #out >= MEMBER_LINES then\n            break\n        end\n", ""),
    "requests_unlimited": ("        if i > REQUEST_ROWS then\n            break\n        end\n", ""),
    "sworn_as_settler": ('            local form = not s.sworn and "st_fotz_tab_member_settler"',
                         '            local form = "st_fotz_tab_member_settler" or "st_fotz_tab_member_settler"'),
    "member_state": ('local state = it.m.dead and "dead" or (level.object_by_id(it.id) and "near" or "away")',
                     'local state = "near"'),
    "member_cap": ("        if i > MEMBER_LINES then", "        if false then"),
    "side": ("    return F and fotz_politics.OWN or get_actor_true_community()", "    return get_actor_true_community()"),
    "status": ('p.status = why and text("st_fotz_tab_down_" .. why) or text("st_fotz_tab_in_charge")',
               'p.status = text("st_fotz_tab_in_charge")'),
    "date": ('return m and (dd .. "." .. m) or tostring(d or "")', 'return tostring(d or "")'),
    "fixed_as_rows": ("            if not pair then", "            if false then"),
    "fixed_one_band": ("                local list = fixed[band(rel)]", "                local list = fixed.neutral"),
    "fixed_order": ('    for _, b in ipairs({ "enemies", "neutral", "friends" }) do',
                    '    for _, b in ipairs({ "neutral", "enemies", "friends" }) do'),
    "trend_sign": ('return t > 0 and "up" or "down"', 'return t > 0 and "down" or "up"'),
    "trend_unsaid": ('                    change = trend and text("st_fotz_tab_trend_" .. trend) or "",',
                     '                    change = "",'),
    "event_split": ('                    event = event_line(ev) or "", trend = trend,', '                    event = "", trend = trend,'),
    "leader_alive": ("    if se and (se.alive == nil or se:alive()) then", "    if se then"),
    "leader_trader": ("    if se and (se.alive == nil or se:alive()) then", "    if se and se:alive() then"),
    "leader_gone": ("local name = se and se:character_name() or (fp.leader_name and game.translate_string(fp.leader_name))",
                    "local name = se and se:character_name()"),
    "list_no_and": ('    return table.concat(list, ", ", 1, #list - 1) .. " " .. text("st_fotz_and") .. " " .. list[#list]',
                    '    return table.concat(list, ", ")'),
    "list_uncapped": ("    if cap and n > cap then", "    if false then"),
    "fight_total_ignored": ("        if f.fa + f.fb >= min and math.min(f.fa, f.fb) >= SIDE_MIN then",
                            "        if math.min(f.fa, f.fb) >= SIDE_MIN then"),
    "fight_stragglers": ("        if f.fa + f.fb >= min and math.min(f.fa, f.fb) >= SIDE_MIN then",
                         "        if f.fa + f.fb >= min then"),
    "focus_not_yours": ("        local focus = lv.foes[side] and side or nil", "        local focus = nil"),
    "behind_not_turned": ("        if share >= 0.5 then", "        if true then"),
    "behind_every_foe": ("                if lv.n[f] > mine then", "                if true then"),
    "verdict_line": ('VERDICTS = { { 0.8, "control" }, { 2 / 3, "winning" }, { 0.55, "ahead" } }',
                     'VERDICTS = { { 0.8, "control" }, { 0.7, "winning" }, { 0.55, "ahead" } }'),
    "yours_not_first": ("        if x.yours ~= y.yours then\n            return x.yours\n        end\n", ""),
    "even_names_all": ('    if fx.kind == "even" then\n        w, l = { w[1] }, { l[1] }\n    end\n', ""),
    "your_unnamed": ('            out[i] = f == side and text("st_fotz_your", { name = P.faction_name(f) }) or P.faction_name(f)',
                     "            out[i] = P.faction_name(f)"),
    "fights_uncapped": ("        if i > FIGHT_LINES then", "        if false then"),
    "fights_wait_ignored": ("    if T and not T.COUNTED then", "    if false then"),
    "fights_no_none": ('        out[1] = text("st_fotz_tab_fighting_none")', "        out[1] = nil"),
    "relations_elsewhere": ('        m:SetActiveSubdialog("eptRelations")', '        m:SetActiveSubdialog("eptTasks")'),
    "tile_section_left": ("            if was == modxml_fotz_tab.SECTION and TAB then", "            if false then"),
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
}

FACTIONS = ("stalker", "bandit", "csky", "dolg", "freedom", "killer", "army", "ecolog", "monolith",
            "renegade", "greh", "isg")

#: territory's fronts at a census, each faction's fighters the same on a level across its fronts
FRONTS = """
STR.l01_escape, STR.l02_garbage, STR.l03_agroprom, STR.l04_darkvalley = "Cordon", "Garbage", "Agroprom", "Dark Valley"
STR.l05_bar, STR.l06_rostok, STR.l07_military, STR.l08_yantar = "Bar", "Rostok", "Army Warehouses", "Yantar"
fotz_territory.FRONTS = {
    { a = "bandit", b = "army", level = "l02_garbage", fa = 5, fb = 40 },
    { a = "stalker", b = "bandit", level = "l02_garbage", fa = 12, fb = 5 },
    { a = "csky", b = "freedom", level = "l03_agroprom", fa = 20, fb = 18 },
    { a = "dolg", b = "killer", level = "l03_agroprom", fa = 10, fb = 26 },
    { a = "ecolog", b = "monolith", level = "l04_darkvalley", fa = 3, fb = 20 },
    { a = "freedom", b = "dolg", level = "l04_darkvalley", fa = 9, fb = 6 },
    { a = "dolg", b = "killer", level = "l04_darkvalley", fa = 6, fb = 4 },
    { a = "army", b = "renegade", level = "l04_darkvalley", fa = 2, fb = 3 },
    { a = "dolg", b = "freedom", level = "l06_rostok", fa = 12, fb = 12 },
    { a = "dolg", b = "bandit", level = "l06_rostok", fa = 12, fb = 4 },
    { a = "ecolog", b = "monolith", level = "l08_yantar", fa = 30, fb = 4 },
    { a = "ecolog", b = "killer", level = "l08_yantar", fa = 30, fb = 5 },
    { a = "bandit", b = "stalker", level = "l05_bar", fa = 21, fb = 10 },
    { a = "csky", b = "renegade", level = "l01_escape", fa = 4, fb = 3 },
    { a = "freedom", b = "monolith", level = "l07_military", fa = 30, fb = 2 } }
"""
#: every fight in those fronts, seen from Duty's side, in the page's order
FIGHTS = ["Agroprom: Mercenaries winning, your Duty losing",
          "Dark Valley: Freedom ahead, your Duty holding on",
          "Rostok: your Duty and Freedom evenly matched",
          "Garbage: Military in control, Bandits nearly gone",
          "Yantar: Ecologists in control, Mercenaries and Monolith nearly gone",
          "Bar: Bandits winning, Loners losing"]


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
        for name in ("modxml_fotz_tab", "z_fotz_mac", "fotz_mcm", "fotz_territory", "fotz_patch"):
            g[name] = load(srcs[name], name)
        self.env = load(srcs["fotz_tab"], "fotz_tab")
        g.fotz_tab = self.env
        self.env.on_game_start()

    def run(self, code):
        return self.p.lua.execute(code)

    def page(self):
        return self.env.page()


def rows(p):
    return {p.rows[i].faction: p.rows[i] for i in range(1, len(p.rows) + 1)}


def lines(t):
    return [t[i] for i in range(1, len(t) + 1)]


def names(srcs):
    """Lists as a sentence gives them, and a cap past which the rest are "N more"."""
    t = Tab(srcs)
    nl = t.env.names_list
    lst = t.p.lua.table
    got = [nl(lst()), nl(lst("A")), nl(lst("A", "B")), nl(lst("A", "B", "C")), nl(lst("A", "B", "C"), 3),
           nl(lst("A", "B", "C", "D"), 3), nl(lst("A", "B", "C", "D", "E"), 3)]
    check(got == ["", "A", "A and B", "A, B and C", "A, B and C", "A, B and 2 more", "A, B and 3 more"], "lists %s" % got)


def your_own(srcs):
    t = Tab(srcs)
    p = t.page()
    r = rows(p)
    check(p.leading is False and p.side == "dolg" and p.title == "Duty", "side %s, title %s" % (p.side, p.title))
    check(p.subtitle.startswith("You lead no faction"), "subtitle %s" % p.subtitle)
    # this world fixes Duty and Freedom, and the four factions politics leaves alone
    check(sorted(r) == ["army", "bandit", "csky", "ecolog", "killer", "stalker"], "rows: %s" % sorted(r))
    check(lines(p.fixed) == ["Always neutral: Freedom, Monolith, Renegades, Sin and UNISG."], "fixed %s" % lines(p.fixed))
    check(p.status == "Relations change as the factions fight.", "status %s" % p.status)
    check(p.icon == "ui_mm_faction_dolg" and r["killer"].icon == "ui_mm_faction_killer", "icons")
    check(r["killer"].standing == "Neutral" and r["killer"].change == "" and r["killer"].detail == "Dushman (dead)",
          "killer at start: %r / %r / %r" % (r["killer"].standing, r["killer"].change, r["killer"].detail))
    check(lines(p.log) == ["Nothing yet: wars, truces and alliances show here."], "empty log %s" % lines(p.log))
    check(p.members is None, "members without a faction")

    # a war, the lines at -1000 and 1000, and permanent enemies
    t.run('REL["dolg>bandit"] = -1000; REL["dolg>csky"] = 1000; REL["dolg>army"] = 999')
    t.run('for _, f in ipairs({ "monolith", "renegade", "greh", "isg" }) do REL["dolg>" .. f] = -2000 end')
    t.p.env.S.events["dolg/killer"] = t.p.lua.eval('{ kind = "war", since = "2012-05-03", a = "dolg", b = "killer" }')
    t.p.env.S.drift["dolg/killer"] = -1200
    t.p.env.apply()
    p = t.page()
    r = rows(p)
    check(r["killer"].standing == "At war" and r["killer"].band == "war" and r["killer"].event == "at war since 03.05",
          "killer: %r, %r" % (r["killer"].standing, r["killer"].event))
    check(r["csky"].standing == "Friendly" and r["csky"].event == "", "csky: %r" % r["csky"].standing)
    check(r["bandit"].standing == "Hostile" and r["army"].standing == "Neutral",
          "bandit %r, army %r" % (r["bandit"].standing, r["army"].standing))
    check(list(r["killer"].color.values()) == [230, 80, 70], "war color %s" % list(r["killer"].color.values()))
    check(lines(p.fixed) == ["Permanent enemies: Monolith, Renegades, Sin and UNISG.", "Always neutral: Freedom."],
          "fixed %s" % lines(p.fixed))
    t.run('REL["dolg>freedom"] = 1000')
    check(lines(t.page().fixed) == ["Permanent enemies: Monolith, Renegades, Sin and UNISG.", "Permanent friends: Freedom."],
          "fixed with a friend %s" % lines(t.page().fixed))

    # which way politics moved each pair on its last day, in words
    t.p.env.S.trend["dolg/killer"] = -360
    t.p.env.S.trend["csky/dolg"] = 120
    r = rows(t.page())
    check(r["killer"].trend == "down" and r["killer"].change == "getting worse"
          and r["csky"].trend == "up" and r["csky"].change == "getting better",
          "trends %s %r, %s %r" % (r["killer"].trend, r["killer"].change, r["csky"].trend, r["csky"].change))

    # the war log: newest first, four at most
    for i in range(12):
        t.p.env.S.history[len(t.p.env.S.history) + 1] = t.p.lua.eval(
            '{ kind = "war", a = "dolg", b = "killer", day = "2012-05-%02d" }' % (i + 1))
    t.p.env.S.history[len(t.p.env.S.history) + 1] = t.p.lua.eval('{ kind = "truce", a = "dolg", b = "killer", day = "2012-05-20" }')
    log = lines(t.page().log)
    check(len(log) == 4 and log[0] == "20.05  Duty and Mercenaries made a truce" and log[1] == "12.05  Duty and Mercenaries went to war",
          "log %s" % log)

    # where the fighting is, from territory's last census
    check(lines(t.page().fights) == ["Not counted yet: the census comes shortly after a load."],
          "before the census: %s" % lines(t.page().fights))
    t.run("fotz_territory.COUNTED = true")
    check(lines(t.page().fights) == ["No fighting: no two hostile factions share a level."], "none: %s" % lines(t.page().fights))
    t.run(FRONTS)
    fx = t.env.fights(t.p.g.fotz_territory.FRONTS, "dolg")
    got = [t.env.fight_line(fx[i], "dolg") for i in range(1, len(fx) + 1)]
    check(got == FIGHTS, "fights %s" % got)
    check(lines(t.page().fights) == FIGHTS[:4], "the page's four %s" % lines(t.page().fights))

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
    t.run('for _, f in ipairs({ "monolith", "renegade", "greh", "isg" }) do REL["fotz_own>" .. f] = -2000 end')
    p = t.page()
    r = rows(p)
    check(p.leading is True and p.side == "fotz_own" and p.title == "Wolves", "side %s, title %s" % (p.side, p.title))
    check(p.subtitle == "Your faction · founded 01.05 · came from: Duty · members: 2", "subtitle %r" % p.subtitle)
    # every faction politics manages can change with yours; the four that never change, in a line
    check(p.icon == "fotz_your_faction" and sorted(r) == sorted(["stalker", "bandit", "csky", "dolg", "freedom", "killer",
                                                                  "army", "ecolog"]), "icon %s, rows %s" % (p.icon, sorted(r)))
    check(lines(p.fixed) == ["Permanent enemies: Monolith, Renegades, Sin and UNISG."], "fixed %s" % lines(p.fixed))
    check(r["killer"].standing == "Neutral", "killer: %s" % r["killer"].standing)
    check(r["dolg"].detail == "Voronin" and r["stalker"].detail == "Sidorovich" and r["army"].detail == "Kuznetsov (dead)",
          "leaders %r %r %r" % (r["dolg"].detail, r["stalker"].detail, r["army"].detail))
    check(lines(p.members) == ["Fedya (Clear Sky), away", "Oleg (Duty), dead", "Vaska (Loners), with you"],
          "members %s" % lines(p.members))
    # your faction's fights are yours: Garbage's Duty there is Duty, not you
    t.run("fotz_territory.COUNTED = true")
    t.run(FRONTS.replace('a = "dolg", b = "killer", level = "l03_agroprom"', 'a = "fotz_own", b = "killer", level = "l03_agroprom"'))
    check(lines(t.page().fights)[0] == "Agroprom: Mercenaries winning, your Wolves losing", "yours: %s" % lines(t.page().fights))

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
    check(lines(t.page().log)[0] == "02.05  Relations reset to their start", "log %s" % lines(t.page().log))


def strings(srcs):
    import re
    import xml.etree.ElementTree as ET
    root = ET.fromstring(open(TP.ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    ui = io.open(os.path.join(HERE, "..", "gamedata", "scripts", "ui_fotz_tab.script"), encoding="utf-8").read()
    # whole ids; the prefixes the script builds ids from are listed below in full
    want = {w for w in re.findall(r'"(st_fotz_\w*)"', srcs["fotz_tab"] + ui + srcs["z_fotz_mac"]) if not w.endswith("_")}
    for b in ("war", "enemies", "truce", "neutral", "friends", "alliance"):
        want.add("st_fotz_tab_band_" + b)
    for k in ("war", "war_over", "truce", "truce_over", "alliance", "alliance_over", "restored"):
        want.add("st_fotz_tab_log_" + k)
    for k in ("war_since", "truce_until", "alliance_since", "trend_up", "trend_down", "fixed_enemies", "fixed_neutral",
              "fixed_friends"):
        want.add("st_fotz_tab_" + k)
    for k in ("control", "winning", "ahead", "even"):
        want.add("st_fotz_fight_" + k)
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
    # the numbers are the PDA's own Relations tab's
    t.run('pda_menu("ept_dynamic_1")')
    check(t.env.to_relations() is True and t.p.g.MENU.section == "eptRelations", "the button went to %s" % t.p.g.MENU.section)

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
    t2 = Tab(srcs, mac=True)
    t2.env.sync()
    t2.run('MCM["fotz/pda_tab"] = true; pda_menu("eptFactions")')
    t2.env.sync()
    check(t2.p.g.MENU.section == "ept_dynamic_1", "from the tile to the tab, the PDA stayed on %s" % t2.p.g.MENU.section)
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


def settler_lines(srcs):
    """With settler loyalty (fotz_loyalty): a settler member's line has their camp and loyalty, a
    sworn member's says so (between camps too), the residents nearest to asking follow the members
    while there's room, and the requests go to the page apart, two at most, each with its id for
    the buttons."""
    t = Tab(srcs, pre=TP.led_lua() + """
fotz_faction.F.members = { [501] = { name = "Vaska", mother = "stalker", joined = "2012-05-01" },
                           [701] = { name = "Petro", mother = "dolg", joined = "2012-05-01", via = "settler" },
                           [702] = { name = "Ivan", mother = "dolg", joined = "2012-05-01", via = "settler" },
                           [703] = { name = "Sasha", mother = "dolg", joined = "2012-05-01", via = "settler" } }
fotz_loyalty = { page_lists = function() return {
    requests = { { id = 801, name = "Boris", v = 72 }, { id = 802, name = "Gleb", v = 70 }, { id = 803, name = "Dima", v = 71 } },
    members = { { id = 701, name = "Petro", v = 64, camp = "Cordon Settlement" },
                { id = 702, name = "Ivan", v = 100, sworn = true, camp = "Cordon Settlement" },
                { id = 703, name = "Sasha", v = 100, sworn = true } },
    near = { { id = 901, name = "Kim", v = 69, camp = "Cordon Settlement" },
             { id = 902, name = "Lev", v = 50, camp = "Cordon Settlement" } } } end }
""")
    p = t.page()
    want = ["Ivan (Cordon Settlement), sworn for life", "Petro (Cordon Settlement), loyalty 64",
            "Sasha, sworn for life, between camps", "Vaska (Loners), away", "Kim (Cordon Settlement), resident, loyalty 69"]
    check(lines(p.members) == want, "members %s" % lines(p.members))
    got = [(p.requests[i].id, p.requests[i].line) for i in range(1, len(p.requests) + 1)]
    check(got == [(801, "Boris asks to join"), (802, "Gleb asks to join")], "requests %s" % got)
    # without a faction, no requests and no members
    t.run("fotz_faction.F = nil")
    p = t.page()
    check(p.members is None and p.requests is None, "a page without a faction lists %s, %s" % (p.members, p.requests))


def run(srcs):
    n = strings(srcs)
    names(srcs)
    your_own(srcs)
    yours(srcs)
    restore(srcs)
    ways_in(srcs)
    parked(srcs)
    mcm_option(srcs)
    settler_lines(srcs)
    return "8 scenarios, %d strings" % n


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
