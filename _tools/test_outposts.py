"""Run fotz_outposts.script under LuaJIT 2.0 against a stand-in for Homestead's rival outposts (their
garrisons' squads, ranks and goodwill), the faction you lead, settler loyalty's trips and the
game's news, and check beaten outposts.

Checked: the shipped config's [outposts] section is the script's defaults; the chances by rank,
never under 0; the fight: only an outpost of a faction at war with you (at -1000 too), held, not
mutants or the Zombied, on your level, within reach; its top kept while you're there and raised
by reinforcements, forgotten when you leave; the roll at the share of the top or fewer, the last
one always, never before a loss, once a fight; the survivors' average rank; defection (each joins,
leaves the garrison for a squad of their own and sets out at the defector's loyalty; one with no
trip leaves again) and its fallbacks to surrender (no faction, loyalty off, no room); surrender (a
ceasefire to a time from the draw, each one's attitude toward you and your companions, both ways,
brought to 0, a pair not at war left alone, the old goodwill kept once); the ceasefire held, over
at its time, broken by your hit and no one else's, gone with its outpost; the old goodwill back
offline; the save keeping the old goodwill and the next update applying the ceasefire again; a
save of another version set aside; switched off, every ceasefire ends; the strings exist.

    python test_outposts.py            the real script
    python test_outposts.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(HERE, "..", "gamedata")
SCRIPT = os.path.join(GD, "scripts", "fotz_outposts.script")
CONFIG = os.path.join(GD, "configs", "plugins", "fotz_politics.ltx")
ENG = os.path.join(GD, "configs", "text", "eng", "st_fotz.xml")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "no_war_check": ("    return relation_registry.community_relation(f, db.actor:character_community()) <= ENEMIES",
                     "    return true"),
    "war_line_strict": ("db.actor:character_community()) <= ENEMIES", "db.actor:character_community()) < ENEMIES"),
    "mutants_fought": ('    if camp.status or not f or f == "monster" or f == "zombied" then',
                       "    if camp.status or not f then"),
    "held_ignored": ('    if camp.status or not f or', "    if not f or"),
    "near_unlimited": ("vector():set(camp.position.x, camp.position.y, camp.position.z)) <= cfg.near then",
                       "vector():set(camp.position.x, camp.position.y, camp.position.z)) <= 99999 then"),
    "any_level": ("camp.level == lvl and camp.position", "camp.position"),
    "fight_not_forgotten": ("        if not here[key] then\n            FIGHTS[key] = nil\n",
                            "        if not here[key] then\n"),
    "rolls_twice": ("    if f.rolled or #alive == 0", "    if #alive == 0"),
    "no_loss_needed": ("or #alive == f.top or", "or"),
    "last_not_always": ("#alive > math.max(1, f.top * cfg.broken)", "#alive > f.top * cfg.broken"),
    "broken_ignored": ("#alive > math.max(1, f.top * cfg.broken)", "#alive > f.top"),
    "top_not_kept": ("    f.top = math.max(f.top, #alive)\n", ""),
    "rank_ignored": ("        sum = sum + rank_of(se)", "        sum = sum + 0"),
    "defect_inverted": ("    if x < d then", "    if x >= d then"),
    "surrender_band": ("    elseif x < d + s then", "    elseif x < s then"),
    "chance_floor": ("    return math.max(0, cfg.defect_novice - cfg.defect_step * rank),",
                     "    return cfg.defect_novice - cfg.defect_step * rank,"),
    "no_fallback": ("        return defect(key, camp, alive) or surrender(key, camp, alive)",
                    '        return defect(key, camp, alive) or "fought on"'),
    "room_ignored": ("    if not (F and L and L.enabled() and L.has_room()) then",
                     "    if not (F and L and L.enabled()) then"),
    "loyalty_off_ignored": ("    if not (F and L and L.enabled() and L.has_room()) then",
                            "    if not (F and L and L.has_room()) then"),
    "no_release": ("            sb.release_npc_from_squad_and_smart(id)\n", ""),
    "no_reassign": ("            sb.reassign_freed_settler_to_smart(id)\n", ""),
    "stray_kept": ('                fotz_faction.leave(id, "no camp to go to")\n', ""),
    "defector_loyalty_ignored": ("L.take_in(id, name, cfg.defector_loyalty)", "L.take_in(id, name, 30)"),
    "hold_fire_any": ("    if g <= ENEMIES then\n        local old = a:goodwill(b)", "    if true then\n        local old = a:goodwill(b)"),
    "no_companions": ("            for _, c in ipairs(comps) do", "            for _, c in ipairs({}) do"),
    "one_way": ("local them, us = hold_fire(npc, c), hold_fire(c, npc)", "local them, us = hold_fire(npc, c), nil"),
    "pairs_always": ("                if p[1] ~= nil or p[2] ~= nil then\n                    t.pairs[k] = p\n                end",
                     "                t.pairs[k] = p"),
    "restore_unchanged": ("        if olds[1] ~= nil then\n            set_back(a, b, olds[1])\n        end",
                          "        set_back(a, b, olds[1] or 0)"),
    "old_overwritten": ("            if old == false then\n                t.npcs[id] = npc:goodwill(actor)\n            end",
                        "            t.npcs[id] = npc:goodwill(actor)"),
    "truce_endless": ("        elseif now >= t.ends then", "        elseif false then"),
    "hours_fixed": ("math.random(cfg.truce_days_min * 24, cfg.truce_days_max * 24)", "cfg.truce_days_min * 24"),
    "gone_kept": ('        if type(camp) ~= "table" or camp.status or camp.faction ~= t.faction then',
                  '        if type(camp) ~= "table" then'),
    "hit_by_anyone": ("    if not (who and who:id() == 0) then", "    if not who then"),
    "save_keeps_truce": ('    for _, t in pairs(T.truces) do\n        guarded("restore", restore, t)\n    end\n    again = true',
                         "    again = true"),
    "not_again": ("    again = true\n    m_data.fotz_outposts = T", "    m_data.fotz_outposts = T"),
    "load_any_version": ('    if type(d) == "table" and d.v == SAVE_VERSION then', '    if type(d) == "table" then'),
    "off_keeps_truces": ("    elseif next(T.truces) then", "    elseif false then"),
    "offline_not_restored": ("    if se and se.force_set_goodwill and se:alive() then", "    if false then"),
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
NOW = "2026-11-01 12:00"
fotz_census = { game_date = function() return NOW end }
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
fotz_politics = {
    day_num = day_num, day_str = day_str,
    faction_name = function(f) return "F:" .. tostring(f) end,
    news_level = function() return "events" end,
}
NEWS = {}
news_manager = { send_tip = function(actor, text) NEWS[#NEWS + 1] = text end }
MCM = {}
ui_mcm = { get = function(id) return MCM[id] end }
TIME = 0
function time_global() return TIME end
RANDOM = 0.5
math.random = function(a, b)
    if a then return math.floor(a + (b - a) * RANDOM + 0.5) end
    return RANDOM
end

-- relations: a faction toward a community; goodwill: personal ("a>b", by ids) and the rest of the
-- attitude (community terms, rank, reputation), which general_goodwill adds
REL, GW, ATT, DEAD = {}, {}, {}, {}
relation_registry = { community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end }
local function pos(x, y, z)
    return { x = x, y = y, z = z, distance_to = function(self, o)
        return math.sqrt((self.x - o.x) ^ 2 + (self.y - o.y) ^ 2 + (self.z - o.z) ^ 2) end }
end
function vector() return { set = function(self, x, y, z) return pos(x, y, z) end } end
ME = pos(0, 0, 0)
ACTOR_COMM = "actor_stalker"
function obj(id, comm)
    return {
        id = function() return id end,
        alive = function() return not DEAD[id] end,
        character_name = function() return "n" .. id end,
        character_community = function() return comm end,
        position = function() return ME end,
        goodwill = function(self, who) return GW[id .. ">" .. who:id()] or 0 end,
        general_goodwill = function(self, who)
            local k = id .. ">" .. who:id()
            return (GW[k] or 0) + (ATT[k] or 0)
        end,
        force_set_goodwill = function(self, v, who) GW[id .. ">" .. who:id()] = v end,
    }
end
db = { actor = obj(0, "actor_stalker") }
db.actor.character_community = function() return ACTOR_COMM end
LEVEL = "l01_escape"
ONLINE = {}
level = { name = function() return LEVEL end,
          object_by_id = function(id) if id == 0 then return db.actor end return ONLINE[id] end }

-- the alife: NPCs' server objects (rank, goodwill offline) and squads
SE, SQUADS = {}, {}
function se_npc(id, rank)
    SE[id] = { id = id, rank = rank, alive = function() return not DEAD[id] end,
               force_set_goodwill = function(self, v, who_id) GW[id .. ">" .. who_id] = v end }
    return SE[id]
end
ranks = { get_se_obj_rank_name = function(se) return se.rank end }
function squad(id, ids, comm)
    local sq = { id = id, comm = comm, members = ids }
    sq.squad_members = function(self)
        local i = 0
        return function()
            i = i + 1
            local m = self.members[i]
            if m then return { id = m, object = SE[m] } end
        end
    end
    SQUADS[id] = sq
    return sq
end
SIM = { object = function(self, id) return SQUADS[id] or SE[id] end }
function alife() return SIM end

-- Homestead: the outposts and what Factions calls on it
RELEASED, REASSIGNED = {}, {}
stalker_camp_builder = {
    rival_camps = {},
    is_valid_camp_squad = function(camp, sq) return sq.comm == camp.faction end,
    release_npc_from_squad_and_smart = function(id)
        RELEASED[#RELEASED + 1] = id
        for _, sq in pairs(SQUADS) do
            for i, m in ipairs(sq.members) do
                if m == id then table.remove(sq.members, i) break end
            end
        end
    end,
    reassign_freed_settler_to_smart = function(id) REASSIGNED[#REASSIGNED + 1] = id end,
}
NEXT_ID = 100
-- an outpost of a faction, its garrison of these ranks in one squad, online, its attitude toward
-- you the faction's (REL)
function garrison(key, faction, x, z, list, lvl)
    local ids = {}
    for _, r in ipairs(list) do
        local id = NEXT_ID
        NEXT_ID = NEXT_ID + 1
        se_npc(id, r)
        ONLINE[id] = obj(id, faction)
        ATT[id .. ">0"] = REL[faction .. ">" .. ACTOR_COMM] or 0
        ids[#ids + 1] = id
    end
    local sq = NEXT_ID
    NEXT_ID = NEXT_ID + 1
    squad(sq, ids, faction)
    stalker_camp_builder.rival_camps[key] = { faction = faction, name = "O:" .. key, level = lvl or "l01_escape",
                                              position = { x = x, y = 0, z = z }, squad_id = sq, extra_squad_ids = {} }
    return ids
end
-- one more fighter in an outpost's squad (a reinforcement)
function reinforce(key, rank)
    local camp = stalker_camp_builder.rival_camps[key]
    local id = NEXT_ID
    NEXT_ID = NEXT_ID + 1
    se_npc(id, rank)
    ONLINE[id] = obj(id, camp.faction)
    table.insert(SQUADS[camp.squad_id].members, id)
    return id
end
function kill(id) DEAD[id] = true end

-- your faction and settler loyalty's trips
JOINED, LEFT, TAKEN, TAKE_FAIL = {}, {}, {}, {}
ROOM, LOYALTY_ON = true, true
fotz_faction = {
    F = nil,
    join_settler = function(id)
        local F = fotz_faction.F
        if not F or F.members[id] then return false end
        F.members[id] = { via = "settler" }
        JOINED[#JOINED + 1] = id
        return true
    end,
    leave = function(id) fotz_faction.F.members[id] = nil LEFT[#LEFT + 1] = id end,
}
function found() fotz_faction.F = { name = "Wolves", members = {} } end
fotz_loyalty = {
    enabled = function() return LOYALTY_ON and fotz_faction.F ~= nil end,
    has_room = function() return ROOM end,
    take_in = function(id, name, v)
        if not ROOM or TAKE_FAIL[id] then return false end
        TAKEN[id] = { name = name, v = v }
        return true
    end,
}
axr_companions = { companion_squads = {} }
-- a companion following you, at war with the garrison both ways (ATT set by the test)
function companion(id)
    ONLINE[id] = obj(id, "stalker")
    se_npc(id, "veteran")
    squad(id + 1, { id }, "stalker")
    axr_companions.companion_squads[id + 1] = true
end
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def config_values():
    """The shipped [outposts] section, key -> number."""
    text = open(CONFIG, encoding="cp1251").read()
    body = text.split("[outposts]", 1)[1]
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
        self.env = load(src, "fotz_outposts")
        self.g.fotz_outposts = self.env
        ini = self.lua.eval("function(t) return { section_exist = function(self, s) return s == 'outposts' end, "
                            "r_float_ex = function(self, s, k) return t[k] end } end")(self.lua.table_from(config_values()))
        self.env.load_config(ini)

    def run(self, code):
        return self.lua.execute(code)

    def ev(self, code):
        return self.lua.eval(code)

    def look(self):
        self.env.look()

    def news(self):
        return list(self.g.NEWS.values())

    def beaten(self):
        return [m for m in self.g.LOG.values() if " beaten: " in m]

    def truce(self, key="A"):
        return self.env.T.truces[key]

    def att(self, a, b):
        """a's whole attitude toward b, as general_goodwill gives it"""
        return self.ev("(GW['%s>%s'] or 0) + (ATT['%s>%s'] or 0)" % (a, b, a, b))


