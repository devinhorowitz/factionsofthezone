"""Run fotz_faction.script under LuaJIT 2.0 against stand-ins for the engine's packets, server
objects, live NPCs and relation matrix, and check the faction you lead.

Checked: founding refuses without the declaration; founding copies your old faction's relations
and makes the faction your friend; companions join with their own squad and group; a save returns
every member (online, offline, dead) to their old faction by editing only the faction index in the
state packet, returns you to yours, and drops the dead; you're back in your faction after the save;
a load reapplies relations, re-gives the faction on the update after a member comes online (never
inside net spawn), and drops an id that names someone else now; disguise and "you join it" are
respected; a dismissed companion leaves; disbanding returns everyone, live or by packet; nothing
ever changes a dead NPC's faction; a save of another version is set aside; the strings exist.
Others: anyone another mod put in the faction is saved in the old one (live NPC untouched), also
after disbanding; Homestead's records (settlers, trader, keyed timers) get the old faction on each
update, at the save and at load; a game without a faction never looks through every object.

    python test_faction.py            the real script
    python test_faction.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
GD = os.path.join(HERE, "..", "gamedata")
SCRIPT = os.path.join(GD, "scripts", "fotz_faction.script")
ENG = os.path.join(GD, "configs", "text", "eng", "st_fotz.xml")
MCM = os.path.join(GD, "scripts", "fotz_mcm.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    # the 2026-10-31 sweep
    "blank_renames": ('    local name = name_wanted(ui_mcm.get("fotz/faction_name"))',
                      '    local name = ui_mcm.get("fotz/faction_name") or ""'),
    "undeclared_kept_on": ("        parked, F = F, nil\n", "        parked = F\n"),
    "parked_not_saved": ("    m_data.fotz_faction = F or parked", "    m_data.fotz_faction = F"),
    "no_back_after_save": ("    if saved then\n        back_after_save()\n    end\n", ""),
    "offset": ("    p:r_s32()\n    p:r_stringZ()\n    local at", "    p:r_s32()\n    local at"),
    "dead_set": ("    if o and o:alive() then\n        o:set_character_community(m.mother", "    if o then\n        o:set_character_community(m.mother"),
    "identity": ("return se ~= nil and IsStalker(nil, se:clsid()) and se:profile_name() == m.profile",
                 "return se ~= nil"),
    "no_defer": ("    if same_member(id, m) then\n        pending[id] = true",
                 "    if same_member(id, m) then\n        npc:set_character_community(OWN, npc:squad(), npc:group())"),
    "actor_save": ('    if db.actor:character_community() == ACTOR_OWN then\n        db.actor:set_character_community("actor_" .. F.mother, 0, 0)\n    end\n    log("save: %s members',
                   '    log("save: %s members'),
    "keep_dead": ("            if m.dead then\n                F.members[id] = nil\n            end\n", ""),
    "always_join": ("    if you_join() then", "    if true then"),
    "keep_dismissed": ('if m.via == "companion" and not m.dead and not comp[id] then', "if false then"),
    "squad_zero": ("npc:set_character_community(OWN, npc:squad(), npc:group())", "npc:set_character_community(OWN, 0, 0)"),
    "no_declared_check": ("    if not declared() then\n        log(\"! %s isn't declared: is", "    if false then\n        log(\"! %s isn't declared: is"),
    "copy_reversed": ("base[OWN .. \">\" .. comm] = rel(mother, comm)", "base[OWN .. \">\" .. comm] = rel(comm, mother)"),
    "not_friends": ("            base[a .. \">\" .. b] = 2000", "            base[a .. \">\" .. b] = 0"),
    "no_reapply": ('    log("%s: %s cells, %s members", F.name, apply_relations(),', '    log("%s: %s cells, %s members", F.name, 0,'),
    "any_version": ('if type(d) == "table" and d.v == SAVE_VERSION then', 'if type(d) == "table" then'),
    "disband_keeps_actor": ('    if db.actor:character_community() == ACTOR_OWN then\n        db.actor:set_character_community("actor_" .. F.mother, 0, 0)\n    end\n    last_mother', "    last_mother"),
    "no_strays": ("local ok, strays = pcall(function() return touched and return_strays() or 0 end)", "local ok, strays = true, 0"),
    "no_scrub_update": ("    tick()\n    if touched then\n        scrub_partners()\n    end\nend", "    tick()\nend"),
    "no_scrub_save": ("    if touched then\n        scrub_partners()\n    end\n    local reverted", "    local reverted"),
    "no_scrub_load": ("    sync_mcm()\n    scrub_partners()\n", "    sync_mcm()\n"),
    "scrub_no_npc": ('local at = type(k) == "number" and k or id', "local at = id"),
    "scrub_keeps_keys": ("if k == OWN or k == ACTOR_OWN then", "if false then"),
    "scrub_no_cycles": ("    if seen[t] then\n        return 0\n    end\n", ""),
    "disband_forgets": ("    last_mother = F.mother\n", ""),
    "always_sweep": ("return touched and return_strays() or 0", "return return_strays()"),
    "partner_raises": ("        local ok, err = pcall(function()\n            local mod = _G[module]",
                       "        local ok, err = (function(f) return true, f() end)(function()\n            local mod = _G[module]"),
    "partner_log_spam": ("if not ok and not unreadable[module] then", "if not ok then"),
    "no_fair_autocomplete": ('    fair_autocomplete_kill_tracker = { "_player_kills" },\n', ""),
    "no_politics_found": ("    politics_apply()\n    return n", "    return n"),
    "no_politics_disband": ("    scrub_partners()\n    politics_apply()\n", "    scrub_partners()\n"),
    "same_uid": ('uid = string.format("%s/%s", tostring(os.time()), tostring(time_global())) }', 'uid = "same" }'),
    "join_by_default": ('return ui_mcm ~= nil and ui_mcm.get("fotz/faction_join") == true',
                        'return not (ui_mcm and ui_mcm.get("fotz/faction_join") == false)'),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end

-- net_packet: little-endian, a u16 from w_begin, zero-terminated strings
local Packet = {}
Packet.__index = Packet
function net_packet() return setmetatable({ b = {}, r = 0 }, Packet) end
function Packet:w_begin(n) self.b = {}; self:w_u8(n % 256); self:w_u8(math.floor(n / 256)) end
function Packet:w_u8(v) self.b[#self.b + 1] = v % 256 end
function Packet:w_u32(v) for i = 0, 3 do self:w_u8(math.floor(v / 2 ^ (8 * i)) % 256) end end
function Packet:w_s32(v) if v < 0 then v = v + 2 ^ 32 end self:w_u32(v) end
function Packet:w_stringZ(s) for i = 1, #s do self:w_u8(s:byte(i)) end self:w_u8(0) end
function Packet:w_tell() return #self.b end
function Packet:r_seek(n) self.r = n end
function Packet:r_tell() return self.r end
function Packet:r_u8() self.r = self.r + 1 local v = self.b[self.r] assert(v, "read past the end") return v end
function Packet:r_u32() local v = 0 for i = 0, 3 do v = v + self:r_u8() * 2 ^ (8 * i) end return v end
function Packet:r_s32() local v = self:r_u32() if v >= 2 ^ 31 then v = v - 2 ^ 32 end return v end
function Packet:r_stringZ()
    local t = {}
    while true do local c = self:r_u8() if c == 0 then break end t[#t + 1] = string.char(c) end
    return table.concat(t)
end

COMMS = "actor, 0, stalker, 1, dolg, 2, ecolog, 3, bandit, 4, actor_stalker, 5, actor_dolg, 6, actor_ecolog, 7, actor_bandit, 8, fotz_own, 36, actor_fotz_own, 37"
local NAMES = {}
function names() NAMES = {} local i = 0 for w in string.gmatch(COMMS, "([%a_]+), %d+") do NAMES[i] = w; NAMES[w] = i; i = i + 1 end end
names()
ini_sys = { r_string_ex = function(_, sec, key) return (sec == "game_relations" and key == "communities") and COMMS or nil end }

CLS_STALKER = 7
function IsStalker(o, c) if o then return o.stalker == true end return c == CLS_STALKER end

SE, ONLINE, CALLS = {}, {}, {}
local Server = {}
Server.__index = Server
function Server:community() return NAMES[self.comm] end
function Server:profile_name() return self.profile end
function Server:clsid() return CLS_STALKER end
function Server:STATE_Write(p)
    p:w_u32(self.money); p:w_stringZ(self.spec); p:w_s32(self.flags); p:w_stringZ(self.profile)
    p:w_s32(self.comm); p:w_s32(self.rank)
    for i = 1, #self.rest do p:w_u8(self.rest:byte(i)) end
end
function Server:STATE_Read(p, size)
    self.money = p:r_u32(); self.spec = p:r_stringZ(); self.flags = p:r_s32(); self.profile = p:r_stringZ()
    self.comm = p:r_s32(); self.rank = p:r_s32()
    local t = {}
    while p:r_tell() < size do t[#t + 1] = string.char(p:r_u8()) end
    self.rest = table.concat(t)
    self.reads = (self.reads or 0) + 1
end
function Server:squad_members()
    local i = 0
    return function() i = i + 1 local id = self.members and self.members[i] if id then return { id = id } end end
end
function server(id, comm, profile)
    SE[id] = setmetatable({ id = id, comm = NAMES[comm], money = 1000 + id, spec = "spec_" .. id, flags = -3,
                            profile = profile or ("p" .. id), rank = 450, rest = "\1\2\0\127tail" .. id }, Server)
    return SE[id]
end

PHASE = "update"
local Npc = {}
Npc.__index = Npc
function Npc:id() return self.nid end
function Npc:alive() return self.live end
function Npc:character_community() return self.comm end
function Npc:character_name() return self.name end
function Npc:squad() return self.sq end
function Npc:group() return self.gr end
function Npc:set_character_community(c, sq, gr)
    assert(self.live, "set_character_community on a dead NPC")
    CALLS[#CALLS + 1] = { id = self.nid, comm = c, sq = sq, gr = gr, phase = PHASE }
    self.comm = c
    if SE[self.nid] then SE[self.nid].comm = NAMES[c] end
end
function online(id, comm, sq, gr)
    local se = SE[id] or server(id, comm)
    ONLINE[id] = setmetatable({ nid = id, live = true, comm = comm, name = "Stalker " .. id, sq = sq or 3, gr = gr or 4, stalker = true }, Npc)
    return ONLINE[id]
end
level = { object_by_id = function(id) return ONLINE[id] end }
LOOKUPS = 0
function alife() return { object = function(_, id) LOOKUPS = LOOKUPS + 1 return SE[id] end } end

ACTOR = setmetatable({ nid = 0, live = true, comm = "actor_ecolog", name = "You", sq = 0, gr = 0, stalker = false }, Npc)
db = { actor = ACTOR }
server(0, "actor_ecolog", "actor")
TRUE_COMM = "ecolog"
function get_actor_true_community() return TRUE_COMM end
DISGUISED = false
gameplay_disguise = { is_actor_disguised = function() return DISGUISED end }

REL = {}
relation_registry = {
    community_relation = function(a, b) return REL[a .. ">" .. b] or 0 end,
    set_community_relation = function(a, b, v) REL[a .. ">" .. b] = v end,
}
MCM = {}
SET = {}
ui_mcm = { get = function(id) return MCM[id] end, set = function(id, v) SET[id] = v; MCM[id] = v end }
NEWS = {}
news_manager = { send_tip = function(_, text) NEWS[#NEWS + 1] = text end }
STR = {}
game = { translate_string = function(id) return STR[id] or id end }
DATE = "2012-05-01"
fotz_census = { game_date = function() return DATE .. " 08:00" end }
COMPANIONS = {}
axr_companions = { companion_squads = COMPANIONS }
NOW = 0
function time_global() return NOW end
CALLBACKS = {}
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end

function tick() NOW = NOW + 1500; CALLBACKS.actor_on_update() end

-- a value as Lua source, as a save carries it to the next game
function dump(v)
    local ty = type(v)
    if ty == "table" then
        local out = {}
        for k, x in pairs(v) do out[#out + 1] = "[" .. dump(k) .. "] = " .. dump(x) end
        return "{ " .. table.concat(out, ", ") .. " }"
    elseif ty == "string" then return string.format("%q", v)
    elseif ty == "number" then return string.format("%.17g", v) end
    return tostring(v)
end
function snapshot(id) local s = SE[id] return dump({ s.money, s.spec, s.flags, s.profile, s.rank, s.rest }) end
"""


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def english():
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    return {s.get("id"): s.findtext("text") for s in root.iter("string")}


