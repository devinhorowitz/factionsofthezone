"""Run fotz_politics.script under LuaJIT 2.0 against a stateful relation matrix and check what it does.

Scenarios: kills lead to a war, quiet days to a truce, and the truce holds the line; ground taken
and fronts name a war's cause and voice, with the news levels; a common enemy makes an alliance
that lapses once the enemy is gone; each reason to stand down puts the game's relations back;
a relation another mod changed becomes the new start; a save and load rebuild the same matrix;
offline kills pass through the wrapper; the player's kills, silent kills and ignored kills; the
caps; members from a faction moving your faction's pair with it more (fotz_perks.amp), either way
round, and no other pair; and the shipped config's pairs.

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
    # the cells' starts across loads, other scripts' changes, the base game's store (the 2026-10-31 sweep)
    "start_reread_at_load": ("    if s and live == s.w then\n", "    if false then\n"),
    "pair_rows_additive": ("                pair_rows = pair_rows or i <= 2", "                pair_rows = false"),
    "restart_keeps_event": ('        if ev then\n            finish(p, st.day or today(), ev.kind .. "_over", "changed")\n        end\n', ""),
    "restart_keeps_drift": ("        st.drift[p.key], st.pending[p.key], st.trend[p.key] = nil, nil, nil\n", ""),
    "no_undo": ("        if o and r.live == o.w then", "        if false then"),
    "clamped_shift": ("            anchor[r.k] = r.live - (applied[r.k] or 0)",
                      "            anchor[r.k] = r.live - (written[r.k] - anchor[r.k])"),
    "no_notice_at_save": ("        for _, p in ipairs(PAIRS) do\n            if not p.own then\n                notice(p)\n"
                          "            end\n        end\n        local cells = {}", "        local cells = {}"),
    "no_scrub": ("        local n = scrub_store()", "        local n = 0"),
    "scrub_outside": ("        if a ~= nil and not outside[k] and not string.find(k, OWN, 1, true) then\n            local x, y",
                      "        if a ~= nil and not string.find(k, OWN, 1, true) then\n            local x, y"),
    "scrub_undone_ignored": ("(v == w or v == undone[k])", "v == w"),
    "cells_not_saved": ("        state().cells = cells", "        state().cells = {}"),
    "calendar_doy": ("local doy = math.floor((153 * ((m + 9) % 12) + 2) / 5) + d - 1",
                     "local doy = math.floor((153 * ((m + 9) % 12) + 2) / 5) + d"),
    "calendar_back": ("    local d = doy - math.floor((153 * mp + 2) / 5) + 1", "    local d = doy - math.floor((153 * mp + 2) / 5) + 2"),
    "budget": ("local move = clamp(pending, -cfg.daily_budget, cfg.daily_budget)", "local move = pending"),
    # members from a faction move your faction's pair with it more (fotz_perks.amp, 0.6.0)
    "encroach_ignored": ("            if p and push < 0 then\n                note(t, p, \"settled\", push)", "            if false then\n                note(t, p, \"settled\", push)"),
    # a war your members' settling caused has its own cause and voice (the 2026-11-07 sweep, C3)
    "settled_as_ground": ('note(t, p, "settled", push)', 'note(t, p, "ground", push)'),
    "settled_not_cause": ('for _, what in ipairs({ "front", "ground", "settled", "incident" }) do',
                          'for _, what in ipairs({ "front", "ground", "incident" }) do'),
    "settled_not_kept": ('for _, what in ipairs({ "kills", "ground", "front", "settled", "incident" }) do',
                         'for _, what in ipairs({ "kills", "ground", "front", "incident" }) do'),
    "settled_voice": ('    if best == "settled" then\n        voice = p.a == OWN and p.b or p.a\n    end\n', ""),
    "settled_old_save": ("                r.settled, r.ground = (r.settled or 0) + r.ground, nil", "                r.ground = r.ground"),
    # a parked faction keeps its state (M7)
    "parked_cleared": ("    if st.own ~= uid and not parked then", "    if st.own ~= uid then"),
    "parked_while_led": ("    local parked = not F and FF and", "    local parked = FF and"),
    "encroach_unguarded": ("        local ok, enc = pcall(T.encroachment, c)", "        local ok, enc = true, T.encroachment(c)"),
    "amp_ignored": ("(st.pending[k] or 0) + g.delta * own_amp(p)", "(st.pending[k] or 0) + g.delta"),
    "amp_here_only": ("M and M.amp_all and M.amp_all(other)", "M and M.amp and M.amp(other)"),
    "amp_one_side": ("local other = (p.a == OWN and p.b) or (p.b == OWN and p.a)", "local other = (p.a == OWN and p.b)"),
    "amp_all_pairs": ("local other = (p.a == OWN and p.b) or (p.b == OWN and p.a)",
                      "local other = (p.a == OWN and p.b) or (p.b == OWN and p.a) or p.a"),
    "no_recover": ("        d = d - d * cfg.recover\n", "        d = d\n"),
    "recover_at_war": ('if not (ev and ev.kind == "war") then', "if true then"),
    "truce_hold": ("d = math.max(d, ENEMIES + 1 - base)", "d = d"),
    "truce_damp": ("        move = move / 2\n", "        move = move\n"),
    "quiet": (">= cfg.quiet_days", ">= 0"),
    "min_war": ("days_between(ev.since, day) >= cfg.min_war_days", "true"),
    "fixed_pairs": ("if not fixed_pair[a .. \"/\" .. b] then", "if true then"),
    "fixed_factions": ("if not fixed[f] then", "if true then"),
    "actor_rows": ('{ "actor_" .. a, b }, { b, "actor_" .. a },', ""),
    "anchor_shift": ("            anchor[r.k] = r.live - (applied[r.k] or 0)", "            anchor[r.k] = anchor[r.k]"),
    "dynamic": ('if ui_options and ui_options.get("alife/general/dynamic_relations") then', "if false then"),
    "dfrc": ("if dynamic_faction_relations_customizer then", "if false then"),
    "fluid": ("if game_relations and game_relations.faction_cares then", "if false then"),
    "warfare": ("if IsWarfare and IsWarfare() then", "if false then"),
    "warfare_flag": ("if IsWarfare and IsWarfare() then", "if _G.WARFARE then"),
    "off_keeps": ("local d = on and (state().drift[p.key] or 0) or 0", "local d = state().drift[p.key] or 0"),
    "player_weight": ("if killer:id() == AC_ID then\n        comm, weight = players_side(), cfg.player_kill",
                      "if killer:id() == AC_ID then\n        comm, weight = players_side(), nil"),
    "silent_kill": ("if owner and owner:id() == AC_ID then", "if false then"),
    "rank_weight": ("(cfg.rank_weight[rank] or 1)", "1"),
    "forward": ("        return orig(...)\n", "        return orig()\n"),
    "ground_voice": ('note(t, p, "ground", cfg.ground * w, smart, was,', 'note(t, p, "ground", cfg.ground * w, smart, now,'),
    "common_either": ("at_war(p.a, f) and at_war(p.b, f)", "at_war(p.a, f) or at_war(p.b, f)"),
    "no_lapse": ('elseif ev and ev.kind == "alliance" and after < FRIENDS then',
                 'elseif ev and ev.kind == "alliance" and false then'),
    "same_day": ("    if st.day == day then\n        return\n    end\n", ""),
    "first_ticks": ("if first or not active() then", "if not active() then"),
    "any_version": ('if type(d) == "table" and d.v == SAVE_VERSION then', 'if type(d) == "table" then'),
    "news_level": ('if lv == "off" or (level == "all" and lv ~= "all") then', 'if lv == "off" then'),
    "news_cap": ("if (place or shown < 3) and say(", "if say("),
    # hooks for other mods (fotz_api, docs/HOOKS.md)
    "hook_start_unsent": ('    send("fotz_on_politics", { kind = kind,', '    local _ = ({ kind = kind,'),
    "hook_end_unsent": ("    send_end(p, day, how, ev, why)\n", "    local _ = why\n"),
    "hook_why_lost": ("since = ev and ev.since, why = why })", "since = ev and ev.since })"),
    "hook_reset_unsent": ('            send_end(PAIR[k], st.day or today(), ev.kind .. "_over", ev, "reset")\n', ""),
    "hook_changed_why": ('ev.kind .. "_over", "changed")', 'ev.kind .. "_over")'),
    "hook_disband_unsent": ('                        send_end(PAIR[k], st.day or today(), v.kind .. "_over", v, "disbanded")\n', ""),
    "hook_truce_why": ('finish(p, day, "war_over", "truce")', 'finish(p, day, "war_over")'),
    "taken_unsent_standing": ("        send_taken(c, not first and prev or nil, false)\n", ""),
    "taken_unsent": ("    send_taken(c, prev, true)\n", ""),
    "taken_counted_always": ("counted = counting and pair_of(was, now) ~= nil or false", "counted = true"),
    "taken_abandoned": ("        if was and now and was ~= now then\n", "        if was and was ~= now then\n"),
    "grievance_while_down": ("or amount == 0 or not active() then", "or amount == 0 then"),
    "incident_ignored": ('note(t, p, "incident", inc.war, inc.at)', 'note(t, p, "incident", 0, inc.at)'),
    "incident_kept": ("    st.incidents = {}\n    -- your members settled", "    -- your members settled"),
    "incident_not_cause": ('for _, what in ipairs({ "front", "ground", "settled", "incident" }) do',
                           'for _, what in ipairs({ "front", "ground", "settled" }) do'),
    "incident_news_lost": ("t[key].incident_news = t[key].incident_news or inc.news", "t[key].incident_news = nil"),
    "incident_default_news": ('news = at and "st_fotz_news_war_incident_at" or "st_fotz_news_war_incident"',
                              'news = "st_fotz_news_war_incident"'),
    "peace_ignored": ('            note(t, p, "goodwill", inc.peace)\n', ""),
    "place_ground": ('note(t, p, "ground", cfg.ground * w,', 'note(t, p, "ground", cfg.ground,'),
    "place_front_weight": ("        n = n + w\n", "        n = n + 1\n"),
    "place_front_at": ("        if w > top then\n", "        if false then\n"),
    "place_config_clamp": ("PLACES[id] = clamp(w, 1, PLACE_MAX)", "PLACES[id] = w"),
    "place_set_clamp": ("placed[smart] = clamp(w, 1, PLACE_MAX)", "placed[smart] = w"),
    "place_runtime_first": ("(placed[smart] or PLACES[smart])", "(PLACES[smart] or placed[smart])"),
    "place_clear_config": ("    if placed[smart] == nil then\n        return false\n", "    if false then\n        return false\n"),
    # a place's name, never its raw id (STALKER's report on 1.0.0, 2026-11-07)
    "place_raw_kept": ('name ~= "" and name ~= smart then', 'name ~= "" then'),
    "place_no_warfare_name": ('    local key = "st_" .. smart .. "_name"\n', "    local key = smart\n"),
    "place_no_level": ("        return s ~= lv and s or nil\n", "        return nil\n"),
    "place_level_raw": ("        return s ~= lv and s or nil\n", "        return lv\n"),
    "pending_cap": ("clamp((st.pending[k] or 0) + g.delta * own_amp(p), -cfg.pending_max, cfg.pending_max)",
                    "(st.pending[k] or 0) + g.delta * own_amp(p)"),
    "lo_cap": ("d = clamp(d + move, p.lo, p.hi)", "d = d + move"),
    "string_id": ('"st_fotz_news_alliance_plain"', '"st_fotz_news_alliance_plane"'),
    "news_unlogged": ('        log("news: %s", text)\n', ""),
    "base_names": ("    local s = game.translate_string(id)\n", "    local s = id\n"),
    "own_no_pairs": ("    if not F then\n        return\n    end\n    SIDES[#SIDES + 1] = OWN",
                     "    if true then\n        return\n    end\n    SIDES[#SIDES + 1] = OWN"),
    "own_anchor_live": ("anchor[k] = F and F.base[k] or live", "anchor[k] = live"),
    "own_anchor_of": ("return F and F.base[k] or relation_registry.community_relation(p.a, p.b)",
                      "return relation_registry.community_relation(p.a, p.b)"),
    "own_player_side": ("return led() and OWN or get_actor_true_community()", "return get_actor_true_community()"),
    "own_members_cells": ("{ ACTOR_OWN, f }, { f, ACTOR_OWN } } }", '{ ACTOR_OWN, f }, { f, ACTOR_OWN }, { OWN, "actor_" .. f } } }'),
    "own_keeps_old": ("    if st.own ~= uid and not parked then\n        for _, name in", "    if false then\n        for _, name in"),
    "own_sides": ("    SIDES[#SIDES + 1] = OWN\n", ""),
    "own_name": ('        return F and F.name or game.translate_string("st_fotz_default_name")',
                 '        return game.translate_string("st_fotz_default_name")'),
    "own_icon": ("voice ~= OWN and voice or nil", "voice"),
    "restore_no_apply": ('    log("relations restored to where they started")\n    return apply()',
                         '    log("relations restored to where they started")\n    return 1'),
    "restore_keeps_events": ("st.drift, st.pending, st.kills, st.hurt, st.recent, st.events, st.trend = {}, {}, {}, {}, {}, {}, {}",
                             "st.drift, st.pending, st.kills, st.hurt, st.recent, st.trend = {}, {}, {}, {}, {}, {}"),
    "restore_keeps_pending": ("st.drift, st.pending, st.kills, st.hurt, st.recent, st.events, st.trend = {}, {}, {}, {}, {}, {}, {}",
                              "st.drift, st.kills, st.hurt, st.recent, st.events, st.trend = {}, {}, {}, {}, {}, {}"),
    "restore_keeps_trend": ("st.drift, st.pending, st.kills, st.hurt, st.recent, st.events, st.trend = {}, {}, {}, {}, {}, {}, {}",
                            "st.drift, st.pending, st.kills, st.hurt, st.recent, st.events = {}, {}, {}, {}, {}, {}"),
    "no_trend": ("    st.trend[k] = after ~= before and after - before or nil\n", ""),
    "truce_trend": ("        st.trend[k] = cfg.truce_relation - before\n", ""),
    # your old faction's fixed relations (0.5.1)
    "own_not_fixed": ("        if not fixed_for_own(F.mother, f) then", "        if true then"),
    "own_fixed_faction_moves": ("return FIXED_FACTIONS[mother] == true or FIXED_PAIRS", "return FIXED_PAIRS"),
    "own_mother_prefixed": ('    mother = string.gsub(mother or "", "^actor_", "")\n', ""),
    "own_stale_kept": ("            if string.find(k, OWN, 1, true) and not PAIR[k] then\n                st[name][k] = nil",
                       "            if false then\n                st[name][k] = nil"),
    "own_stale_all": ("            if string.find(k, OWN, 1, true) and not PAIR[k] then\n                st[name][k] = nil",
                      "            if string.find(k, OWN, 1, true) then\n                st[name][k] = nil"),
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
news_manager = { send_tip = function(actor, text, timeout, sender, showtime) NEWS[#NEWS + 1] = tostring(sender) .. "|" .. text end }
-- the base game's own names, singular for some: Factions shows its own group names
NAMES = { dolg = "Duty", freedom = "Freedom", killer = "Mercenary", csky = "Clear Sky", stalker = "Free stalkers",
          bandit = "Bandit", army = "Military", ecolog = "Ecologist" }
STR = {}
-- the names of places: G.A.M.M.A.'s st_<smart>_name (the Warfare convention) and the levels'
PLACES = { st_s2_name = "Cordon - Rookie Village", l01_escape = "Cordon" }
game = { translate_string = function(id) return NAMES[id] or STR[id] or PLACES[id] or id end }
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
-- a smart's server object, every one on Cordon
SIMBOARD = { smarts_by_names = setmetatable({}, { __index = function(_, k)
    return { name = function() return k end, m_game_vertex_id = 7 }
end }) }
-- like the base game's: smart_names.ltx names a few (here s1, s6 and s7), else the raw id
SMART_NAMES = { s1 = true, s6 = true, s7 = true }
smart_terrain = { get_smart_terrain_name = function(se)
    return SMART_NAMES[se:name()] and ("Place " .. se:name()) or se:name()
end }
function alife() return { level_name = function(_, lid) return lid == 3 and "l01_escape" or "?" end } end
function game_graph() return { vertex = function(_, gv) return { level_id = function() return gv == 7 and 3 or 0 end } end } end
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
-- the base game's store of saved relations: game_relations.save_relation writes both ways, live
-- and into the actor's pstor, which the base game puts back at every load
PSTOR = {}
function load_var(obj, name, def) local v = PSTOR[name] if v == nil then return def end return v end
function save_var(obj, name, v) PSTOR[name] = v end
function save_relation(a, b, v)
    REL[a .. ">" .. b], REL[b .. ">" .. a] = v, v
    PSTOR["drx_df_" .. a .. "_" .. b .. "_relations"], PSTOR["drx_df_" .. b .. "_" .. a .. "_relations"] = v, v
end
function reapply_store(cells)
    for _, cell in ipairs(cells) do
        local x, y = string.match(cell, "^(.-)>(.*)$")
        local v = PSTOR["drx_df_" .. x .. "_" .. y .. "_relations"]
        if v ~= nil then REL[cell] = v end
    end
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
    def __init__(self, src, config=TEST_CONFIG, anchors=None, m_data=None, pre=None, at_load=None):
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
        # the base game's on_game_load, between the load and the first update
        if at_load:
            self.lua.execute(at_load)
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
    check(w.env.S.trend["dolg/killer"] == -360, "day 3: the day's move %s" % w.env.S.trend["dolg/killer"])
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
    check(w.env.S.trend["dolg/killer"] is None, "a day without a move kept a trend: %s" % w.env.S.trend["dolg/killer"])
    w.run('day("2012-05-07")')
    check(w.event("dolg/killer") == "truce" and w.drift("dolg/killer") == -600,
          "day 7: %s, drift %s" % (w.event("dolg/killer"), w.drift("dolg/killer")))
    check(w.env.S.trend["dolg/killer"] == 484, "the truce's move %s" % w.env.S.trend["dolg/killer"])
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
    # a place by smart_names.ltx's name, else G.A.M.M.A.'s st_<smart>_name, else its level's: never the raw id
    check(w.news() == ["killer|Mercenaries: We took Place s1 from Freedom.",
                       "killer|Mercenaries: We took Cordon - Rookie Village from Freedom.",
                       "killer|Mercenaries: We took Cordon from Freedom."], "ground news %s" % w.news())
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
    # something else sets one of the pair's own rows: the pair starts over from the values it has
    # now, drift gone, and the days after leave it there
    w.run('REL["dolg>killer"] = 2000')
    w.cb["on_option_change"]()
    w.run('day("2012-05-10")')
    check(w.rel("dolg>killer") == 2000 and w.rel("killer>dolg") == -500 and w.drift("dolg/killer") is None,
          "after another mod's change: %s, %s, drift %s" % (w.rel("dolg>killer"), w.rel("killer>dolg"),
                                                           w.drift("dolg/killer")))


DRIFT_500 = '{ fotz = { v = 1, day = "2012-05-09", drift = { ["dolg/killer"] = -500 } } }'


def reload(src, w, anchors=None):
    """w's game saved and loaded: the save's m_data and the base game's store go along; the engine
    resets the matrix to the starts, and the base game puts back what its store holds."""
    m = w.lua.eval("{}")
    w.cb["save_state"](m)
    dump = w.lua.eval("dump")
    at_load = "PSTOR = %s\nreapply_store({ %s })" % (dump(w.g.PSTOR), ", ".join('"%s"' % c for c in CELLS))
    return World(src, anchors=anchors or DK_ANCHORS, m_data=dump(m), at_load=at_load)


def store(w, cell):
    x, y = cell.split(">")
    return w.g.PSTOR["drx_df_%s_%s_relations" % (x, y)]


def other_scripts(src):
    """A disguise and a story ceasefire, through the base game's store, across saves and loads."""
    # a disguise: a copy of the row, 300 both ways while worn; the drift moves meanwhile; taken off,
    # the copy goes back: the row is Factions' again, at its start plus today's drift
    w = World(src, anchors=DK_ANCHORS, m_data=DRIFT_500)
    w.run('SNAP = REL["dolg>actor_killer"]; save_relation("dolg", "actor_killer", 300)')
    w.cb["on_option_change"]()
    check(w.rel("dolg>actor_killer") == 300 and w.rel("actor_killer>dolg") == 300,
          "the disguise's 300 wasn't kept: %s" % w.rel("dolg>actor_killer"))
    w.run('kill("dolg", "killer", "veteran", 10)')
    w.run('day("2012-05-10")')
    d1 = w.drift("dolg/killer")
    check(d1 is not None and d1 != -500, "the drift didn't move: %s" % d1)
    w.run('save_relation("dolg", "actor_killer", SNAP)')
    w.cb["on_option_change"]()
    check(w.rel("dolg>actor_killer") == -50 + d1 and w.rel("actor_killer>dolg") == -50 + d1,
          "taken off: %s, not %s" % (w.rel("dolg>actor_killer"), -50 + d1))
    # the save: the store's copy (Factions' old value) goes back to the row's start; the load
    # rebuilds every cell at its start plus the drift, and without Factions the row is at its start
    w2 = reload(src, w)
    check(store(w, "dolg>actor_killer") == -50 and store(w, "actor_killer>dolg") == -50,
          "the store kept Factions' value: %s" % store(w, "dolg>actor_killer"))
    want = {c: DK_ANCHORS[c] + d1 for c in CELLS}
    check({c: w2.rel(c) for c in CELLS} == want, "the load: %s, not %s" % ({c: w2.rel(c) for c in CELLS}, want))

    # worn through a save: the store keeps the disguise's 300, the load keeps the row at 300 and the
    # rest at their starts plus the drift, load after load
    w = World(src, anchors=DK_ANCHORS, m_data=DRIFT_500)
    w.run('save_relation("dolg", "actor_killer", 300)')
    w.cb["on_option_change"]()
    w2 = reload(src, w)
    w3 = reload(src, w2)
    for x in (w2, w3):
        rows = {c: x.rel(c) for c in CELLS}
        want = {c: (300 if c in ("dolg>actor_killer", "actor_killer>dolg") else DK_ANCHORS[c] - 500) for c in CELLS}
        check(rows == want, "worn across a load: %s, not %s" % (rows, want))
    check(store(w2, "dolg>actor_killer") == 300, "the disguise's stored 300 was changed: %s" % store(w2, "dolg>actor_killer"))

    # a story ceasefire during a war, all six rows at 2000, just before a save: the pair starts over
    # there, the war ends (in the war log, no news), and the days after leave it at 2000
    war = ('{ fotz = { v = 1, day = "2012-05-09", drift = { ["dolg/killer"] = -1500 }, events = { '
           '["dolg/killer"] = { kind = "war", since = "2012-05-05", a = "dolg", b = "killer" } } } }')
    w = World(src, anchors=DK_ANCHORS, m_data=war)
    w.run('save_relation("dolg", "killer", 2000); save_relation("actor_dolg", "killer", 2000); '
          'save_relation("dolg", "actor_killer", 2000)')
    news = len(w.news())
    w2 = reload(src, w)
    check(len(w.news()) == news, "the ceasefire made news: %s" % w.news()[news:])
    check({c: w2.rel(c) for c in CELLS} == {c: 2000 for c in CELLS} and w2.drift("dolg/killer") is None
          and w2.event("dolg/killer") is None and w2.history()[-1:] == ["war_over"],
          "after the ceasefire: %s, drift %s, event %s, history %s" % ({c: w2.rel(c) for c in CELLS},
          w2.drift("dolg/killer"), w2.event("dolg/killer"), w2.history()))
    w2.run('day("2012-05-10")')
    w2.run('day("2012-05-11")')
    check({c: w2.rel(c) for c in CELLS} == {c: 2000 for c in CELLS}, "the days after: %s" % {c: w2.rel(c) for c in CELLS})

    # the limit: a player row whose start plus drift was clamped; another script's value is kept
    # exactly, not moved by what the clamp cut
    anchors = dict(DK_ANCHORS, **{"dolg>actor_killer": -4500, "actor_killer>dolg": -4500})
    w = World(src, anchors=anchors, m_data=DRIFT_500)
    check(w.rel("dolg>actor_killer") == -4750, "the clamp: %s" % w.rel("dolg>actor_killer"))
    w.run('save_relation("dolg", "actor_killer", 2000)')
    w.cb["on_option_change"]()
    check(w.rel("dolg>actor_killer") == 2000 and w.rel("actor_killer>dolg") == 2000,
          "after the clamp, another script's 2000 became %s" % w.rel("dolg>actor_killer"))