def fresh(src, *setup):
    w = World(src)
    w.run('REL["bandit>actor_stalker"] = -2000')
    for code in setup:
        w.run(code)
    return w


def ids(w, code):
    return list(w.ev(code).values())


def config(src):
    w = World(src)
    shipped = config_values()
    defaults = {k: float(v) for k, v in w.env.DEFAULTS.items()}
    check(shipped == defaults, "the shipped [outposts] isn't the script's defaults: %s vs %s" % (shipped, defaults))


def chances(src):
    w = World(src)
    for rank, want in ((0, (30, 50)), (4, (14, 22)), (7, (2, 1)), (10, (0, 0)), (2, (22, 36))):
        got = w.env.chances(rank)
        check(tuple(got) == want, "chances at rank %s: %s, not %s" % (rank, got, want))


def fight(src):
    # five novices 100 m off; the draw 0.99: they fight on, so the trigger shows alone
    w = fresh(src, "RANDOM = 0.99")
    g = ids(w, 'garrison("A", "bandit", 100, 0, { "novice", "novice", "novice", "novice", "novice" })')
    w.look()
    check(w.env.FIGHTS.A and w.env.FIGHTS.A.top == 5 and not w.beaten(), "the fight's start")
    w.run("kill(%d); kill(%d)" % (g[0], g[1]))
    w.look()
    check(not w.beaten(), "3 of 5 rolled")
    w.run("kill(%d)" % g[2])
    w.look()
    check(len(w.beaten()) == 1 and "2 of 5 left" in w.beaten()[0] and w.env.FIGHTS.A.rolled == "fought on",
          "2 of 5: %s" % w.beaten())
    w.run("kill(%d)" % g[3])
    w.look()
    check(len(w.beaten()) == 1, "rolled again in the same fight")
    # away and back: a new fight, its top the one left, so not before another loss
    w.run("ME = vector():set(300, 0, 0)")
    w.look()
    check(w.env.FIGHTS.A is None, "the fight not forgotten when you left")
    w.run("ME = vector():set(0, 0, 0); n = reinforce('A', 'novice')")
    w.look()
    check(len(w.beaten()) == 1 and w.env.FIGHTS.A.top == 2, "back: %s, top %s" % (w.beaten(), w.env.FIGHTS.A.top))
    w.run("kill(n)")
    w.look()
    check(len(w.beaten()) == 2 and "1 of 2 left" in w.beaten()[1], "the new fight's roll: %s" % w.beaten())
    # reinforced in the fight: the top rises with it
    w = fresh(src, "RANDOM = 0.99")
    g = ids(w, 'garrison("A", "bandit", 100, 0, { "novice", "novice", "novice" })')
    w.look()
    w.run("reinforce('A', 'novice'); reinforce('A', 'novice')")
    w.look()
    w.run("kill(%d); kill(%d); kill(%d)" % tuple(g))
    w.look()
    check(w.env.FIGHTS.A.top == 5 and len(w.beaten()) == 1 and "2 of 5 left" in w.beaten()[0],
          "reinforced: top %s, %s" % (w.env.FIGHTS.A.top, w.beaten()))
    # two men: one down leaves the last, who rolls; one man alone never rolls unharmed
    w = fresh(src, "RANDOM = 0.99")
    g = ids(w, 'garrison("A", "bandit", 100, 0, { "novice", "novice" })')
    ids(w, 'garrison("B", "bandit", -100, 0, { "novice" })')
    w.look()
    w.run("kill(%d)" % g[0])
    w.look()
    w.look()
    check(len(w.beaten()) == 1 and "1 of 2 left" in w.beaten()[0], "two men: %s" % w.beaten())
    # outposts that never fight
    w = fresh(src, "RANDOM = 0.99", 'REL["dolg>actor_stalker"] = -999; REL["killer>actor_stalker"] = -1000')
    for setup in ('garrison("far", "bandit", 151, 0, { "novice", "novice" })',
                  'garrison("away", "bandit", 50, 0, { "novice", "novice" }, "l02_garbage")',
                  'garrison("calm", "dolg", 0, 50, { "novice", "novice" })',
                  'garrison("beasts", "monster", 0, 60, { "novice", "novice" })',
                  'garrison("dead", "zombied", 0, 70, { "novice", "novice" })',
                  'garrison("empty", "bandit", 0, 80, { "novice", "novice" }); '
                  'stalker_camp_builder.rival_camps.empty.status = "unoccupied"',
                  'garrison("war", "killer", 0, 90, { "novice", "novice" })'):
        w.run("REL['zombied>actor_stalker'] = -5000; REL['monster>actor_stalker'] = -5000; " + setup)
    w.look()
    seen = sorted(k for k in w.env.FIGHTS.keys())
    check(seen == ["war"], "fights at %s, not only the one at war at -1000" % seen)