class World:
    def __init__(self, src, setup="", m_data="{}", first_update=True):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(WORLD)
        self.lua.execute("\n".join("STR[%s] = %s" % (lua_str(k), lua_str(v)) for k, v in english().items()))
        self.lua.execute(setup)
        self.env = self.lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                                 "local f = assert(loadstring(src, 'fotz_faction')) setfenv(f, env) f() return env end")(src)
        self.env.on_game_start()
        self.cb = self.g.CALLBACKS
        self.cb["load_state"](self.lua.eval(m_data))
        if first_update:
            self.cb["actor_on_first_update"]()

    def run(self, code):
        return self.lua.execute(code)

    def eval(self, code):
        return self.lua.eval(code)

    def comm(self, id):
        return self.eval("SE[%d]:community()" % id)

    def live(self, id):
        o = self.g.ONLINE[id]
        return o and o.comm

    def calls(self):
        c = self.g.CALLS
        return [(c[i].id, c[i].comm, c[i].sq, c[i].gr, c[i].phase) for i in range(1, len(c) + 1)]

    def news(self):
        return list(self.g.NEWS.values())

    def log(self):
        return list(self.g.LOG.values())


#: most scenarios run with "You join it" chosen; default_leads runs without it
JOIN = 'MCM["fotz/faction_join"] = true\n'