def calendar(src):
    """day_num and day_str against Python's calendar, leap days and century years included."""
    import datetime
    w = World(src, anchors=DK_ANCHORS)
    # by the calendar alone: the OS clock carries its time zone (a day off at UTC+-12)
    w.run("os.time = function() error('the OS clock') end; os.date = function() error('the OS clock') end")
    epoch = datetime.date(1970, 1, 1).toordinal()
    for s in ("1970-01-01", "2000-02-29", "2012-02-28", "2012-02-29", "2012-03-01", "2012-12-31", "2018-11-02",
              "2100-02-28", "2100-03-01", "1999-12-31"):
        n = datetime.date(*map(int, s.split("-"))).toordinal() - epoch
        check(w.env.day_num(s) == n and w.env.day_str(n) == s, "%s: %s, %s" % (s, w.env.day_num(s), w.env.day_str(n)))
    for n in range(14000, 18000, 7):
        s = datetime.date.fromordinal(n + epoch).isoformat()
        check(w.env.day_str(n) == s and w.env.day_num(s) == n, "day %d: %s" % (n, w.env.day_str(n)))


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


#: the faction you lead, founded from Duty: some of its founding relations
OWN_BASE = {"fotz_own>killer": -200, "killer>fotz_own": -250, "actor_fotz_own>killer": -150,
            "killer>actor_fotz_own": -150, "fotz_own>actor_killer": -300, "actor_killer>fotz_own": -300}