def ranks(src):
    # a veteran and a novice left of five: rank 2, defection 22, surrender 36
    for draw, want in ((0.21, "defected"), (0.22, "surrendered"), (0.57, "surrendered"), (0.59, "fought on")):
        w = fresh(src, "found()", "RANDOM = %s" % draw)
        g = ids(w, 'garrison("A", "bandit", 100, 0, { "veteran", "novice", "expert", "expert", "expert" })')
        w.look()
        w.run("kill(%d); kill(%d); kill(%d)" % (g[2], g[3], g[4]))
        w.look()
        check(w.env.FIGHTS.A.rolled == want and "rank 2.0" in w.beaten()[0],
              "drew %s: %s, %s" % (draw, w.env.FIGHTS.A.rolled, w.beaten()))


def beaten_two(w, draw, comp=False):
    """five novices 100 m off, three killed: the two left roll at the draw"""
    w.run("RANDOM = %s" % draw)
    g = ids(w, 'garrison("A", "bandit", 100, 0, { "novice", "novice", "novice", "novice", "novice" })')
    if comp:
        w.run("companion(900)")
        for i in g:
            w.run("ATT['900>%d'] = -3000; ATT['%d>900'] = -3000" % (i, i))
    w.look()
    w.run("kill(%d); kill(%d); kill(%d)" % (g[0], g[1], g[2]))
    w.look()
    return g[3], g[4]