SETUP = JOIN + """
REL["ecolog>bandit"] = -1500
REL["bandit>ecolog"] = -1400
REL["actor_ecolog>dolg"] = 200
REL["dolg>actor_ecolog"] = 250
-- a companion squad: 501 and 503 online, 502 offline; 601 online but not a companion
server(500, "stalker").members = { 501, 502, 503 }
COMPANIONS[500] = false
online(501, "stalker", 3, 4)
server(502, "dolg")
online(503, "stalker", 5, 6)
online(601, "bandit")
"""


def not_declared(src):
    w = World(src, setup='COMMS = "actor, 0, stalker, 1, ecolog, 2, actor_ecolog, 3"; names()' + SETUP)
    check(w.env.found("Wolves") is False and w.env.F is None, "founded without the declaration")
    check(any("isn't declared" in l for l in w.log()), "no log line for the missing declaration")
    check(w.g.ACTOR.comm == "actor_ecolog" and len(w.calls()) == 0, "something changed: %s" % w.calls())

    # a save with a faction, loaded where the install doesn't declare it: kept aside as saved, so
    # nothing names the faction (the engine asserts on an undeclared one), and the next save keeps it
    saved = ('{ fotz_faction = { v = 1, name = "Wolves", founded = "2012-05-01", mother = "ecolog", base = {}, '
             'members = { [501] = { name = "Stalker 501", mother = "stalker", profile = "p501" } } } }')
    w = World(src, setup='MCM["fotz/faction"] = true; COMMS = "actor, 0, stalker, 1, ecolog, 2, actor_ecolog, 3"; names()'
              + SETUP, m_data=saved)
    check(w.env.F is None and w.g.SET["fotz/faction"] is False, "an undeclared faction was restored: %s" % w.env.F)
    w.run("tick()")
    w.cb["on_option_change"]()
    check(len(w.calls()) == 0 and w.g.ACTOR.comm == "actor_ecolog", "the undeclared faction was named: %s" % w.calls())
    m = w.eval("{}")
    w.cb["save_state"](m)
    check(m.fotz_faction is not None and m.fotz_faction.name == "Wolves", "the save dropped the faction kept aside")