#: the cells politics moves for it and the Mercenaries (not its members' relation to a player)
OWN_CELLS = ["fotz_own>killer", "killer>fotz_own", "actor_fotz_own>killer", "killer>actor_fotz_own"]


def led_lua(uid="u1", mother="dolg"):
    return ('fotz_faction = { F = { name = "Wolves", mother = %s, founded = "2012-05-01", uid = %s, base = { %s } } }'
            % (lua_str(mother), lua_str(uid), ", ".join("[%s] = %d" % (lua_str(k), v) for k, v in OWN_BASE.items())))


def your_faction(src):
    w = World(src, anchors=DK_ANCHORS, pre=led_lua())
    got = {c: w.rel(c) for c in OWN_CELLS}
    check(got == {c: OWN_BASE[c] for c in OWN_CELLS}, "your faction's cells at load: %s" % got)
    own = [w.env.PAIRS[i].key for i in range(1, len(w.env.PAIRS) + 1) if w.env.PAIRS[i].own]
    # every side but Freedom: Duty's lore pair with Freedom never changes, so neither does yours
    check(len(own) == 7 and "fotz_own/killer" in own and "dolg/fotz_own" in own and "fotz_own/freedom" not in own,
          "your faction's pairs: %s" % own)

    # its members' kills and yours count for it, not for Duty
    w.run('day("2012-05-01")')
    w.run('kill("killer", "fotz_own", "veteran", 30)')
    w.run('kill("killer", "actor", "novice", 10)')
    check(w.env.S.kills["fotz_own/killer"] == 65 and w.env.S.kills["dolg/killer"] is None,
          "kills: yours %s, Duty's %s" % (w.env.S.kills["fotz_own/killer"], w.env.S.kills["dolg/killer"]))
    w.run('day("2012-05-02")')
    check(w.drift("fotz_own/killer") == -400, "day 2: drift %s" % w.drift("fotz_own/killer"))
    got = {c: w.rel(c) for c in OWN_CELLS}
    check(got == {c: OWN_BASE[c] - 400 for c in OWN_CELLS}, "day 2: cells %s" % got)
    writes = list(w.g.WRITES.values())
    check(not any(c in writes for c in ("fotz_own>actor_killer", "actor_killer>fotz_own", "fotz_own>actor_dolg")),
          "a member's relation to a player moved")

    # the Mercenaries hit back: war, in your faction's voice and under its name
    w.run('kill("fotz_own", "killer", "veteran", 60)')
    w.run('day("2012-05-03")')
    check(w.event("fotz_own/killer") is None, "war a day early")
    w.run('day("2012-05-04")')
    check(w.event("fotz_own/killer") == "war", "no war: drift %s" % w.drift("fotz_own/killer"))
    check(w.news() and w.news()[-1].startswith("nil|Wolves: "), "the war's news: %s" % w.news())

    # two factions at war with yours grow closer
    w.env.S.events["bandit/fotz_own"] = w.lua.eval('{ kind = "war", since = "2012-05-04", a = "bandit", b = "fotz_own" }')
    w.run('day("2012-05-05")')
    check(w.drift("bandit/killer") == 60, "common enemy: bandit/killer drift %s" % w.drift("bandit/killer"))

    # a load restores it; a different faction in that save starts clean
    m = w.lua.eval("{}")
    w.cb["save_state"](m)
    saved = w.lua.eval("dump")(m)
    w2 = World(src, anchors=DK_ANCHORS, pre=led_lua(), m_data=saved)
    got = {c: w2.rel(c) for c in OWN_CELLS}
    want = {c: w.rel(c) for c in OWN_CELLS}
    check(got == want and w2.event("fotz_own/killer") == "war", "a load rebuilt %s, not %s" % (got, want))
    w3 = World(src, anchors=DK_ANCHORS, pre=led_lua("u2"), m_data=saved)
    check(w3.drift("fotz_own/killer") is None and w3.event("fotz_own/killer") is None and w3.env.S.own == "u2",
          "another faction took over the last one's relations")
    got = {c: w3.rel(c) for c in OWN_CELLS}
    check(got == {c: OWN_BASE[c] for c in OWN_CELLS}, "another faction's cells: %s" % got)

    # disbanded: what was kept for it goes, and your kills count for Duty again
    w2.run("fotz_faction.F = nil")
    w2.env.apply()
    left = [k for t in ("drift", "pending", "events", "recent", "last_fight") for k in w2.env.S[t].keys() if "fotz_own" in k]
    check(not left and not any(w2.env.PAIRS[i].own for i in range(1, len(w2.env.PAIRS) + 1)),
          "after disbanding: %s" % left)
    w2.run('kill("killer", "actor", "novice", 1)')
    check(w2.env.S.kills["dolg/killer"] == 0.5, "after disbanding, your kill counted %s for Duty" % w2.env.S.kills["dolg/killer"])