def defection(src):
    w = fresh(src, "found()")
    a, b = beaten_two(w, 0.1)
    check(w.env.FIGHTS.A.rolled == "defected", "the roll: %s" % w.env.FIGHTS.A.rolled)
    check(ids(w, "JOINED") == [a, b] and ids(w, "RELEASED") == [a, b] and ids(w, "REASSIGNED") == [a, b],
          "joined %s, released %s, reassigned %s" % (ids(w, "JOINED"), ids(w, "RELEASED"), ids(w, "REASSIGNED")))
    taken = w.g.TAKEN
    check(taken[a] and taken[a].v == 50 and taken[a].name == "n%d" % a and taken[b], "the trips: %s" % dict(taken))
    alive = w.ev("(function() local n = 0 for _, m in ipairs(SQUADS[stalker_camp_builder.rival_camps.A.squad_id].members) "
                 "do if not DEAD[m] then n = n + 1 end end return n end)()")
    check(alive == 0, "the garrison not left empty: %s alive" % alive)
    check(w.news() == ["F:bandit at O:A have come over to Wolves."], "the news: %s" % w.news())
    check(w.env.T.truces.A is None, "a truce as well")
    # one with no trip after all goes back
    w = fresh(src, "found()", "TAKE_FAIL[104] = true")
    a, b = beaten_two(w, 0.1)
    check(ids(w, "LEFT") == [104] and w.g.TAKEN[103] and w.env.FIGHTS.A.rolled == "defected",
          "the one with no trip: left %s" % ids(w, "LEFT"))
    # no faction, loyalty off, no room: a surrender instead, no one joined
    for setup in ("", "found(); LOYALTY_ON = false", "found(); ROOM = false"):
        w = fresh(src, setup)
        beaten_two(w, 0.1)
        check(w.env.FIGHTS.A.rolled == "surrendered" and w.truce() and not ids(w, "JOINED"),
              "%r: %s, joined %s" % (setup, w.env.FIGHTS.A.rolled, ids(w, "JOINED")))