def blank_name(src):
    """A blank name (the box's default) is the default name, at founding and at every Accept after."""
    w = World(src, setup=SETUP)
    default = w.eval('game.translate_string("st_fotz_default_name")')
    w.run('MCM["fotz/faction"] = true; MCM["fotz/faction_name"] = ""')
    w.cb["on_option_change"]()
    check(w.env.F is not None and w.env.F.name == default, "founded as %r" % (w.env.F and w.env.F.name))
    w.cb["on_option_change"]()
    check(w.env.F.name == default, "a later Accept with the box blank renamed it %r" % w.env.F.name)
    w.run('MCM["fotz/faction_name"] = "Wolves"')
    w.cb["on_option_change"]()
    check(w.env.F.name == "Wolves", "not renamed: %r" % w.env.F.name)
    w.run('MCM["fotz/faction_name"] = ""')
    w.cb["on_option_change"]()
    check(w.env.F.name == default, "a cleared box: %r" % w.env.F.name)


def found_save_load(src):
    w = World(src, setup=SETUP)
    check(w.g.SET["fotz/faction"] is False, "MCM wasn't set to the save's state at load")
    check(w.env.found("Wolves") is True, "founding failed")
    REL = w.g.REL
    check(REL["fotz_own>bandit"] == -1500 and REL["bandit>fotz_own"] == -1400, "relations weren't copied")
    check(REL["actor_fotz_own>dolg"] == 200 and REL["dolg>actor_fotz_own"] == 250, "the player twin's relations")
    check(all(REL["%s>%s" % (a, b)] == 2000 for a in ("fotz_own", "actor_fotz_own") for b in ("fotz_own", "actor_fotz_own")),
          "the faction isn't its own friend")
    check(w.g.ACTOR.comm == "actor_fotz_own", "you didn't join: %s" % w.g.ACTOR.comm)
    check(w.live(501) == "fotz_own" and w.live(503) == "fotz_own" and w.live(601) == "bandit",
          "companions: %s %s %s" % (w.live(501), w.live(503), w.live(601)))
    check((501, "fotz_own", 3, 4, "update") in w.calls(), "501 didn't join with its own squad and group: %s" % w.calls())
    check(w.env.F.members[502] is None, "an offline companion joined")
    check(w.news()[0] == "Wolves is founded. Its friends and enemies start as your old faction's." and
          "Stalker 501 has joined Wolves." in w.news(), "news %s" % w.news())

    # 501 dies; 503 goes offline (its server object keeps the faction)
    w.run("ONLINE[501].live = false")
    w.cb["npc_on_death_callback"](w.g.ONLINE[501])
    w.run("ONLINE[503] = nil")
    check(w.comm(501) == "fotz_own" and w.comm(503) == "fotz_own", "server objects before the save")
    before = {i: w.eval("snapshot(%d)" % i) for i in (501, 503)}

    m = w.eval("{}")
    w.cb["save_state"](m)
    check(w.comm(501) == "stalker" and w.comm(503) == "stalker", "the save left %s, %s" % (w.comm(501), w.comm(503)))
    check(all(w.eval("snapshot(%d)" % i) == before[i] for i in (501, 503)), "the packet edit changed more than the faction")
    check(w.g.SE[501].reads == 1 and w.g.SE[503].reads == 1, "packets read %s, %s times" % (w.g.SE[501].reads, w.g.SE[503].reads))
    check(w.g.ACTOR.comm == "actor_ecolog" and w.comm(0) == "actor_ecolog", "you were saved as %s" % w.g.ACTOR.comm)
    check(w.env.F.members[501] is None and w.env.F.members[503] is not None, "the dead weren't dropped, or the living were")
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_fotz_own", "you weren't back in your faction after the save")
    check(w.comm(503) == "fotz_own" and w.eval("snapshot(503)") == before[503],
          "after the save, the offline member's server object stayed %s" % w.comm(503))
    check(not any(c[0] == 501 and c[4] != "update" for c in w.calls()), "a dead NPC's faction was changed")
    saved = w.eval("dump")(m)

    # the next game: 503 comes online again; 504 was a member, but its id now names someone else
    setup2 = """
server(503, "stalker")
server(500, "stalker").members = { 503 }
COMPANIONS[500] = false
server(504, "stalker", "someone_else")
SE[0] = nil
server(0, "actor_ecolog", "actor")
""" + SETUP.split("-- a companion")[0]
    m2 = saved.replace('["members"] = { ', '["members"] = { [504] = { ["mother"] = "dolg", ["name"] = "Old", ["profile"] = "p504" }, ', 1)
    w2 = World(src, setup=setup2, m_data=m2)
    check(w2.g.SET["fotz/faction"] is True and w2.g.SET["fotz/faction_name"] == "Wolves", "MCM wasn't synced from the save")
    check(w2.g.REL["fotz_own>bandit"] == -1500 and w2.g.REL["fotz_own>actor_fotz_own"] == 2000, "relations weren't reapplied")
    check(w2.g.ACTOR.comm == "actor_fotz_own", "you weren't put back in your faction at load")
    w2.run('online(503, "stalker", 5, 6)')
    w2.run('PHASE = "net_spawn"')
    w2.cb["npc_on_net_spawn"](w2.g.ONLINE[503])
    w2.run('online(504, "stalker")')
    w2.cb["npc_on_net_spawn"](w2.g.ONLINE[504])
    w2.run('PHASE = "update"')
    check(w2.live(503) == "stalker", "the faction was given inside net spawn")
    w2.run("tick()")
    check(w2.live(503) == "fotz_own" and w2.live(504) == "stalker", "after the update: 503 %s, 504 %s" % (w2.live(503), w2.live(504)))
    check(w2.env.F.members[504] is None, "a reused id stayed a member")
    check(not any(c[4] == "net_spawn" for c in w2.calls()), "a faction changed during net spawn: %s" % w2.calls())
    # an online member through a save: saved in his old faction, his server object back in yours on
    # the next update, the live NPC in it throughout
    m3 = w2.eval("{}")
    w2.cb["save_state"](m3)
    check(w2.comm(503) == "stalker" and w2.live(503) == "fotz_own", "the save: %s, %s" % (w2.comm(503), w2.live(503)))
    w2.run("tick()")
    check(w2.comm(503) == "fotz_own" and w2.live(503) == "fotz_own", "after the save: %s, %s" % (w2.comm(503), w2.live(503)))
    return w2