def members_amp(src):
    """members from a faction move your faction's pair with it more, either way round, and no other
    pair: fotz_perks.amp_all (wherever the members are), here 1.5 for the Mercenaries and 2 for Duty"""
    w = World(src, anchors=DK_ANCHORS, pre=led_lua(mother="stalker") +
              '\nfotz_perks = { amp_all = function(f) return ({ killer = 1.5, dolg = 2 })[f] or 1 end }')
    w.run('day("2012-05-01")')
    w.run('kill("killer", "fotz_own", "veteran", 30)')
    w.run('kill("dolg", "fotz_own", "novice", 30)')
    w.run('kill("killer", "dolg", "novice", 30)')
    keys = {w.env.PAIRS[i].key for i in range(1, len(w.env.PAIRS) + 1)}
    duty = "dolg/fotz_own" if "dolg/fotz_own" in keys else "fotz_own/dolg"
    k0 = {k: w.env.S.kills[k] for k in ("fotz_own/killer", duty, "dolg/killer")}
    w.run('day("2012-05-02")')
    got = {k: w.env.S.pending[k] for k in ("fotz_own/killer", duty, "dolg/killer")}
    want = {}
    for k, amp in (("fotz_own/killer", 1.5), (duty, 2), ("dolg/killer", 1)):
        cfg = w.env.cfg
        p = max(-cfg.pending_max, cfg.kill * k0[k] * amp)
        move = max(p, -cfg.daily_budget)
        want[k] = (p - move) or None
    check(got == want, "pending after a day: %s, not %s (kills %s)" % (got, want, k0))