def surrender(src):
    # the draw 0.4: 40, past defection's 30, inside surrender's 80; the ceasefire 24 + 48 * 0.4 = 43 hours
    w = fresh(src)
    a, b = beaten_two(w, 0.4, comp=True)
    t = w.truce()
    check(w.env.FIGHTS.A.rolled == "surrendered" and t and t.ends == "2026-11-03 07:00" and t.faction == "bandit",
          "the truce: %s" % (t and t.ends))
    for i in (a, b):
        check(w.att(i, 0) == 0 and t.npcs[i] == 0, "%d toward you: %s, old %s" % (i, w.att(i, 0), t.npcs[i]))
        check(w.att(i, 900) == 0 and w.att(900, i) == 0 and list(t.pairs["%d>900" % i].values()) == [0, 0],
              "%d and your companion: %s, %s" % (i, w.att(i, 900), w.att(900, i)))
    check(w.news() == ["F:bandit at O:A have surrendered. They'll hold their fire, for now."], "the news: %s" % w.news())
    # an outpost under a truce has no fight
    w.run("kill(%d)" % a)
    w.look()
    check(len(w.beaten()) == 1 and w.env.FIGHTS.A is None, "a fight under the truce")
    # a pair not at war is left as it is: -999 stays, -1000 comes to 0; only what changed is kept,
    # and only that is put back
    w = fresh(src)
    w.run("companion(900)")
    a, b = beaten_two(w, 0.4)
    w.run("ATT['900>%d'] = -999; ATT['900>%d'] = -1000; GW['%d>900'] = 300" % (a, b, b))
    w.look()
    check(w.att(900, a) == -999 and w.att(900, b) == 0, "-999 and -1000: %s, %s" % (w.att(900, a), w.att(900, b)))
    t = w.truce()
    kept = t.pairs["%d>900" % b]
    check(t.pairs["%d>900" % a] is None and kept and kept[2] == 0 and kept[1] is None,
          "the pairs kept: %s, %s" % (t.pairs["%d>900" % a], kept and dict(kept)))
    w.ev("fotz_outposts.on_hit_hook(ONLINE[%d], 10, nil, db.actor)" % a)
    check(w.att(900, b) == -1000 and w.att(b, 900) == 300, "put back: %s, %s" % (w.att(900, b), w.att(b, 900)))