def you_and_disguise(src):
    w = World(src, setup=SETUP)
    w.env.found("Wolves")
    w.run('ACTOR.comm = "actor_dolg"; DISGUISED = true')
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_dolg", "the disguise was undone")
    w.run('ACTOR.comm = "actor_ecolog"; DISGUISED = false')
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_fotz_own", "you weren't put back after the disguise")
    w.run('MCM["fotz/faction_join"] = false')
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_ecolog", "with 'you join it' off you stayed in: %s" % w.g.ACTOR.comm)
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_ecolog", "you were put back in with the option off")


def default_leads(src):
    # "You join it" is off unless chosen: you lead from your old faction, and only members join
    w = World(src, setup=SETUP.replace(JOIN, ""))
    w.env.found("Wolves")
    check(w.g.ACTOR.comm == "actor_ecolog", "you joined without choosing to: %s" % w.g.ACTOR.comm)
    check(w.live(501) == "fotz_own" and w.live(503) == "fotz_own", "companions didn't join while you lead")
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_ecolog", "an update put you in: %s" % w.g.ACTOR.comm)
    # in from an older build that joined you by default: the next update takes you back out
    w.run('ACTOR.comm = "actor_fotz_own"')
    w.run("tick()")
    check(w.g.ACTOR.comm == "actor_ecolog", "you stayed joined without the option: %s" % w.g.ACTOR.comm)


