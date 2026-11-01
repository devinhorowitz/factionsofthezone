"""Run fotz_loyalty.script under LuaJIT 2.0 against a stand-in for Homestead (its camps, records,
comfort and raid squads), the faction you lead and the game's news, and check settler loyalty.

Checked: the shipped config's [loyalty] section is the script's defaults; each start term; each
day's term (living there, working, the camp's comfort, your faction's relation with theirs times
their tier's pull, your wars, the sworn near them, capped, not counting themselves); the events (a
promotion, a weapon bought, again after Homestead re-creates them, an expedition back, a raid beaten
off, guards more, a raid you left not counted, a campmate killed); a request at the ask threshold,
once a day, withdrawn under its threshold; Accept and its news; Decline, its cost and its wait;
"Accept join requests"; a settler member leaving under the leave threshold, a companion member
not; swearing, each condition failing alone; the sworn kept at full loyalty; a member who stops
being a resident leaving, one who follows you staying; a fallen camp (the sworn stay whatever their
loyalty, other members at a roll of it, residents forgotten); the trip to a camp with room (the
smart nearest its flag, the squad steered there, moving in only near the flag or that smart and on
its level, through Homestead's recruitment, the squad let go); a camp that turns them away or
falls meanwhile crossed off; with nowhere to go the sworn waiting and looking again each day, the
others going back, a companion staying a member; a re-created settler keeping their entry and
membership; the first census only starting the book; nothing without a faction, Homestead or the
MCM switch; the page's lists; the strings exist.

    python test_loyalty.py            the real script
    python test_loyalty.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(HERE, "..", "gamedata")
SCRIPT = os.path.join(GD, "scripts", "fotz_loyalty.script")
CONFIG = os.path.join(GD, "configs", "plugins", "fotz_politics.ltx")
ENG = os.path.join(GD, "configs", "text", "eng", "st_fotz.xml")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "no_same_faction": ("    if comm and comm == f.mother then\n        v = v + cfg.same_faction", "    if false then\n        v = v + cfg.same_faction"),
    "no_companion_start": ("    if rec.was_companion then", "    if false then"),
    "enemies_start_friends": ("    elseif r <= ENEMIES then\n        v = v + cfg.start_enemies", "    elseif r <= ENEMIES then\n        v = v + cfg.start_friends"),
    "idle_works": ('    return rec.job ~= nil and rec.job ~= "idle" and rec.job ~= "companion"', "    return rec.job ~= nil"),
    "no_comfort_top": ("    if c >= cfg.morale_top then\n        v = v + cfg.morale_top_add\n    elseif", "    if false then\n    elseif"),
    "no_low_comfort": ("    elseif c <= cfg.morale_low then\n        v = v + cfg.morale_low_add\n", ""),
    "no_pull": ("local r, pull = rel_with(own_faction(id, rec)), 1 + (rec.tier or 0) / 3", "local r, pull = rel_with(own_faction(id, rec)), 1"),
    "no_wars": ("    if at_war >= cfg.many_wars then", "    if false then"),
    "friends_ignored": ("    elseif r >= FRIENDS then\n        v = v + cfg.day_friends * pull", "    elseif false then\n        v = v + cfg.day_friends * pull"),
    "sworn_uncapped": ("math.min(sworn_in(res, e.hub), cfg.sworn_near_max)", "sworn_in(res, e.hub)"),
    "promotion_once": ("        e.v = clamp(e.v + cfg.promotion * (tier - e.tier))", "        e.v = clamp(e.v + cfg.promotion)"),
    "no_weapon": ("    if bought > e.bought then\n        e.v = clamp(e.v + cfg.weapon)\n    end\n", ""),
    "no_expedition": ("    if e.away and not rec.on_expedition then", "    if false then"),
    "raid_any_end": ("    if left > 0 then\n        log(", "    if false then\n        log("),
    "guards_as_others": ('(rec.job == "guard" and cfg.raid_guard or cfg.raid_beaten)', "cfg.raid_beaten"),
    "no_campmate_loss": ("            o.v = clamp(o.v + cfg.campmate_killed)", "            o.v = o.v"),
    "asks_while_waiting": ("    if e.req or e.v < cfg.ask or (e.quiet", "    if e.v < cfg.ask or (e.quiet"),
    "near_by_name": ("    table.sort(out.near, function(x, y) return x.v > y.v or", "    table.sort(out.near, function(x, y) return false or"),
    "never_withdrawn": ("    if e.req and e.v < cfg.withdraw then", "    if false then"),
    "decline_free": ("    e.v = clamp(e.v - cfg.decline_cost)", "    e.v = e.v"),
    "decline_no_wait": ("(e.quiet and days_between(day, e.quiet) > 0)", "false"),
    "no_accept_all": ("    if accept_all() then", "    if false then"),
    "never_leaves": ('        if e.v < cfg.leave and m.via == "settler" then', "        if false then"),
    "companion_leaves": ('        if e.v < cfg.leave and m.via == "settler" then', "        if e.v < cfg.leave then"),
    "sworn_any_tier": ("        if rec and (rec.tier or 0) >= cfg.sworn_tier and e.v >= cfg.sworn_loyalty", "        if rec and e.v >= cfg.sworn_loyalty"),
    "sworn_any_loyalty": ("(rec.tier or 0) >= cfg.sworn_tier and e.v >= cfg.sworn_loyalty", "(rec.tier or 0) >= cfg.sworn_tier"),
    "sworn_at_once": ("            and days_between(m.joined or day, day) >= cfg.sworn_days then", "            then"),
    "sworn_moves": ("    if e.sworn then\n        e.v = cfg.sworn_loyalty\n        return\n    end\n    local v = e.v + cfg.resident",
                    "    local v = e.v + cfg.resident"),
    "follower_leaves": ("        if fotz_faction.is_companion(id) then", "        if false then"),
    "resident_kept": ("            stop_being_resident(id, e, \"no longer a resident\")\n            res[id] = nil\n", ""),
    "sworn_falls_with_camp": ("    if not e.sworn and math.random() >= e.v / 100 then", "    if math.random() >= e.v / 100 then"),
    "sworn_nowhere_leave": ('    if e.sworn then\n        log("%s, sworn, waits for a camp with room", e.name)', '    if false then\n        log("%s, sworn, waits for a camp with room", e.name)'),
    # the trip's smart: none an enemy of yours holds (run 20)
    "enemies_ignored": ("            if d < s2 and d <= SAFE_SMART * SAFE_SMART and not enemies_at(sm) then",
                        "            if d < s2 and d <= SAFE_SMART * SAFE_SMART then"),
    "no_safe_limit": ("and d <= SAFE_SMART * SAFE_SMART and not enemies_at(sm)", "and not enemies_at(sm)"),
    "safe_unused": ("    best = safe or best\n", ""),
    "monsters_harmless": ("            if is_squad_monster and is_squad_monster[sq.player_id] then", "            if false then"),
    "any_community": ("            if a_faction(comm) and rel_with(comm) <= ENEMIES then", "            if comm and rel_with(comm) <= ENEMIES then"),
    "war_line_strict": ("a_faction(comm) and rel_with(comm) <= ENEMIES", "a_faction(comm) and rel_with(comm) < ENEMIES"),
    "zombied_unknown": ('    return comm == "zombied"\n', "    return false\n"),
    "no_relink": ("                if camp.survivors[id].name == e.name then", "                if false then"),
    "first_census_counts": ("    if b.day == nil then\n        look()\n        b.day = date\n        return\n    end\n", ""),
    "ignores_switch": ('return F() ~= nil and homestead() ~= nil and not (ui_mcm and ui_mcm.get("fotz/loyalty") == false)',
                       "return F() ~= nil and homestead() ~= nil"),
    "dead_kept": ("        if e.dead then\n            res[id] = nil\n        else", "        if false then\n        else"),
    # between camps (0.5.0, second part)
    "fell_no_roll": ("    if not e.sworn and math.random() >= e.v / 100 then", "    if false then"),
    "roll_inverted": ("math.random() >= e.v / 100", "math.random() < e.v / 100"),
    "no_steer": ("        sq.scripted_target = smart\n", ""),
    "far_arrives": ("    if not (by_flag or at_smart) then", "    if false then"),
    "smart_not_there": ("    local at_smart = at and here:distance_to(vector():set(at.x, at.y, at.z)) <= ARRIVE_SMART",
                        "    local at_smart = false"),
    "any_level_arrives": ("if not (npc and npc:alive() and p and level.name() == camp.level) then", "if not (npc and npc:alive() and p) then"),
    "tried_ignored": ("        if not (e.tried and e.tried[it.hub_id]) then", "        if true then"),
    "waiting_never_looks": ("            if e.sworn and not e.hub and not e.trip and member(id) then\n                e.tried = nil\n                set_out(id, e)\n            end\n", ""),
    "lost_target_kept": ("            if not camp then\n                e.tried = e.tried or {}", "            if false then\n                e.tried = e.tried or {}"),
    "farthest_smart": ("            if d < d2 then", "            if d > d2 then"),
    "unsworn_waits": ('    if e.sworn then\n        log("%s, sworn, waits for a camp with room", e.name)', '    if true then\n        log("%s, sworn, waits for a camp with room", e.name)'),
    "keeps_target": ("        steer(id, nil)\n        e.hub, e.trip, e.tried, e.label", "        e.hub, e.trip, e.tried, e.label"),
    "companion_travels": ('    if fotz_faction.is_companion(id) then\n        m.via = "companion"\n        return true\n    end\n    if not e.sworn and math.random()',
                          "    if not e.sworn and math.random()"),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end
STR = {}
game = { translate_string = function(s) return STR[s] or s end }
fotz_tab = { text = function(id, fields)
    local s = game.translate_string(id)
    if fields then
        s = string.gsub(s, "{(%w+)}", function(k) return fields[k] ~= nil and tostring(fields[k]) or ("{" .. k .. "}") end)
    end
    return s
end }
DATE = "2026-11-01"
fotz_census = { game_date = function() return DATE .. " 12:00" end, listen = function(fn) CENSUS = fn end,
                FACTIONS = { "stalker", "bandit", "dolg", "freedom", "renegade" } }

-- the politics engine's calendar (its own algorithm) and what loyalty reads of it
local function day_num(s)
    local y, m, d = string.match(s, "^(%d+)-(%d+)-(%d+)")
    y, m, d = tonumber(y), tonumber(m), tonumber(d)
    if m <= 2 then y = y - 1 end
    local era = math.floor(y / 400)
    local yoe = y - era * 400
    local doy = math.floor((153 * ((m + 9) % 12) + 2) / 5) + d - 1
    return era * 146097 + yoe * 365 + math.floor(yoe / 4) - math.floor(yoe / 100) + doy - 719468
end
local function day_str(n)
    local z = n + 719468
    local era = math.floor(z / 146097)
    local doe = z - era * 146097
    local yoe = math.floor((doe - math.floor(doe / 1460) + math.floor(doe / 36524) - math.floor(doe / 146096)) / 365)
    local doy = doe - (365 * yoe + math.floor(yoe / 4) - math.floor(yoe / 100))
    local mp = math.floor((5 * doy + 2) / 153)
    local d = doy - math.floor((153 * mp + 2) / 5) + 1
    local m = mp < 10 and mp + 3 or mp - 9
    local y = yoe + era * 400 + (m <= 2 and 1 or 0)
    return string.format("%04d-%02d-%02d", y, m, d)
end
function next_day(n) DATE = day_str(day_num(DATE) + (n or 1)) end
WARS = 0
fotz_politics = {
    day_num = day_num, day_str = day_str,
    faction_name = function(f) return "F:" .. tostring(f) end,
    news_level = function() return "events" end,
}
function sync_wars()
    fotz_politics.PAIRS, fotz_politics.S = {}, { events = {} }
    for i = 1, WARS do
        local p = { key = "w" .. i, own = true }
        fotz_politics.PAIRS[#fotz_politics.PAIRS + 1] = p
        fotz_politics.S.events[p.key] = { kind = "war" }
    end
    -- a war of two other factions never counts
    local q = { key = "x", own = false }
    fotz_politics.PAIRS[#fotz_politics.PAIRS + 1] = q
    fotz_politics.S.events.x = { kind = "war" }
end
sync_wars()
REL = {}
relation_registry = { community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end }

-- the faction you lead, as far as loyalty uses it
JOINED, LEFT, RELINKED, COMPANIONS = {}, {}, {}, {}
JOIN_OK = true
fotz_faction = { OWN = "fotz_own", ACTOR_OWN = "actor_fotz_own", F = nil }
function fotz_faction.join_settler(id)
    local F = fotz_faction.F
    if not JOIN_OK or F.members[id] then return false end
    F.members[id] = { mother = "stalker", name = "n" .. id, via = "settler", joined = DATE }
    JOINED[#JOINED + 1] = id
    return true
end
function fotz_faction.leave(id, why)
    fotz_faction.F.members[id] = nil
    LEFT[#LEFT + 1] = id
end
function fotz_faction.relink(old, new)
    local F = fotz_faction.F
    local m = F.members[old]
    if not m then return false end
    F.members[old], F.members[new] = nil, m
    RELINKED[#RELINKED + 1] = old .. ">" .. new
    return true
end
function fotz_faction.is_companion(id) return COMPANIONS[id] == true end
function found() fotz_faction.F = { name = "Wolves", mother = "stalker", members = {} } end

MCM = {}
ui_mcm = { get = function(k) return MCM[k] end }
NEWS = {}
db = { actor = {} }
news_manager = { send_tip = function(actor, text) NEWS[#NEWS + 1] = text end }

-- Homestead: its camps by hub id, each with records by NPC id, its comfort and its raid
CAMPS = {}
stalker_camp_builder = { active_camps = CAMPS,
    get_camp_label = function(camp) return camp.label or "Camp" end,
    get_camp_morale = function(camp) return camp.comfort or 50 end }
function camp(hub, label, comfort)
    CAMPS[hub] = { level = "l01_escape", label = label, comfort = comfort, survivors = {} }
    return CAMPS[hub]
end
function settler(hub, id, t)
    t = t or {}
    t.name = t.name or ("n" .. id)
    t.community = t.community or "stalker"
    t.job = t.job or "idle"
    CAMPS[hub].survivors[id] = t
    return t
end
SQUADS = {}
SIM = { object = function(self, id) return SQUADS[id] end }
function alife() return SIM end
function squad(id, n) SQUADS[id] = { npc_count = function() return n end } end
T = 0
function time_global() return T end
CALLBACKS = {}
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end
function census() CENSUS({ date = DATE .. " 08:00" }) end
function victim(id) return { id = function() return id end } end

-- between camps: the roll's draw, the camps with room and their answer, smarts, squads, NPCs
RANDOM = 0.5
math.random = function() return RANDOM end
ROOM, ACCEPT, ASKED_FOR, RECRUITED = {}, {}, {}, {}
function stalker_camp_builder.get_recruitable_camps(comm)
    ASKED_FOR[#ASKED_FOR + 1] = comm
    local hubs = {}
    for hub in pairs(ROOM) do if CAMPS[hub] then hubs[#hubs + 1] = hub end end
    table.sort(hubs)
    local out = {}
    for _, hub in ipairs(hubs) do out[#out + 1] = { hub_id = hub, camp = CAMPS[hub] } end
    return out
end
function stalker_camp_builder.recruit_npc_to_camp(actor, npc, hub)
    RECRUITED[#RECRUITED + 1] = npc:id() .. ">" .. hub
    if not ACCEPT[hub] then return nil end
    CAMPS[hub].survivors[npc:id()] = { name = "n" .. npc:id(), community = "fotz_own", job = "idle" }
    return true
end
local function pos(x, y, z)
    return { x = x, y = y, z = z, distance_to = function(self, o)
        return math.sqrt((self.x - o.x) ^ 2 + (self.y - o.y) ^ 2 + (self.z - o.z) ^ 2) end }
end
function vector() return { set = function(self, x, y, z) return pos(x, y, z) end } end
LEVEL_OF_GV, LEVEL_NAMES = {}, { [1] = "l01_escape", [2] = "l02_garbage", [3] = "l03_agroprom" }
function game_graph() return { vertex = function(self, gv) return { level_id = function() return LEVEL_OF_GV[gv] end } end } end
SIM.level_name = function(self, lid) return LEVEL_NAMES[lid] end
SIMBOARD = { smarts = {} }
GV_N = 100
function smart(name, lid, x, z)
    GV_N = GV_N + 1
    local gv = GV_N
    LEVEL_OF_GV[gv] = lid
    SIMBOARD.smarts[name] = { smrt = { position = pos(x, 0, z), m_game_vertex_id = gv, name = function() return name end } }
end
-- a squad of a community at a smart; a mutant one by its behaviour
SQUADS, SQ_N = {}, 50000
function held(name, comm, behaviour)
    SQ_N = SQ_N + 1
    SQUADS[SQ_N] = { id = SQ_N, player_id = behaviour or comm, get_squad_community = function() return comm end }
    local sm = SIMBOARD.smarts[name]
    sm.squads = sm.squads or {}
    sm.squads[SQ_N] = true
end
function alife_object(id) return SQUADS[id] end
is_squad_monster = { monster = true, monster_predatory_day = true }
NPCS, SQUAD_OF, ONLINE = {}, {}, {}
local object = SIM.object
SIM.object = function(self, id) return NPCS[id] or object(self, id) end
function npc(id) NPCS[id] = { id = id }; SQUAD_OF[id] = { id = 9000 + id } end
function get_object_squad(se) return SQUAD_OF[se.id] end
LEVEL = "l01_escape"
level = { name = function() return LEVEL end, object_by_id = function(id) return ONLINE[id] end }
function online(id, x, z)
    ONLINE[id] = { id = function() return id end, alive = function() return true end, position = function() return pos(x, 0, z) end }
end
function placed(hub, label, lvl, x, z)
    local c = camp(hub, label, 50)
    c.level, c.pos = lvl, { x = x, y = 0, z = z }
    return c
end
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def config_values():
    """The shipped [loyalty] section, key -> number."""
    text = open(CONFIG, encoding="cp1251").read()
    body = text.split("[loyalty]", 1)[1]
    out = {}
    for line in body.splitlines():
        line = line.split(";", 1)[0].strip()
        if line.startswith("["):
            break
        m = re.match(r"(\w+)\s*=\s*(-?[\d.]+)$", line)
        if m:
            out[m.group(1)] = float(m.group(2))
    return out


class World:
    def __init__(self, src):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(WORLD)
        root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
        for s in root.iter("string"):
            self.g.STR[s.get("id")] = s.findtext("text")
        load = self.lua.eval("function(src, name) local env = setmetatable({}, { __index = _G }) "
                             "local f = assert(loadstring(src, name)) setfenv(f, env) f() return env end")
        self.env = load(src, "fotz_loyalty")
        self.g.fotz_loyalty = self.env
        cfg = config_values()
        ini = self.lua.eval("function(t) return { section_exist = function(self, s) return s == 'loyalty' end, "
                            "r_float_ex = function(self, s, k) return t[k] end } end")(self.lua.table_from(cfg))
        self.env.load_config(ini)

    def run(self, code):
        return self.lua.execute(code)

    def res(self):
        b = self.env.book()
        return b.res if b else None

    def v(self, id):
        e = self.res()[id]
        return None if e is None else e.v

    def news(self):
        return list(self.g.NEWS.values())

    def members(self):
        return sorted(self.g.fotz_faction.F.members.keys()) if self.g.fotz_faction.F else []


def fresh(src, *setup):
    w = World(src)
    w.run("found()")
    for code in setup:
        w.run(code)
    return w


def config(src):
    w = World(src)
    shipped = config_values()
    defaults = {k: float(v) for k, v in w.env.DEFAULTS.items()}
    check(shipped == defaults, "the shipped [loyalty] isn't the script's defaults: %s" %
          sorted(set(shipped.items()) ^ set(defaults.items())))


def start(src):
    w = fresh(src, 'camp(1, "Cordon Settlement", 50)',
              'settler(1, 10)',                                       # a Loner, as you were
              'settler(1, 11, { community = "dolg" })',
              'settler(1, 12, { community = "dolg", was_companion = true })',
              'settler(1, 13, { community = "freedom" })',
              'settler(1, 14, { community = "bandit" })',
              'REL["fotz_own>freedom"] = 1200; REL["fotz_own>bandit"] = -2000')
    w.env.look()
    got = [w.v(i) for i in (10, 11, 12, 13, 14)]
    check(got == [40, 30, 40, 45, 15], "start terms %s" % got)


def daily(src):
    w = fresh(src, 'camp(1, "A", 50)', 'camp(2, "B", 90)', 'camp(3, "C", 70)', 'camp(4, "D", 45)',
              'settler(1, 10, { community = "dolg" })',              # idle, comfort 50: +5
              'settler(1, 11, { community = "dolg", job = "guard" })',  # working: +8
              'settler(2, 20, { community = "dolg" })',              # comfort 90: +8
              'settler(3, 30, { community = "dolg" })',              # comfort 70: +7
              'settler(4, 40, { community = "dolg" })',              # comfort 45: +3
              'settler(1, 12, { community = "dolg", job = "companion" })')  # following you: idle
    w.env.look()
    base = {i: w.v(i) for i in (10, 11, 20, 30, 40, 12)}
    w.env.day("2026-11-02")
    got = {i: round(w.v(i) - base[i], 3) for i in base}
    check(got == {10: 5, 11: 8, 20: 8, 30: 7, 40: 3, 12: 5}, "the day's terms %s" % got)
    # your faction and theirs enemies, felt by tier: a Master (tier 3) twice a novice's
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "bandit" })',
              'settler(1, 11, { community = "bandit", tier = 3 })', 'settler(1, 12, { community = "freedom", tier = 3 })',
              'REL["fotz_own>bandit"] = -2000; REL["fotz_own>freedom"] = 1500')
    w.env.look()
    for i in (10, 11, 12):
        w.res()[i].v = 50
    w.env.day("2026-11-02")
    got = [round(w.v(i), 3) for i in (10, 11, 12)]
    check(got == [49, 43, 59], "relation terms with the tier's pull %s" % got)
    # two wars or more: -2, and a war between two other factions doesn't count
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })', 'WARS = 2; sync_wars()')
    w.env.look()
    w.res()[10].v = 50
    w.env.day("2026-11-02")
    check(w.v(10) == 53, "two wars: %s" % w.v(10))
    w.run("WARS = 1; sync_wars()")
    w.env.day("2026-11-03")
    check(w.v(10) == 58, "one war: %s" % w.v(10))


def sworn_near(src):
    w = fresh(src, 'camp(1, "A", 50)', 'camp(2, "B", 50)')
    for i in range(10, 16):
        w.run('settler(1, %d, { community = "dolg" })' % i)
    w.run('settler(2, 20, { community = "dolg" })')
    w.env.look()
    for i in (10, 11, 12, 13):
        w.res()[i].sworn = True
        w.res()[i].v = 100
    for i in (14, 15, 20):
        w.res()[i].v = 50
    w.env.day("2026-11-02")
    check(w.v(14) == 58 and w.v(15) == 58, "four sworn near, capped at three: %s %s" % (w.v(14), w.v(15)))
    check(w.v(20) == 55, "no sworn in camp B: %s" % w.v(20))
    check(w.v(10) == 100, "a sworn member stays at 100: %s" % w.v(10))
    # one sworn: not counting themselves
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })', 'settler(1, 11, { community = "dolg" })')
    w.env.look()
    w.res()[10].sworn, w.res()[10].v, w.res()[11].v = True, 100, 50
    w.env.day("2026-11-02")
    check(w.v(11) == 56 and w.v(10) == 100, "one sworn near: %s, the sworn %s" % (w.v(11), w.v(10)))


def events(src):
    w = fresh(src, 'camp(1, "A", 50)', 'S = settler(1, 10, { community = "dolg", tier = 0 })')
    w.env.look()
    w.res()[10].v = 40
    w.run("S.tier = 2")
    w.env.look()
    check(w.v(10) == 60, "two promotions at once: %s" % w.v(10))
    w.run("S.tier = 1")
    w.env.look()
    check(w.v(10) == 60, "a tier down costs nothing: %s" % w.v(10))
    w.run("S.bought_tier = 1")
    w.env.look()
    check(w.v(10) == 63, "a weapon bought: %s" % w.v(10))
    w.env.look()
    check(w.v(10) == 63, "the same weapon twice: %s" % w.v(10))
    w.run("S.bought_tier = nil")                 # re-created: Homestead clears it
    w.env.look()
    w.run("S.bought_tier = 1")
    w.env.look()
    check(w.v(10) == 66, "a weapon bought again after re-creation: %s" % w.v(10))
    w.run("S.on_expedition = true")
    w.env.look()
    w.run("S.on_expedition = nil")
    w.env.look()
    check(w.v(10) == 68, "back from an expedition: %s" % w.v(10))


def raids(src):
    w = fresh(src, 'camp(1, "A", 50)', 'camp(2, "B", 50)',
              'settler(1, 10, { community = "dolg" })', 'settler(1, 11, { community = "dolg", job = "guard" })',
              'settler(1, 12, { community = "dolg" })', 'settler(2, 20, { community = "dolg" })')
    w.env.look()
    for i in (10, 11, 12, 20):
        w.res()[i].v = 50
    w.res()[12].sworn = True
    w.run('CAMPS[1].active_raid = { squad_id = 500 }; squad(500, 3)')
    w.env.look()
    w.run('CAMPS[1].active_raid = nil; squad(500, 0)')
    w.env.look()
    check((w.v(10), w.v(11), w.v(12), w.v(20)) == (56, 60, 50, 50), "a raid beaten off: %s %s %s %s" %
          (w.v(10), w.v(11), w.v(12), w.v(20)))
    # you left the level: Homestead drops it with its raiders alive
    w.run('CAMPS[1].active_raid = { squad_id = 501 }; squad(501, 4)')
    w.env.look()
    w.run('CAMPS[1].active_raid = nil')
    w.env.look()
    check(w.v(10) == 56, "a raid left behind counted: %s" % w.v(10))


def deaths(src):
    w = fresh(src, 'camp(1, "A", 50)', 'camp(2, "B", 50)',
              'settler(1, 10, { community = "dolg" })', 'settler(1, 11, { community = "dolg" })',
              'settler(1, 12, { community = "dolg" })', 'settler(2, 20, { community = "dolg" })')
    w.env.look()
    for i in (10, 11, 12, 20):
        w.res()[i].v = 50
    w.res()[12].sworn = True
    # Homestead deletes the record as it dies
    w.run('CAMPS[1].survivors[10] = nil')
    w.env.npc_on_death_hook(w.lua.eval("victim(10)"))
    check((w.v(11), w.v(12), w.v(20)) == (46, 50, 50), "a campmate killed: %s %s %s" % (w.v(11), w.v(12), w.v(20)))
    check(w.res()[10] is not None and w.res()[10].dead, "the dead entry waits")
    w.env.look()
    check(w.res()[10] is not None, "the dead dropped before the day")
    w.env.day("2026-11-02")
    check(w.res()[10] is None, "the dead kept past the day")


def requests(src):
    w = fresh(src, 'camp(1, "Cordon Settlement", 50)', 'settler(1, 10, { community = "dolg", name = "Petro" })')
    w.env.look()
    w.res()[10].v = 66
    w.env.day("2026-11-02")                              # 71: asks
    e = w.res()[10]
    check(e.req == "2026-11-02" and len(w.news()) == 1 and "Petro" in w.news()[0] and "Cordon Settlement" in w.news()[0],
          "a request at 70: %s %s" % (e.req, w.news()))
    w.env.day("2026-11-02")
    check(len(w.news()) == 1, "asked twice: %s" % w.news())
    lists = w.env.page_lists()
    check(len(lists.requests) == 1 and lists.requests[1].id == 10 and len(lists.near) == 0, "the page's request")
    # withdrawn under 60 (54, and the day's +5)
    e.v = 54
    w.env.day("2026-11-03")
    check(e.req is None, "a request kept under 60")
    # asks again, then Accept
    e.v = 70
    w.env.day("2026-11-04")
    check(e.req == "2026-11-04", "no new request: %s" % e.req)
    check(w.env.accept(10) is True and w.members() == [10] and e.req is None, "Accept didn't join")
    check("Petro" in w.news()[-1] and "Wolves" in w.news()[-1], "the joined news %s" % w.news()[-1])
    check(w.env.accept(10) is False, "accepted twice")
    # Decline: -10 and three days without asking
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })')
    w.env.look()
    w.res()[10].v = 70
    w.run('DATE = "2026-11-02"')
    w.env.day("2026-11-02")
    e = w.res()[10]
    v = e.v
    check(e.req and w.env.decline(10) is True and e.req is None and e.v == v - 10, "Decline: %s -> %s" % (v, e.v))
    for d, want in (("2026-11-03", None), ("2026-11-04", None), ("2026-11-05", "2026-11-05")):
        w.run('DATE = "%s"' % d)
        e.v = 75
        w.env.day(d)
        check(e.req == want, "%s: request %s, wanted %s" % (d, e.req, want))
    # Accept join requests: joined at once, nothing waits
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })', 'MCM["fotz/loyalty_accept"] = true')
    w.env.look()
    w.res()[10].v = 70
    w.env.day("2026-11-02")
    check(w.members() == [10] and w.res()[10].req is None and len(w.env.page_lists().requests) == 0,
          "accept-all: members %s" % w.members())


def leaving(src):
    w = fresh(src, 'camp(1, "A", 30)', 'settler(1, 10, { community = "bandit", name = "Petro" })',
              'settler(1, 11, { community = "bandit" })', 'REL["fotz_own>bandit"] = -2000')
    w.env.look()
    w.g.fotz_faction.F.members[10] = w.lua.eval('{ mother = "bandit", name = "Petro", via = "settler", joined = "2026-11-01" }')
    w.g.fotz_faction.F.members[11] = w.lua.eval('{ mother = "bandit", name = "n11", via = "companion", joined = "2026-11-01" }')
    w.res()[10].v, w.res()[11].v = 31, 31
    w.env.day("2026-11-02")                              # +5 -6 -2 = -3: 28
    check(w.members() == [11] and list(w.g.LEFT.values()) == [10], "under 30: members %s" % w.members())
    check("Petro" in w.news()[-1] and "F:bandit" in w.news()[-1], "the left news %s" % w.news()[-1:])
    check(w.res()[10] is not None, "a settler member who left the faction lost their resident's entry")


def swearing(src):
    def case(tier, v, joined, today="2026-11-20"):
        w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg", tier = %d })' % tier)
        w.env.look()
        w.g.fotz_faction.F.members[10] = w.lua.eval('{ mother = "dolg", name = "n10", via = "settler", joined = "%s" }' % joined)
        e = w.res()[10]
        e.tier, e.v = tier, v
        w.env.day(today)
        return w, e
    w, e = case(3, 100, "2026-11-06")
    check(e.sworn and "n10" in w.news()[-1], "a Master at 100 after 14 days not sworn")
    for tier, v, joined in ((2, 100, "2026-11-06"), (3, 92, "2026-11-06"), (3, 100, "2026-11-07")):
        w, e = case(tier, v, joined)
        check(not e.sworn, "sworn with tier %s, loyalty %s, joined %s" % (tier, v, joined))
    # sworn: their loyalty doesn't move, and they never leave over it
    w, e = case(3, 100, "2026-11-06")
    w.run('REL["fotz_own>dolg"] = -3000; WARS = 3; sync_wars()')
    for d in ("2026-11-21", "2026-11-22", "2026-11-23"):
        w.env.day(d)
    check(e.v == 100 and w.members() == [10], "the sworn moved: %s, members %s" % (e.v, w.members()))


def residency(src):
    # a member who stops being a resident of a standing camp leaves, unless they follow you
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })', 'settler(1, 11, { community = "dolg" })',
              'settler(1, 12, { community = "dolg" })')
    w.env.look()
    for i in (10, 11):
        w.g.fotz_faction.F.members[i] = w.lua.eval('{ mother = "dolg", name = "n%d", via = "settler", joined = "2026-11-01" }' % i)
    w.run('COMPANIONS[11] = true; CAMPS[1].survivors[10] = nil; CAMPS[1].survivors[11] = nil; CAMPS[1].survivors[12] = nil')
    w.env.look()
    check(w.members() == [11] and w.g.fotz_faction.F.members[11].via == "companion", "left the camp: members %s" % w.members())
    check(w.res()[10] is None and w.res()[11] is None and w.res()[12] is None, "entries kept after leaving")
    check(not w.env.resident(10), "still a resident")
    # a fallen camp: the sworn stay members between camps, others go back, the rest are forgotten
    w = fresh(src, 'camp(1, "A", 50)', 'camp(2, "B", 50)')
    for i in (10, 11, 12):
        w.run('settler(1, %d, { community = "dolg" })' % i)
    w.run('settler(2, 20, { community = "dolg" })')
    w.env.look()
    for i in (10, 11):
        w.g.fotz_faction.F.members[i] = w.lua.eval('{ mother = "dolg", name = "n%d", via = "settler", joined = "2026-11-01" }' % i)
    w.res()[10].sworn = True
    w.run("CAMPS[1] = nil")
    w.env.look()
    check(w.members() == [10] and w.res()[10] is not None and w.res()[10].hub is None, "the sworn after the fall: %s" % w.members())
    check(w.res()[11] is None and w.res()[12] is None and w.res()[20] is not None, "the others after the fall")
    lists = w.env.page_lists()
    check(len(lists.members) == 1 and lists.members[1].camp is None and lists.members[1].sworn, "the page between camps")


def relinking(src):
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg", name = "Petro" })',
              'settler(1, 11, { community = "dolg", name = "Ivan" })')
    w.env.look()
    w.g.fotz_faction.F.members[10] = w.lua.eval('{ mother = "dolg", name = "Petro", via = "settler", joined = "2026-11-01" }')
    w.res()[10].v = 77
    # Homestead re-creates Petro under a new id, with another section, the same record
    w.run('local r = CAMPS[1].survivors[10]; CAMPS[1].survivors[10] = nil; r.section = "sim_default_stalker_0"; '
          'CAMPS[1].survivors[40] = r')
    w.env.look()
    check(w.res()[10] is None and w.res()[40] is not None and w.v(40) == 77, "the entry didn't follow the new id")
    check(w.members() == [40] and list(w.g.RELINKED.values()) == ["10>40"], "the membership: %s" % w.members())
    check(len(w.g.LEFT) == 0 and w.res()[11].v != 77, "someone left, or Ivan took Petro's entry")


def census_flow(src):
    w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })')
    w.env.on_census_hook(w.lua.eval('{ date = "2026-11-01 08:00" }'))
    v0 = w.v(10)
    check(v0 == 30 and w.env.book().day == "2026-11-01", "the first census: %s, day %s" % (v0, w.env.book().day))
    w.env.on_census_hook(w.lua.eval('{ date = "2026-11-01 20:00" }'))
    check(w.v(10) == 30, "the same day counted twice")
    w.env.on_census_hook(w.lua.eval('{ date = "2026-11-02 08:00" }'))
    check(w.v(10) == 35, "the next day: %s" % w.v(10))


def switched_off(src):
    for setup in ('MCM["fotz/loyalty"] = false', 'stalker_camp_builder = nil', 'fotz_faction.F = nil'):
        w = fresh(src, 'camp(1, "A", 50)', 'settler(1, 10, { community = "dolg" })', setup)
        check(not w.env.enabled(), "enabled with %s" % setup)
        w.env.on_census_hook(w.lua.eval('{ date = "2026-11-02 08:00" }'))
        b = w.env.book()
        check(b is None or len(b.res) == 0, "ran with %s" % setup)
        lists = w.env.page_lists()
        check(len(lists.requests) == 0 and len(lists.members) == 0 and len(lists.near) == 0, "listed with %s" % setup)


def near_list(src):
    w = fresh(src, 'camp(1, "A", 50)')
    cast = (("Max", 20), ("Zed", 64), ("Abe", 64), ("Kim", 69))
    for i, (name, v) in enumerate(cast, start=10):
        w.run('settler(1, %d, { community = "dolg", name = "%s" })' % (i, name))
    w.env.look()
    for i, (name, v) in enumerate(cast, start=10):
        w.res()[i].v = v
    names = [it.name for it in w.env.page_lists().near.values()]
    check(names == ["Kim", "Abe", "Zed", "Max"], "nearest to asking first: %s" % names)


#: camp A (hub 1, Cordon) falls; B (hub 2, Garbage) has room; smarts near B and far from it
BETWEEN = """
placed(1, "A", "l01_escape", 0, 0)
placed(2, "B", "l02_garbage", 100, 100)
smart("gar_near", 2, 160, 100)
smart("gar_far", 2, 500, 500)
smart("esc_near", 1, 101, 100)
ROOM[2] = true
for _, id in ipairs({ 10, 11, 12, 13 }) do settler(1, id, { community = "dolg" }); npc(id) end
"""


def members_of(w, ids, via="settler"):
    for i in ids:
        w.g.fotz_faction.F.members[i] = w.lua.eval('{ mother = "dolg", name = "n%d", via = "%s", joined = "2026-11-01" }' % (i, via))


def fallen(w):
    """A falls: 10 sworn (at 50, as under a sworn_loyalty of 50), 11 and 12 members at 70 and 60,
    13 a resident; the draw 0.65."""
    w.env.look()
    members_of(w, (10, 11, 12))
    w.res()[10].sworn, w.res()[10].v = True, 50
    w.res()[11].v, w.res()[12].v = 70, 60
    w.run("RANDOM = 0.65; CAMPS[1] = nil")
    w.env.look()


def between(src):
    # the sworn stay, a member at 70 stays (0.65 < 0.70), one at 60 doesn't, the resident is forgotten
    w = fresh(src, BETWEEN)
    fallen(w)
    r = w.res()
    check(w.members() == [10, 11] and list(w.g.LEFT.values()) == [12], "after the fall: members %s" % w.members())
    check(r[12] is None and r[13] is None, "a member who went back, or the resident, kept")
    for i in (10, 11):
        check(r[i] and r[i].hub is None and r[i].trip and r[i].trip.hub == 2 and r[i].trip.smart == "gar_near",
              "%d's trip: %s" % (i, r[i] and r[i].trip and (r[i].trip.hub, r[i].trip.smart)))
        check(w.g.SQUAD_OF[i].scripted_target == "gar_near", "%d's squad: %s" % (i, w.g.SQUAD_OF[i].scripted_target))
    check(set(w.g.ASKED_FOR.values()) == {"fotz_own"}, "camps asked for %s" % list(w.g.ASKED_FOR.values()))
    news = w.news()
    check(any("n12" in n and "A" in n and "F:dolg" in n for n in news), "the news of the one who went back: %s" % news)
    check(sum("B" in n and ("n10" in n or "n11" in n) for n in news) == 2, "the news of the trips: %s" % news)
    heading = {it.id: it.heading for it in w.env.page_lists().members.values()}
    check(heading == {10: "B", 11: "B"}, "the page's trips %s" % heading)
    # not there yet: far from B's flag, or on another level
    w.run('LEVEL = "l02_garbage"; online(11, 300, 300)')
    w.env.look()
    w.run('LEVEL = "l01_escape"; online(11, 102, 100)')
    w.env.look()
    check(len(w.g.RECRUITED) == 0 and r[11].trip, "moved in while away: %s" % list(w.g.RECRUITED.values()))
    # there, at the smart the squad heads for (60 m from B's flag): B takes 11 in, through
    # Homestead's own recruitment, and the squad is let go
    w.run('LEVEL = "l02_garbage"; online(11, 158, 100); ACCEPT[2] = true')
    w.env.look()
    check(list(w.g.RECRUITED.values()) == ["11>2"] and r[11].hub == 2 and r[11].trip is None,
          "the arrival: %s, hub %s" % (list(w.g.RECRUITED.values()), r[11].hub))
    check(w.g.SQUAD_OF[11].scripted_target is None and "n11" in w.news()[-1] and "B" in w.news()[-1],
          "after the arrival: target %s, news %s" % (w.g.SQUAD_OF[11].scripted_target, w.news()[-1]))
    check(w.members() == [10, 11] and r[11].v == 70, "the member after moving in: %s, %s" % (w.members(), r[11].v))


def turned_away(src):
    # B turns them away: the sworn wait, and look again each day; one not sworn goes back
    w = fresh(src, BETWEEN)
    fallen(w)
    r = w.res()
    w.run('LEVEL = "l02_garbage"; online(10, 104, 100); online(11, 106, 100)')
    w.env.look()
    check(set(w.g.RECRUITED.values()) == {"10>2", "11>2"}, "asked %s" % list(w.g.RECRUITED.values()))
    check(r[10] and r[10].trip is None and r[10].hub is None and w.members() == [10], "the sworn turned away: %s" % w.members())
    check(r[11] is None and 11 in list(w.g.LEFT.values()), "one not sworn, turned away, kept")
    w.env.look()
    check(r[10].trip is None, "set out again for the camp that turned them away")
    w.env.day("2026-11-02")
    check(r[10].trip and r[10].trip.hub == 2, "the sworn didn't look again the next day")
    # the camp they head for falls too: the next one with room
    w.run('placed(3, "C", "l03_agroprom", 0, 0); smart("agr_near", 3, 5, 0); ROOM[3] = true; CAMPS[2] = nil')
    w.env.look()
    check(r[10].trip and r[10].trip.hub == 3 and w.g.SQUAD_OF[10].scripted_target == "agr_near",
          "after B fell too: %s" % (r[10].trip and r[10].trip.hub))


def nowhere_to_go(src):
    # no camp with room when A falls: the sworn wait, a member who stayed on the roll goes back
    w = fresh(src, BETWEEN, "ROOM = {}")
    fallen(w)
    r = w.res()
    check(w.members() == [10] and r[10].trip is None and r[10].hub is None, "no room: members %s" % w.members())
    check(sorted(w.g.LEFT.values()) == [11, 12], "left %s" % sorted(w.g.LEFT.values()))
    lists = w.env.page_lists()
    check(len(lists.members) == 1 and lists.members[1].heading is None and lists.members[1].camp is None, "the page")
    # a member who follows you stays one, as a companion
    w = fresh(src, BETWEEN, "COMPANIONS[11] = true")
    fallen(w)
    check(11 in w.members() and w.g.fotz_faction.F.members[11].via == "companion" and w.res()[11] is None,
          "a companion member after the fall: %s" % w.members())


def enemy_smart(src):
    # the smart nearest B's flag held by an enemy of yours: the trip goes to the nearest with none,
    # as run 20 showed (a camp at a Renegade post, both members shot on the way in)
    near = 'smart("gar_held", 2, 105, 100); '
    cases = [
        ('held("gar_held", "renegade"); REL["fotz_own>renegade"] = -2000', "gar_near", "past the Renegades"),
        ('held("gar_held", "monster", "monster_predatory_day")', "gar_near", "past mutants"),
        ('held("gar_held", "zombied"); REL["fotz_own>zombied"] = -5000', "gar_near", "past the Zombied"),
        ('held("gar_held", "freedom"); REL["fotz_own>freedom"] = -999', "gar_held", "a squad not at war isn't an enemy"),
        ('held("gar_held", "trader"); REL["fotz_own>trader"] = -2000', "gar_held",
         "a community outside the census's factions isn't one"),
        # every smart within 300 m an enemy's: the nearest after all, not gar_far, 566 m out
        ('held("gar_held", "renegade"); held("gar_near", "bandit"); REL["fotz_own>renegade"] = -2000; '
         'REL["fotz_own>bandit"] = -1000', "gar_held", "no smart near without enemies"),
    ]
    for setup, want, what in cases:
        w = fresh(src, BETWEEN, near + setup)
        fallen(w)
        r = w.res()
        for i in (10, 11):
            got = r[i] and r[i].trip and r[i].trip.smart
            check(got == want and w.g.SQUAD_OF[i].scripted_target == want, "%s: %d heads for %s" % (what, i, got))


def strings(src):
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    want = set(re.findall(r'"(st_fotz_\w+)"', src))
    check(want and want <= have, "missing: %s" % sorted(want - have))


def run(src):
    for t in (config, start, daily, sworn_near, events, raids, deaths, requests, leaving, swearing, residency,
              relinking, census_flow, switched_off, near_list, between, turned_away, nowhere_to_go, enemy_smart,
              strings):
        t(src)
    return "20 scenarios"


def expose(src):
    """The script's local callbacks, reachable for the test: the census listener and the death."""
    return src + "\nnpc_on_death_hook = npc_on_death_callback\non_census_hook = on_census\n"


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
        print("ok: " + run(expose(src)))
        return 0
    except Fail as e:
        print("FAIL: %s" % e)
        return 1
    except Exception as e:
        print("FAIL (error): %s: %s" % (type(e).__name__, " | ".join(str(e).splitlines())))
        return 1


if __name__ == "__main__":
    sys.exit(main())