def truce_time(src):
    w = fresh(src)
    a, b = beaten_two(w, 0.4)
    # something sets their goodwill back meanwhile: the next look holds them again, old kept
    w.run("GW['%d>0'] = 0" % a)
    check(w.att(a, 0) == -2000, "the reset didn't take")
    w.run('NOW = "2026-11-03 06:59"')
    w.look()
    check(w.att(a, 0) == 0 and w.truce() and w.truce().npcs[a] == 0, "held again: %s, old %s" % (w.att(a, 0), w.truce().npcs[a]))
    # its time: the old goodwill back, live and offline, and the news
    w.run('ONLINE[%d] = nil; NOW = "2026-11-03 07:00"' % b)
    w.look()
    check(w.truce() is None and w.att(a, 0) == -2000 and w.att(b, 0) == -2000,
          "over: %s, %s, %s" % (w.truce(), w.att(a, 0), w.att(b, 0)))
    check(w.news()[-1] == "The ceasefire at O:A is over: F:bandit there are hostile again.", "the news: %s" % w.news())


def truce_broken(src):
    w = fresh(src)
    a, b = beaten_two(w, 0.4, comp=True)
    w.ev("fotz_outposts.on_hit_hook(ONLINE[%d], 10, nil, ONLINE[900])" % a)
    check(w.truce() and w.att(a, 0) == 0, "your companion's hit ended it")
    w.ev("fotz_outposts.on_hit_hook(ONLINE[%d], 10, nil, db.actor)" % a)
    check(w.truce() is None and w.att(a, 0) == -2000 and w.att(b, 0) == -2000 and w.att(900, b) == -3000,
          "your hit: %s, %s, %s" % (w.att(a, 0), w.att(b, 0), w.att(900, b)))
    check(w.news()[-1] == "You broke the ceasefire at O:A: F:bandit there are hostile again.", "the news: %s" % w.news())