def politics_hook(src):
    # the politics engine writes the faction's relations again after it does, and forgets a
    # disbanded faction: each faction has its own id
    w = World(src, setup=SETUP + "APPLIED = 0; fotz_politics = { apply = function() APPLIED = APPLIED + 1 end }")
    w.env.found("Wolves")
    n, uid = w.g.APPLIED, w.env.F.uid
    check(n >= 1 and uid, "founding: politics applied %d times, id %s" % (n, uid))
    w.run('MCM["fotz/faction"] = false')
    w.cb["on_option_change"]()
    check(w.g.APPLIED > n, "disbanding didn't tell politics")
    w.run("tick()")
    w.run('MCM["fotz/faction"] = true')
    w.cb["on_option_change"]()
    check(w.env.F.uid and w.env.F.uid != uid, "a new faction kept the id %s" % w.env.F.uid)


def dismissed_and_disband(src, w):
    w.run("COMPANIONS[500] = nil")
    w.run("tick()")
    check(w.live(503) == "stalker" and w.env.F.members[503] is None, "a dismissed companion stayed")
    check(w.news()[-1] == "Stalker 503 has left Wolves.", "news %s" % w.news()[-1])
    # new members: 701 online, then dead and online; 702 offline
    w.run('server(700, "stalker").members = { 701, 702 }; COMPANIONS[700] = false; online(701, "stalker"); online(702, "stalker")')
    w.run("tick()")
    w.run("ONLINE[702] = nil")
    w.run("ONLINE[701].live = false")
    w.cb["npc_on_death_callback"](w.g.ONLINE[701])
    w.run('MCM["fotz/faction"] = false')
    w.cb["on_option_change"]()
    check(w.env.F is None, "the faction wasn't disbanded")
    check(w.comm(701) == "stalker" and w.comm(702) == "stalker", "disbanding left %s, %s" % (w.comm(701), w.comm(702)))
    check(w.g.ACTOR.comm == "actor_ecolog", "you weren't returned: %s" % w.g.ACTOR.comm)
    check(w.news()[-1] == "Wolves is disbanded. Everyone goes back to their old faction.", "news %s" % w.news()[-1])