def encroached(src):
    """your members on others' ground strain your faction's pair with each holder: fotz_territory's
    day's push lands on the pair, as ground, and an error there costs nothing else"""
    w = World(src, anchors=DK_ANCHORS, pre=led_lua(mother="stalker") +
              '\nfotz_territory = { encroachment = function(c) return { killer = -40, dolg = -10, monolith = -5 } end }')
    w.run('day("2012-05-01")')
    w.run('day("2012-05-02")')
    keys = {w.env.PAIRS[i].key for i in range(1, len(w.env.PAIRS) + 1)}
    duty = "dolg/fotz_own" if "dolg/fotz_own" in keys else "fotz_own/dolg"
    got = (w.drift("fotz_own/killer"), w.drift(duty))
    check(got == (-40, -10), "the pairs after a day of strain: %s" % (got,))
    w = World(src, anchors=DK_ANCHORS, pre=led_lua(mother="stalker") +
              "\nfotz_territory = { encroachment = function(c) error('boom') end }")
    w.run('day("2012-05-01")')
    w.run('day("2012-05-02")')
    check(w.drift("fotz_own/killer") is None and any("! encroachment" in l for l in w.g.LOG.values()), "a failing strain")


SETTLED_NEWS = "killer|Mercenaries: Wolves settled on our ground and stayed. From today we are at war with them."


