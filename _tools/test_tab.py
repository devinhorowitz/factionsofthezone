"""Run fotz_tab.script's page() under LuaJIT 2.0 on top of the real politics engine (test_politics'
world), and check what the Factions tab shows.

Checked: your side without a faction (your own) and with one (yours, all twelve factions); each
row's standing in words and colors, an event in force before the lines at -1000 and 1000; how far
politics moved a pair, "never changes" for fixed pairs and factions; the census's ground and
fighters; the war log, newest first, ten at most, with its dates; members (the dead apart, near or
away, eight then "and N more"); why politics stands down; Restore relations; every string exists.
The page's layout (ui_fotz_tab.script) is checked in game.

    python test_tab.py            the real script
    python test_tab.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import sys

import test_politics as TP

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "gamedata", "scripts", "fotz_tab.script")

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
    "side": ("local side = F and P.OWN or get_actor_true_community()", "local side = get_actor_true_community()"),
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

    def __init__(self, src, pre=None, m_data=None):
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
        self.env = lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                            "local f = assert(loadstring(src, 'fotz_tab')) setfenv(f, env) f() return env end")(src)
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


def your_own(src):
    t = Tab(src)
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

    # the war log: newest first, ten at most
    for i in range(12):
        t.p.env.S.history[len(t.p.env.S.history) + 1] = t.p.lua.eval(
            '{ kind = "war", a = "dolg", b = "killer", day = "2012-05-%02d" }' % (i + 1))
    t.p.env.S.history[len(t.p.env.S.history) + 1] = t.p.lua.eval('{ kind = "truce", a = "dolg", b = "killer", day = "2012-05-20" }')
    log = lines(t.page().log)
    check(len(log) == 10 and log[0] == "20.05  Truce: Duty and Mercenaries" and log[1] == "12.05  War: Duty and Mercenaries",
          "log %s" % log)

    # standing down says why
    t.run('MCM["fotz/politics"] = false')
    check(t.page().status == "Relations stand still: turned off in MCM.", "off: %s" % t.page().status)
    t.run('MCM["fotz/politics"] = nil; OPT["alife/general/dynamic_relations"] = true')
    check(t.page().status == "Relations are left to the base game's dynamic relations.", "dynamic: %s" % t.page().status)
    return t


def yours(src):
    t = Tab(src, pre=TP.led_lua() + """
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

    # more than eight
    t.run("for i = 1, 10 do fotz_faction.F.members[600 + i] = { name = 'Zed ' .. string.char(64 + i), mother = 'stalker' } end")
    m = lines(t.page().members)
    check(len(m) == 9 and m[-1] == "and 5 more", "nine lines, the last 'and 5 more': %s" % m)
    return t


def restore(src):
    t = Tab(src)
    t.run('day("2012-05-01")')
    t.run('kill("dolg", "killer", "veteran", 60)')
    t.run('day("2012-05-02")')
    check(t.p.drift("dolg/killer") == -400, "a drift to restore: %s" % t.p.drift("dolg/killer"))
    t.p.env.restore()
    check(t.p.drift("dolg/killer") is None and t.p.pending("dolg/killer") is None, "restore left drift or pressure")
    check(all(t.p.rel(c) == TP.DK_ANCHORS[c] for c in TP.CELLS), "restore didn't write the starts back")
    check(lines(t.page().log)[0] == "02.05  Relations restored to their start", "log %s" % lines(t.page().log))


def strings(src):
    import re
    import xml.etree.ElementTree as ET
    root = ET.fromstring(open(TP.ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    ui = io.open(os.path.join(HERE, "..", "gamedata", "scripts", "ui_fotz_tab.script"), encoding="utf-8").read()
    # whole ids; the prefixes the script builds ids from are listed below in full
    want = {w for w in re.findall(r'"(st_fotz_tab\w*)"', src + ui) if not w.endswith("_")}
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
    want |= {"ui_mcm_fotz_tab_key", "ui_mcm_fotz_tab_key_desc"}
    missing = sorted(want - have)
    check(not missing, "missing from the English table: %s" % missing)
    return len(want)


def run(src):
    n = strings(src)
    your_own(src)
    yours(src)
    restore(src)
    return "3 scenarios, %d strings" % n


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