#: Homestead's saved tables, as far as they hold factions: a camp (hub 900, not a stalker) with a
#: trader and settlers, and the retaliation timers keyed by faction; 901 is a stalker another mod
#: can put in the faction
HOMESTEAD = """
stalker_camp_builder = { active_camps = { [900] = { trader_community = "dolg", survivors = {
    [503] = { community = "stalker", name = "Settler 503" },
    [801] = { community = "stalker" },
    [802] = { community = "dolg" } } } },
    faction_retaliation_timers = { bandit = 7 } }
stalker_camp_builder.active_camps[900].camp = stalker_camp_builder.active_camps[900]
server(801, "stalker")
server(802, "dolg")
online(901, "stalker")
"""

CAMP = "stalker_camp_builder.active_camps[900]"


def others(src):
    w = World(src, setup=SETUP + HOMESTEAD)
    w.env.found("Wolves")
    # Homestead caches the faction: 503's while a member, 801's when it was one (a Loner again now),
    # the trader's and a timer's; another mod puts 901 (online) and 902 (offline) in the faction
    w.run("local c = " + CAMP + """
c.trader_community = "fotz_own"
c.survivors[503].community = "fotz_own"; c.survivors[503].pending_community = "fotz_own"
c.survivors[801].community = "fotz_own"; c.survivors[801].comm = "fotz_own"
stalker_camp_builder.faction_retaliation_timers.fotz_own = 5
fair_autocomplete_kill_tracker = { _player_kills = { [503] = { faction = "fotz_own", time = 1 }, [998] = { faction = "bandit" } } }
ONLINE[901]:set_character_community("fotz_own", 0, 0)
server(902, "fotz_own")
""")
    w.run("tick()")
    got = w.eval("function() local c = %s local s = c.survivors return c.trader_community, s[503].community, "
                 "s[503].pending_community, s[801].community, s[801].comm, s[802].community end" % CAMP)()
    check(got == ("ecolog", "stalker", "stalker", "stalker", "stalker", "dolg"), "Homestead's records after an update: %s" % (got,))
    timers = dict(w.eval("stalker_camp_builder.faction_retaliation_timers").items())
    check(timers == {"ecolog": 5, "bandit": 7}, "Homestead's timers: %s" % timers)
    kills = w.eval("fair_autocomplete_kill_tracker._player_kills")
    check(kills[503]["faction"] == "stalker" and kills[998]["faction"] == "bandit",
          "Fair Autocomplete's kills: %s, %s" % (kills[503]["faction"], kills[998]["faction"]))

    # Homestead caches it again between the last update and the save
    w.run(CAMP + '.survivors[802].pending_community = "fotz_own"')
    m = w.eval("{}")
    w.cb["save_state"](m)
    check(w.eval(CAMP + ".survivors[802].pending_community") == "dolg", "a record cached just before the save kept our faction")
    check(w.comm(901) == "ecolog" and w.comm(902) == "ecolog", "others were saved in %s, %s" % (w.comm(901), w.comm(902)))
    check(w.live(901) == "fotz_own", "an outsider's live faction was changed: %s" % w.live(901))
    check(w.comm(501) == "stalker" and w.comm(503) == "stalker", "members were saved in %s, %s" % (w.comm(501), w.comm(503)))
    check(w.env.F.members[901] is None and w.env.F.members[902] is None, "an outsider became a member")
    check(any("2 others" in l for l in w.log()), "no log line for the others: %s" % w.log()[-1])

    # after disbanding, Homestead and another mod still spread the faction; the save takes both back
    w.run("tick()")
    w.run('MCM["fotz/faction"] = false')
    w.cb["on_option_change"]()
    w.run('server(903, "fotz_own"); %s.trader_community = "fotz_own"' % CAMP)
    m2 = w.eval("{}")
    w.cb["save_state"](m2)
    check(m2["fotz_faction"] is None, "a disbanded faction was saved")
    check(w.comm(903) == "ecolog", "after disbanding, another was saved in %s" % w.comm(903))
    check(w.eval(CAMP + ".trader_community") == "ecolog", "after disbanding, the trader record kept our faction")