def settled_war(src):
    """a war your members' settling causes has its own cause and news, in the voice of the faction
    whose ground it is, whichever way the pair's names sort (Duty before your faction's, the
    Mercenaries after); a 0.6.0 save, which kept the strain as ground with no place, names it so too"""
    strain = "\nfotz_territory = { encroachment = function(c) return { killer = STRAIN, dolg = STRAIN } end }\nSTRAIN = -400"
    w = World(src, anchors=DK_ANCHORS, pre=led_lua(mother="stalker") + strain)
    for d in ("01", "02", "03"):
        w.run('day("2012-05-%s")' % d)
    check(w.event("fotz_own/killer") is None, "war a day early: drift %s" % w.drift("fotz_own/killer"))
    w.run('day("2012-05-04")')
    h = w.env.S.history
    wars = [(h[i].a, h[i].b, h[i].cause, h[i].voice) for i in range(1, len(h) + 1) if h[i].kind == "war"]
    check(wars == [("dolg", "fotz_own", "settled", "dolg"), ("fotz_own", "killer", "settled", "killer")],
          "the wars: %s" % wars)
    check(w.news() == ["dolg|Duty: Wolves settled on our ground and stayed. From today we are at war with them.",
                       SETTLED_NEWS], "the wars' news: %s" % w.news())
    # a 0.6.0 save: the strain kept as ground, no place; a little more strain tips it into war
    saved = ('{ fotz = { v = 1, own = "u1", day = "2012-05-09", drift = { ["fotz_own/killer"] = -700 }, '
             'pending = { ["fotz_own/killer"] = -400 }, recent = { ["fotz_own/killer"] = { ground = 800, hurt = {} } } } }')
    w = World(src, anchors=DK_ANCHORS, m_data=saved, pre=led_lua(mother="stalker") + strain.replace("-400", "-40"))
    w.run('day("2012-05-10")')
    check(w.event("fotz_own/killer") == "war" and w.news() == [SETTLED_NEWS],
          "after a 0.6.0 save: %s, news %s" % (w.event("fotz_own/killer"), w.news()))


def parked(src):
    """a faction parked (its save loaded without the declaration: fotz_faction.parked_uid) keeps
    what politics kept for it through the next save, for an install that can restore it; a faction
    founded meanwhile starts clean"""
    saved = ('{ fotz = { v = 1, own = "u1", day = "2012-05-09", drift = { ["fotz_own/killer"] = -300 }, '
             'events = { ["fotz_own/killer"] = { kind = "truce", since = "2012-05-08", a = "fotz_own", b = "killer", '
             '["until"] = "2012-05-13" } } } }')
    w = World(src, anchors=DK_ANCHORS, m_data=saved,
              pre='fotz_faction = { F = nil, parked_uid = function() return "u1" end }')
    w.run('day("2012-05-10")')
    m = w.lua.eval("{}")
    w.cb["save_state"](m)
    check(m.fotz.own == "u1" and m.fotz.drift["fotz_own/killer"] == -300 and m.fotz.events["fotz_own/killer"] is not None,
          "parked, the save kept: own %s, drift %s" % (m.fotz.own, m.fotz.drift["fotz_own/killer"]))
    check(not any("fotz_own" in c for c in w.g.WRITES.values()), "a parked faction's cells were written")
    w2 = World(src, anchors=DK_ANCHORS, m_data=w.lua.eval("dump")(m), pre=led_lua("u1"))
    got = {c: w2.rel(c) for c in OWN_CELLS}
    check(got == {c: OWN_BASE[c] - 300 for c in OWN_CELLS} and w2.event("fotz_own/killer") == "truce",
          "restored: %s, %s" % (got, w2.event("fotz_own/killer")))
    w3 = World(src, anchors=DK_ANCHORS, m_data=saved,
               pre=led_lua("u2") + '\nfotz_faction.parked_uid = function() return "u1" end')
    check(w3.drift("fotz_own/killer") is None and w3.event("fotz_own/killer") is None and w3.env.S.own == "u2",
          "a new faction took the parked one's: drift %s, own %s" % (w3.drift("fotz_own/killer"), w3.env.S.own))


def old_fixed(src):
    """Your old faction's fixed relations stay fixed for yours: no pair with a faction your old one
    has a lore pair with, none at all from a faction that never changes. What a 0.5.0 save kept for
    such a pair (a truce with Freedom) goes at the load, and its cells stay at the founding values;
    the rest is kept."""
    w = World(src, anchors=DK_ANCHORS, pre=led_lua())
    check(w.env.pair_of("fotz_own", "freedom") is None and w.env.pair_of("fotz_own", "killer") is not None,
          "pairs with Freedom and the Mercenaries: %s, %s" % (w.env.pair_of("fotz_own", "freedom"), w.env.pair_of("fotz_own", "killer")))
    check(w.env.fixed_for_own("actor_dolg", "freedom") is True and w.env.fixed_for_own("dolg", "killer") is False,
          "fixed_for_own: %s, %s" % (w.env.fixed_for_own("actor_dolg", "freedom"), w.env.fixed_for_own("dolg", "killer")))
    w2 = World(src, anchors=DK_ANCHORS, pre=led_lua(mother="monolith"))
    own = [p.key for p in w2.env.PAIRS.values() if p.own]
    check(not own, "a faction founded from the Monolith moves: %s" % own)
    # a 0.5.0 save: its pair with Freedom in a truce, its pair with the Mercenaries moved
    saved = ('{ fotz = { v = 1, own = "u1", drift = { ["fotz_own/freedom"] = -900, ["fotz_own/killer"] = -100 }, '
             'pending = { ["fotz_own/freedom"] = 50 }, kills = { ["fotz_own/freedom"] = 3 }, hurt = {}, recent = {}, '
             'last_fight = { ["fotz_own/freedom"] = "2012-05-01" }, history = {}, trend = { ["fotz_own/freedom"] = 300 }, '
             'events = { ["fotz_own/freedom"] = { kind = "truce", since = "2012-05-02", a = "fotz_own", b = "freedom" } } } }')
    w3 = World(src, anchors=DK_ANCHORS, pre=led_lua(), m_data=saved)
    left = [(t, k) for t in ("drift", "pending", "kills", "last_fight", "events", "trend") for k in w3.env.S[t].keys() if "freedom" in k]
    check(not left, "what the save kept for the fixed pair: %s" % left)
    check(w3.drift("fotz_own/killer") == -100, "the Mercenaries' drift: %s" % w3.drift("fotz_own/killer"))
    check(not any(c in list(w3.g.WRITES.values()) for c in ("fotz_own>freedom", "freedom>fotz_own", "freedom>actor_fotz_own")),
          "Freedom's cells written")