def truce_gone(src):
    for change in ('stalker_camp_builder.rival_camps.A.status = "unoccupied"',
                   'stalker_camp_builder.rival_camps.A.faction = "dolg"',
                   "stalker_camp_builder.rival_camps.A = nil"):
        w = fresh(src)
        a, b = beaten_two(w, 0.4)
        n = len(w.news())
        w.run(change)
        w.look()
        check(w.truce() is None and w.att(a, 0) == -2000 and len(w.news()) == n,
              "%s: truce %s, %s, news %s" % (change, w.truce(), w.att(a, 0), w.news()[n:]))


def save_load(src):
    w = fresh(src)
    a, b = beaten_two(w, 0.4)
    # an update just now: the next look is 5 s off, so only the save's flag applies it again
    w.env.update_hook()
    w.run("TIME = 100")
    m = w.ev("{}")
    w.env.save_hook(m)
    check(w.att(a, 0) == -2000 and w.att(b, 0) == -2000, "the save kept the ceasefire's goodwill")
    check(m.fotz_outposts and m.fotz_outposts.truces.A, "the truces not in the save")
    w.env.update_hook()
    check(w.att(a, 0) == 0 and w.att(b, 0) == 0, "not applied again after the save: %s" % w.att(a, 0))
    # a load: the saved truces, the fights forgotten; another version is set aside
    w2 = fresh(src)
    w2.env.FIGHTS.X = w2.ev("{ top = 3 }")
    w2.env.load_hook(w2.ev('{ fotz_outposts = { v = 1, truces = { A = { faction = "bandit", name = "O:A", '
                           'ends = "2026-11-03 07:00", npcs = {}, pairs = {} } } } }'))
    check(w2.env.T.truces.A and w2.env.T.truces.A.ends == "2026-11-03 07:00" and w2.env.FIGHTS.X is None, "the load")
    w2.env.load_hook(w2.ev('{ fotz_outposts = { v = 99, truces = { A = {} } } }'))
    check(w2.env.T.truces.A is None and any("set aside" in s for s in w2.g.LOG.values()), "version 99 read")


def switched_off(src):
    w = fresh(src)
    a, b = beaten_two(w, 0.4)
    w.run('MCM["fotz/outposts"] = false; TIME = 10000')
    w.env.update_hook()
    check(w.truce() is None and w.att(a, 0) == -2000, "switched off, the ceasefire stays")
    w = fresh(src, "RANDOM = 0.99", 'MCM["fotz/outposts"] = false')
    ids(w, 'garrison("A", "bandit", 100, 0, { "novice", "novice" })')
    w.env.update_hook()
    check(w.env.FIGHTS.A is None, "switched off, a fight")
    w = fresh(src, "stalker_camp_builder = nil")
    check(not w.env.enabled(), "on without Homestead")


def strings(src):
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    want = set(re.findall(r'"(st_fotz_news_outpost_\w+)"', src)) | {"ui_mcm_fotz_outposts", "ui_mcm_fotz_outposts_desc"}
    check(len(want) == 6 and want <= have, "missing: %s" % sorted(want - have))


def run(src):
    for t in (config, chances, fight, ranks, defection, surrender, truce_time, truce_broken, truce_gone, save_load,
              switched_off, strings):
        t(src)
    return "12 scenarios"


def expose(src):
    """The script's local callbacks, reachable for the test."""
    return src + ("\non_hit_hook = npc_on_hit_callback\nsave_hook = save_state\nload_hook = load_state\n"
                  "update_hook = actor_on_update\n")


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