def load_and_untouched(src):
    # a game that never had a faction: a save doesn't look through every object
    w = World(src, setup=SETUP + HOMESTEAD)
    w.run("LOOKUPS = 0")
    w.cb["save_state"](w.eval("{}"))
    check(w.g.LOOKUPS < 100, "a save without a faction looked up %d objects" % w.g.LOOKUPS)
    # a load with our name in Homestead's records (a save made in the moment before an update)
    w = World(src, setup=SETUP + HOMESTEAD + CAMP + '.survivors[801].community = "fotz_own"; server(904, "fotz_own")')
    check(w.env.F is None, "a faction from nowhere")
    check(w.eval(CAMP + ".survivors[801].community") == "stalker", "a load left our faction in Homestead's records")
    w.cb["save_state"](w.eval("{}"))
    check(w.comm(904) == "stalker", "after that load, another was saved in %s" % w.comm(904))
    # a partner whose tables raise: updates and saves go on, and it's logged once
    w = World(src, setup=SETUP + 'stalker_camp_builder = setmetatable({}, { __index = function() error("boom") end })')
    w.env.found("Wolves")
    for _ in range(3):
        w.run("tick()")
    w.cb["save_state"](w.eval("{}"))
    check(sum("couldn't read stalker_camp_builder" in l for l in w.log()) == 1, "a partner's error was logged %d times" %
          sum("couldn't read" in l for l in w.log()))
    check(w.comm(501) == "stalker", "a partner's error stopped the save's edits")


def other_version(src):
    w = World(src, setup=SETUP, m_data='{ fotz_faction = { v = 99, name = "X", members = {} } }')
    check(w.env.F is None and any("set aside" in l for l in w.log()), "a save of another version was read")


def strings(src):
    have = english()
    want = set(re.findall(r'"(st_fotz_\w+)"', src)) | {"fotz_own", "actor_fotz_own"}
    mcm = open(MCM, encoding="utf-8").read()
    for opt in re.findall(r'id = "(faction\w*)", type = "(?:check|input)"', mcm):
        want |= {"ui_mcm_fotz_" + opt, "ui_mcm_fotz_" + opt + "_desc"}
    check(len(want) == 15, "%d string ids looked for, not 15: %s" % (len(want), sorted(want)))
    check(re.search(r'id = "faction_join", type = "check", val = 1, def = false', mcm),
          "MCM's 'You join it' doesn't default to off")
    want |= {"st_dyn_news_comm_fotz_own_%d" % i for i in range(1, 15)}
    missing = sorted(want - set(have))
    check(not missing, "missing from the English table: %s" % missing)


def run(src):
    strings(src)
    not_declared(src)
    blank_name(src)
    w2 = found_save_load(src)
    dismissed_and_disband(src, w2)
    you_and_disguise(src)
    default_leads(src)
    politics_hook(src)
    others(src)
    load_and_untouched(src)
    other_version(src)
    return "11 scenarios: found, save, load, disguise, leading, politics, dismiss, disband, others, load scrub, names"


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