def restore(src):
    # the Factions tab's "Restore relations": every pair back at its start, events ended, mid-save
    w = World(src, anchors=DK_ANCHORS)
    w.run('day("2012-05-01")')
    w.run('kill("dolg", "killer", "veteran", 200)')
    for d in ("02", "03", "04"):
        w.run('day("2012-05-%s")' % d)
    check(w.event("dolg/killer") == "war", "no war to end: %s" % w.event("dolg/killer"))
    n = w.env.restore()
    check(n > 0 and all(w.rel(c) == DK_ANCHORS[c] for c in CELLS), "restored cells: %s" % {c: w.rel(c) for c in CELLS})
    check(w.drift("dolg/killer") is None and w.pending("dolg/killer") is None and w.event("dolg/killer") is None,
          "restore left drift %s, pending %s, event %s" % (w.drift("dolg/killer"), w.pending("dolg/killer"), w.event("dolg/killer")))
    check(w.history()[-1] == "restored", "history %s" % w.history())
    check(w.env.S.trend["dolg/killer"] is None, "restore left a trend: %s" % w.env.S.trend["dolg/killer"])
    w.run('day("2012-05-05")')
    check(w.drift("dolg/killer") is None, "the next day moved a restored pair: %s" % w.drift("dolg/killer"))


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
    want |= {"st_fotz_news_war_" + c for c in ("kills", "ground", "front", "settled")}
    check(len(want) == 11, "%d news ids were looked for, not 11" % len(want))
    mcm = open(os.path.join(GD, "scripts", "fotz_mcm.script"), encoding="utf-8").read()
    opts = re.findall(r'id = "(\w+)", type = "(?:check|list|track)"', mcm)
    for opt in opts:
        want |= {"ui_mcm_fotz_" + opt, "ui_mcm_fotz_" + opt + "_desc"}
    lists = re.findall(r'\{ "\w+", "(fotz_news_\w+)" \}', mcm)
    want |= {"ui_mcm_lst_" + k for k in lists}
    # the MCM page's options are the page's to change: only that they were found
    check(len(opts) >= 15 and len(lists) == 3, "%d MCM options and %d list items found" % (len(opts), len(lists)))
    want |= {"st_fotz_faction_" + f for f in ("stalker", "bandit", "csky", "dolg", "freedom", "killer", "army",
                                              "ecolog", "monolith", "renegade", "greh", "isg")}
    missing = sorted(want - have)
    check(not missing, "string ids missing from the English table: %s" % missing)


HOOKS_LUA = ('SENT = {}\n'
             'fotz_api = { send = function(name, t) SENT[#SENT + 1] = { name = name, t = t } end }')


def py(v):
    """A Lua value as Python: a table with keys 1..n as a list, any other as a dict."""
    if L.lua_type(v) != "table":
        return v
    keys = list(v.keys())
    if keys and sorted(k for k in keys if isinstance(k, int)) == list(range(1, len(keys) + 1)):
        return [py(v[i]) for i in range(1, len(keys) + 1)]
    return {k: py(v[k]) for k in keys}


def sent(w, name):
    s = w.g.SENT
    return [py(s[i].t) for i in range(1, len(s) + 1) if s[i].name == name]


def hooks(src):
    """Other mods hear of each war, truce and alliance, and why it ended; of every smart one faction
    took from another, counted or not; and their grievances and places of interest weigh in
    (fotz_api, docs/HOOKS.md)."""
    w = World(src, anchors=DK_ANCHORS, pre=HOOKS_LUA)
    w.run('day("2012-05-01")')
    w.run('kill("dolg", "killer", "veteran", 60)')
    for d in range(2, 13):
        w.run('day("2012-05-%02d")' % d)
    pair = {"a": "dolg", "b": "killer"}
    want = [dict(pair, kind="war", day="2012-05-04", cause="kills", voice="dolg"),
            dict(pair, kind="war_over", day="2012-05-07", since="2012-05-04", why="truce"),
            dict(pair, kind="truce", day="2012-05-07", voice="dolg", **{"until": "2012-05-12"}),
            dict(pair, kind="truce_over", day="2012-05-12", since="2012-05-07", why="expired")]
    got = sent(w, "fotz_on_politics")
    check(got == want, "the war's callbacks: %s" % got)
    # MCM's reset, and another script setting the pair, end an event too
    w.env.S.events["dolg/killer"] = w.lua.eval('{ kind = "war", since = "2012-05-12", a = "dolg", b = "killer" }')
    w.env.restore()
    got = sent(w, "fotz_on_politics")[4:]
    check(got == [dict(pair, kind="war_over", day="2012-05-12", since="2012-05-12", why="reset")], "the reset: %s" % got)
    w.env.S.events["dolg/killer"] = w.lua.eval('{ kind = "war", since = "2012-05-12", a = "dolg", b = "killer" }')
    w.run('REL["dolg>killer"] = 777')
    w.cb["on_option_change"]()
    got = sent(w, "fotz_on_politics")[5:]
    check(got == [dict(pair, kind="war_over", day="2012-05-12", since="2012-05-12", why="changed")],
          "a change by another script: %s" % got)

    # every smart taken between two factions, whether politics counts the pair or not; never one
    # abandoned; and on while politics stands down, where nothing counts
    w = World(src, pre=HOOKS_LUA)
    w.run('day("2012-05-01", { s1 = "freedom", s2 = "freedom", s3 = "monolith", s4 = "dolg" })')
    w.run('day("2012-05-02", { s1 = "killer", s3 = "freedom", s4 = "freedom" })')
    base = {"date": "2012-05-02 08:00", "weight": 1}
    want = [dict(base, smart="s1", place="Place s1", by="killer", **{"from": "freedom", "counted": True}),
            dict(base, smart="s3", place="Cordon", by="freedom", **{"from": "monolith", "counted": False}),
            dict(base, smart="s4", place="Cordon", by="freedom", **{"from": "dolg", "counted": False})]
    got = sent(w, "fotz_on_ground_taken")
    check(got == want, "ground taken: %s" % got)
    w.run('MCM["fotz/politics"] = false')
    w.run('day("2012-05-03", { s1 = "freedom", s3 = "freedom", s4 = "freedom" })')
    got = sent(w, "fotz_on_ground_taken")[3:]
    check(got == [{"date": "2012-05-03 08:00", "weight": 1, "smart": "s1", "place": "Place s1", "by": "freedom",
                   "from": "killer", "counted": False}], "ground taken while standing down: %s" % got)
    check(w.env.grievance("dolg", "killer", -500) is False, "a grievance counted while standing down")

    # grievances: refused for pairs Factions doesn't follow; a war they cause names its cause, its
    # place and the mod's own news, or Factions' with or without a place; goodwill moves a pair up
    w = World(src, anchors=DK_ANCHORS, pre=HOOKS_LUA)
    w.run('STR["st_test_war"] = "{b} burned our stash at {place}."')
    w.run('day("2012-05-01")')
    opts = w.lua.eval
    check(w.env.grievance("dolg", "killer", -1500, opts('{ at = "s1", news = "st_test_war" }')) is True and
          w.env.grievance("freedom", "killer", -1500, opts('{ at = "s1" }')) is True and
          w.env.grievance("csky", "killer", -1500) is True and w.env.grievance("bandit", "stalker", 300) is True,
          "a grievance refused")
    for a, b, amount in (("dolg", "freedom", -500), ("monolith", "dolg", -500), ("dolg", "killer", 0), ("dolg", "killer", "x")):
        check(w.env.grievance(a, b, amount) is False, "a grievance counted: %s %s %s" % (a, b, amount))
    w.run('day("2012-05-02")')
    check(w.pending("dolg/killer") == -1100 and w.drift("bandit/stalker") == 300,
          "day 2: pending %s, goodwill drift %s" % (w.pending("dolg/killer"), w.drift("bandit/stalker")))
    w.run('day("2012-05-03")')
    check(w.pending("dolg/killer") == -700, "day 3: pending %s (a grievance counted twice?)" % w.pending("dolg/killer"))
    w.run('day("2012-05-04")')
    wars = {e["a"]: e for e in sent(w, "fotz_on_politics") if e["kind"] == "war"}
    check(set(wars) == {"csky", "dolg", "freedom"} and all(e["cause"] == "incident" for e in wars.values())
          and wars["dolg"].get("at") == "s1" and wars["dolg"].get("place") == "Place s1" and "at" not in wars["csky"],
          "the wars grievances made: %s" % wars)
    news = w.news()
    for line in ("dolg|Duty: Mercenaries burned our stash at Place s1.",
                 "freedom|Freedom: Mercenaries crossed us at Place s1 once too often. From today we are at war with them.",
                 "csky|Clear Sky: Mercenaries crossed us once too often. From today we are at war with them."):
        check(line in news, "no news %r in %s" % (line, news))

    # places of interest: the config's, clamped; another mod's, clamped, over the config's, and
    # cleared; ground and fronts there weigh more, a front is named by its heaviest place, and every
    # place taken makes the news
    w = World(src, pre=HOOKS_LUA, config=TEST_CONFIG + "[places]\ns7 = 2\ns8 = 9\ns9 = x\n")
    e = w.env
    check((e.place_weight("s7"), e.place_weight("s8"), e.place_weight("s9"), e.place_weight("s1")) == (2, 3, 1, 1),
          "the config's places: %s" % [e.place_weight(s) for s in ("s7", "s8", "s9", "s1")])
    check(e.set_place("s2", 0.5) is True and e.set_place("s3", 5) is True and e.set_place("", 2) is False
          and e.set_place("s7", 3) is True, "set_place refused")
    check((e.place_weight("s2"), e.place_weight("s3"), e.place_weight("s7")) == (1, 3, 3),
          "set places: %s" % [e.place_weight(s) for s in ("s2", "s3", "s7")])
    check(e.clear_place("s3") is True and e.place_weight("s3") == 1 and e.clear_place("s3") is False
          and e.clear_place("s7") is True and e.place_weight("s7") == 2 and e.clear_place("s8") is False,
          "clear_place: %s" % [e.place_weight(s) for s in ("s3", "s7", "s8")])
    check(e.set_place("s5", 2) is True and e.place_weight("s2") == 1, "a place")
    held = '{ s1 = "%s", s2 = "%s", s3 = "%s", s4 = "%s", s5 = "%s" }'
    w.run('MCM["fotz/news"] = "all"')
    w.run('day("2012-05-01", %s)' % (held % (("freedom",) * 5)))
    w.run('day("2012-05-02", %s)' % (held % (("killer",) * 5)))
    check(w.pending("freedom/killer") == -500, "ground at a place: pending %s" % w.pending("freedom/killer"))
    took = [n for n in w.news() if "We took" in n]
    check(len(took) == 4, "ground news with a place: three a day and the place: %s" % took)
    w.run('day("2012-05-03", %s, { ["freedom/killer"] = { n = 2, at = "s1", smarts = { "s1", "s5" } } })'
          % (held % (("killer",) * 5)))
    check(w.pending("freedom/killer") == -220 and w.env.S.recent["freedom/killer"].front_at == "s5",
          "a front at a place: pending %s, named %s" % (w.pending("freedom/killer"), w.env.S.recent["freedom/killer"].front_at))

    # disbanding ends your faction's events, and other mods hear why
    w = World(src, anchors=DK_ANCHORS, pre=led_lua() + "\n" + HOOKS_LUA)
    w.env.S.events["fotz_own/killer"] = w.lua.eval('{ kind = "war", since = "2012-05-04", a = "fotz_own", b = "killer" }')
    w.run("fotz_faction.F = nil")
    w.env.apply()
    got = [(e["kind"], e["a"], e["b"], e.get("since"), e.get("why")) for e in sent(w, "fotz_on_politics")]
    check(got == [("war_over", "fotz_own", "killer", "2012-05-04", "disbanded")], "disbanding: %s" % got)


def run(src):
    strings(src)
    w = war_and_truce(src)
    ground_and_news(src)
    alliance(src)
    stand_down(src)
    save_and_load(src, w)
    kills(src)
    your_faction(src)
    members_amp(src)
    encroached(src)
    settled_war(src)
    parked(src)
    old_fixed(src)
    restore(src)
    caps(src)
    real_config(src)
    other_scripts(src)
    calendar(src)
    hooks(src)
    return "18 scenarios, 16 pairs from the shipped config"


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
