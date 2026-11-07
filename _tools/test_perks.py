"""Run fotz_perks.script under LuaJIT 2.0 against stand-ins for the game's trade callback, Fair Fast
Travel, the paid companions, Milspec PDA, Dialogues Expanded's radio, Factions' faction and
politics, MCM and the clock, and check the perks.

Checked: a perk is on while a living member came from that faction and your faction isn't at war
with it (a truce or no pair at all is no war), off with the faction gone, the member dead, the war
on or MCM's switch off, and seen again within the cache's time; each scaled perk grows by the
steps of its members' ranks with positive returns, its cap times (steps / full) ^ curve, full being
Homestead's cap on a camp's residents (the config's without Homestead or below 1); members count by
how near their level is to yours on the global map (an online member is on yours, an unplaced level
counts half), and politics' amplifier by every member wherever they are (online or offline; an unreadable rank a professional's; the config's
weights), up to its cap; buying (never selling) a faction's own goods from its
trader costs that much less, on top of every other mod's price, by the item's kind or a section
prefix, at a trader Factions' trader table names (Sidorovich) or by their own faction, and only
while the trade window is open; the [perks] config's steps, caps and goods are read; the
Military's airlifts cost less and no other guide's, through one wrapper that passes every argument
on; merc squads of advanced or veteran fighters take a contract the game's roll refused at the
perk's chance, each squad's roll kept so the dialog's checks agree, novices and other factions'
squads never; Bandit squads show on a PDA that shows allies unless the faction is blacklisted, and
no other faction's; Monolith's, Sin's and the ISG's radio channels open with their perk and close
after it, never a channel the game opened, and not before the radio starts after a load; the
Renegades' outpost bonus; each perk's percent for the page; members from a faction move your
goodwill with it more, for better or worse, at war or not, never compounding, a story-sized jump
and the first look after a load left alone, up to the relations cap or its slider.

    python test_perks.py            the real script
    python test_perks.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import sys

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "gamedata", "scripts", "fotz_perks.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "gate_dead": ("if f and PERKS[f] and not m.dead then", "if f and PERKS[f] then"),
    "gate_war": ("                if not at_war(f) then\n                    t[f] = t[f] or", "                if true then\n                    t[f] = t[f] or"),
    "gate_truce_is_war": ('return ev ~= nil and ev.kind == "war"', "return ev ~= nil"),
    "gate_mcm": ('return not (ui_mcm and ui_mcm.get("fotz/perks") == false)', "return true"),
    "gate_actor_prefix": ('string.gsub(m.mother, "^actor_", "")', "m.mother"),
    "gate_stale": ("if cache and now >= cache_at and now < cache_at + CACHE_MS then", "if cache then"),
    "trade_selling": ("profile.mode == 2 and type(ret)", "profile.mode ~= nil and type(ret)"),
    "trade_any_goods": ("if goods_of(obj:section()) ~= PERKS[f] or not on(f) then", "if goods_of(obj:section()) == nil or not on(f) then"),
    "trade_overwrites": ("local c = tonumber(ret.new_cost) or tonumber(cost)", "local c = tonumber(cost)"),
    "trade_no_table": ("    if who and type(T) == \"table\" then", "    if false then"),
    "trade_no_prefix": ("                    if string.sub(sec, 1, #p) == p then", "                    if false then"),
    "trade_kept_open": ("function trade_closed()\n    trade = nil", "function trade_closed()\n    trade = trade"),
    "trade_no_config": ("                v = ini:r_float_ex(\"perks\", key)", "                v = nil"),
    "airlift_any_guide": ("if AIRLIFTS[g] and type(v) == \"number\"", "if type(v) == \"number\""),
    "airlift_twice": ("if not original_fare and type(g) == \"table\"", "if type(g) == \"table\""),
    "airlift_args": ("local v = original_fare(g, s, ...)", "local v = original_fare(g, s)"),
    "mercs_novices": ("\n            and (string.find(sec, \"veteran\", 1, true) or string.find(sec, \"advanced\", 1, true))) then",
                      ") then"),
    "mercs_any_faction": ("if not (squad and who:character_community() == \"killer\"", "if not (squad and true"),
    "mercs_reroll": ("local roll = merc_rolls[squad.id] or math.random(1, 100)", "local roll = math.random(1, 100)"),
    "near_ignored": ("                local near = w * nearness(member_level(id), here)", "                local near = w"),
    "near_nowhere": ("        local here = level.name()", "        local here = nil"),
    "near_unknown_full": ("        return cfg.near_unknown\n", "        return 1\n"),
    "near_online_ignored": ("        if level.object_by_id(id) then\n            return level.name()\n        end\n", ""),
    "near_corner": ("            p = { x = (tonumber(x1) + tonumber(x2)) / 2, y = (tonumber(y1) + tonumber(y2)) / 2 }",
                    "            p = { x = tonumber(x1), y = tonumber(y1) }"),
    "size_everywhere": ("    return max * share(near_weight(f))", "    return max * share(weight(f))"),
    "amp_everywhere": ('return 1 + cap("relations", cfg.relations_max) * share(steps_all[f])\nend\n\n-- the same',
                       'return 1 + cap("relations", cfg.relations_max) * share(steps_total[f])\nend\n\n-- the same'),
    "amp_all_here": ('return 1 + cap("relations", cfg.relations_max) * share(steps_total[f])\nend\n\nfunction on(f)',
                     'return 1 + cap("relations", cfg.relations_max) * share(steps_all[f])\nend\n\nfunction on(f)'),
    "curve_straight": ("    return math.min(1, w / (full_now or full())) ^ cfg.curve", "    return math.min(1, w / (full_now or full()))"),
    "curve_past_full": ("    return math.min(1, w / (full_now or full())) ^ cfg.curve", "    return (w / (full_now or full())) ^ cfg.curve"),
    "full_no_homestead": ("    return (ok and n and n >= 1) and n or cfg.full_steps", "    return cfg.full_steps"),
    "full_zero": ("    return (ok and n and n >= 1) and n or cfg.full_steps", "    return (ok and n) and n or cfg.full_steps"),
    "slider_ignored": ('local v = s and ui_mcm and tonumber(ui_mcm.get("fotz/" .. s[1]))', "local v = nil"),
    "slider_scale": ("        return math.max(0, v / s[2])", "        return math.max(0, v)"),
    "merc_past_100": ('math.min(100, cap("mercs", cfg.merc_max))', 'cap("mercs", cfg.merc_max)'),
    "caps_unshipped": ("merc_max = 100, outpost_max = 15, relations_max = 1.00,",
                       "merc_max = 100, outpost_max = 10, relations_max = 1.00,"),
    "rank_ignored": ("t[f].weight = t[f].weight + w", "t[f].weight = t[f].weight + 1"),
    # relations, for better or worse
    "amp_war_gated": ("                all[f] = (all[f] or 0) + near\n                total[f] = (total[f] or 0) + w\n"
                      "                if not at_war(f) then\n",
                      "                if not at_war(f) then\n                all[f] = (all[f] or 0) + near\n"
                      "                total[f] = (total[f] or 0) + w\n"),
    "amp_ignores_members": ('return 1 + cap("relations", cfg.relations_max) * share(steps_all[f])',
                            'return 1 + cap("relations", cfg.relations_max)'),
    "goodwill_compounds": ("                    now[f] = rr.community_goodwill(f, AC_ID)\n", ""),
    "goodwill_first_look": ("    if goodwill then\n        for _, f in ipairs(ORDER) do\n            local d = now[f] - (goodwill[f] or now[f])",
                            "    if true then\n        for _, f in ipairs(ORDER) do\n            local d = now[f] - ((goodwill or {})[f] or 0)"),
    "goodwill_jumps": ("local a = d ~= 0 and math.abs(d) <= cfg.goodwill_jump and amp(f) or 1", "local a = d ~= 0 and amp(f) or 1"),
    "goodwill_one_way": ("extra = extra > 0 and math.floor(extra + 0.5) or -math.floor(-extra + 0.5)",
                         "extra = math.max(0, math.floor(extra + 0.5))"),
    "rank_offline_ignored": ("        return se and ranks.get_se_obj_rank_name(se)", "        return nil"),
    "rank_unknown_zero": ("return WEIGHTS[rank_name(id)] or WEIGHTS[RANKS[UNKNOWN_RANK]] or 1", "return WEIGHTS[rank_name(id)] or 0"),
    "rank_unguarded": ("    local ok, name = pcall(function()\n        local o = level.object_by_id(id)",
                       "    local ok, name = (function(f) return true, f() end)(function()\n        local o = level.object_by_id(id)"),
    "level_unguarded": ("    local ok, name = pcall(function()\n        if level.object_by_id(id) then",
                        "    local ok, name = (function(f) return true, f() end)(function()\n        if level.object_by_id(id) then"),
    "rank_no_config": ("        if RANKS[i] and tonumber(w) then", "        if false then"),
    "map_any_faction": ('return comm == "bandit" and on("bandit")', 'return on("bandit")'),
    "map_blacklist": ('    if m.is_blacklisted("bandit") then\n        return false\n    end\n', ""),
    "radio_closes_game_channel": ("        elseif radio_on[f] then", "        else"),
    "radio_early": ("if radio_from and now >= radio_from then", "if radio_from then"),
    "renegade_other": ('    return size("renegade")', '    return size("bandit") or 0'),
    "pct_all_shares": ('((GOODS[perk] or perk == "airlift") and s * 100 or s)', "(s * 100)"),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end

CALLBACKS = {}
function RegisterScriptCallback(name, fn)
    CALLBACKS[name] = CALLBACKS[name] or {}
    table.insert(CALLBACKS[name], fn)
end
function fire(name, ...)
    for _, fn in ipairs(CALLBACKS[name] or {}) do
        fn(...)
    end
end

NOW = 100000
function time_global() return NOW end
function wait(ms) NOW = NOW + ms end

OPTIONS = {}
ui_mcm = { get = function(k) return OPTIONS[k] end }

-- the [perks] config: nil until a test sets one
INI = nil
function ini_file(name)
    if not INI then return nil end
    return {
        section_exist = function(self, s) return INI[s] ~= nil end,
        line_exist = function(self, s, k) return INI[s] ~= nil and INI[s][k] ~= nil end,
        r_float_ex = function(self, s, k) return tonumber(INI[s][k]) end,
        r_string_ex = function(self, s, k) return INI[s][k] end,
    }
end

-- each section's kind, as the game's configs give it
KINDS = { mutant_part_dog_tail = "i_mutant_part", mutant_part_flesh_meat = "i_mutant_raw", bread = "i_food",
          vodka = "i_drink", medkit = "i_medical", gun_oil_ru = "i_misc", toolkit_2 = "i_quest",
          sewing_kit_a = "i_repair", prt_w_barrel_1 = "i_part", wpn_ak74 = "w_rifle" }
function SYS_GetParam(typ, sec, key) if key == "kind" then return KINDS[sec] end end

-- each faction's goodwill toward you, as the game keeps it
AC_ID = 0
GW, GW_CHANGES = {}, 0
relation_registry = {
    community_goodwill = function(f, id) assert(id == AC_ID) return GW[f] or 0 end,
    change_community_goodwill = function(f, id, d) assert(id == AC_ID) GW[f] = (GW[f] or 0) + d; GW_CHANGES = GW_CHANGES + 1 end,
}

-- where you are and where members are: online members are on your level; an offline member's
-- server object is on game vertex 1 (your level, Yantar) unless a test says otherwise
HERE = "l08_yantar"
ONLINE, SE = {}, {}
VERTEX_LEVEL = { [1] = 8, [2] = 11, [3] = 1, [4] = 99, [5] = 6 }
LEVEL_NAME = { [8] = "l08_yantar", [11] = "l11_pripyat", [1] = "l01_escape", [99] = "y04_nowhere", [6] = "l06_rostok" }
level = { object_by_id = function(id) return ONLINE[id] end, name = function() return HERE end }
function alife() return {
    object = function(self, id)
        local member = fotz_faction.F and fotz_faction.F.members[id]
        local se = SE[id] or (member and {})
        if se and not se.m_game_vertex_id then
            se.m_game_vertex_id = member and member.gv or 1
        end
        return se
    end,
    level_name = function(self, lid) return LEVEL_NAME[lid] end,
} end
function game_graph() return { vertex = function(self, gv)
    return { level_id = function() if gv == 666 then error("no such vertex") end return VERTEX_LEVEL[gv] end }
end } end
-- the global map's rectangles (game.ltx)
RECTS = { l08_yantar = "101.0, 1572.0, 249.0, 1720.000000", l11_pripyat = "607.0,762.0,740.0,909.0",
          l01_escape = "358.0, 2022.0, 564.0, 2434.000000", l06_rostok = "258.0,1414.0,407.0,1712" }
function game_ini() return { r_string_ex = function(self, s, k) assert(k == "global_rect") return RECTS[s] end } end
ranks = {
    get_obj_rank_name = function(o) if o.broken then error("no rank") end return o.rank end,
    get_se_obj_rank_name = function(se) return se.rank end,
}

-- Factions: the faction you lead, its members, and politics' events
fotz_faction = { F = nil }
function lead(members) fotz_faction.F = { name = "Wolves", members = members } end
PAIRS = { freedom = { key = "fotz_own/freedom" }, dolg = { key = "fotz_own/dolg" },
          stalker = { key = "fotz_own/stalker" }, killer = { key = "fotz_own/killer" } }
fotz_politics = { OWN = "fotz_own", S = { events = {} },
    pair_of = function(x, y) return x == "fotz_own" and PAIRS[y] or nil end }

-- traders, and the trade window
modxml_fotz_patch = { TRADERS = { stalker = { "esc_2_12_stalker_trader" }, dolg = { "bar_dolg_general_petrenko_stalker" } } }
function npc(comm, profile, squad_sec, squad_id)
    return { character_community = function() return comm end,
             profile_name = function() return profile end, squad_sec = squad_sec, squad_id = squad_id }
end
TALKING = nil
mob_trade = { GetTalkingNpc = function() return TALKING end }
function get_object_squad(o)
    return o and o.squad_sec and { id = o.squad_id or 0, section_name = function() return o.squad_sec end,
                                   get_squad_community = function() return o.squad_comm end } or nil
end
-- the rolls: what math.random gives next
NEXT_ROLL = 50
math.random = function() return NEXT_ROLL end
-- n members from faction f, besides any already there
ADDED = 0
function add(f, n, gv)
    for i = 1, n do
        ADDED = ADDED + 1
        fotz_faction.F.members[5000 + ADDED] = { mother = f, name = f .. " " .. ADDED, gv = gv }
    end
    return 5000 + ADDED
end
function obj(sec) return { section = function() return sec end } end
-- a price as the game's get_item_cost has it: other listeners may have set ret.new_cost first
function price(sec, mode, cost, before)
    local ret = { new_cost = before }
    fire("on_get_item_cost", "condition_based", obj(sec), { mode = mode }, cost, ret)
    return ret.new_cost
end

-- Fair Fast Travel: a fare a guide's route; the fourth argument must arrive
game_guide_travel = { get_guidespot_fare = function(g, s, x, y)
    if x ~= "x" or y ~= "y" then error("arguments lost") end
    return ({ esc_3_16_military_trader = 5000, mil_freedom_guid = 4500 })[g] or 0
end }

-- the paid companions: the game's roll refuses every squad here
dialogs = { who_is_npc = function(actor, n) return n end }
ROLLED = false
txr_paid_companions = { is_squad_competent = function(actor, n) return ROLLED end }

-- Milspec PDA: no faction is shown by the game's own rules here
PDA_ALLIES, BLACKLIST = true, {}
item_milpda = {
    actor_pda_can_see_mapspot = function(comm) return false end,
    is_blacklisted = function(comm) return BLACKLIST[comm] == true end,
    pda_type_supports_mapspot = function(pdata, comm, ally, enemy) return (PDA_ALLIES and ally) or nil end,
}

-- Dialogues Expanded's radio: the manager is made on its first ask
MADE = 0
CHANNELS = nil
dynamic_news_manager = { get_dynamic_news = function()
    if not CHANNELS then
        MADE = MADE + 1
        CHANNELS = { channel_status = { monolith = false, greh = true, isg = false, stalker = true } }
    end
    return CHANNELS
end }
"""


FULL, CURVE = 15, 1.5
CENTERS = {"yantar": (175.0, 1646.0), "pripyat": (673.5, 835.5), "cordon": (461.0, 2228.0), "rostok": (332.5, 1563.0)}


def nearness(a, b, half=300.0):
    """how much a member on level a counts on level b"""
    (ax, ay), (bx, by) = CENTERS[a], CENTERS[b]
    return 1 / (1 + ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 / half)


def share(w, full=FULL, curve=CURVE):
    """the share of a cap that w steps give"""
    return min(1, w / full) ** curve if w > 0 else 0


def near(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) < tol


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


class World:
    def __init__(self, src, setup=""):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(WORLD)
        self.lua.execute(setup)
        self.env = self.lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                                 "local f = assert(loadstring(src, 'fotz_perks')) setfenv(f, env) f() return env end")(src)
        self.lua.globals().fotz_perks = self.env
        self.env.on_game_start()

    def run(self, code):
        self.lua.execute(code)

    def eval(self, code):
        return self.lua.eval(code)

    def on(self):
        """the factions whose perk is on, after the cache"""
        self.run("wait(5000)")
        t = self.env.active()
        return sorted(t.keys())


def gate(src):
    w = World(src)
    check(w.on() == [], "perks without a faction")
    w.run('lead({ [1] = { mother = "freedom", name = "Vova" }, [2] = { mother = "freedom", name = "Anya" },'
          ' [3] = { mother = "trader", name = "Sid" }, [4] = { mother = "actor_dolg", name = "Petro" },'
          ' [5] = { mother = "monolith", name = "Yuri", dead = true } })')
    check(w.on() == ["dolg", "freedom"], "the perks on: %s" % w.on())
    check(list(w.env.active()["freedom"].names.values()) == ["Anya", "Vova"], "who brings Freedom's")
    # one of two members dies: still on; both: off
    w.run("fotz_faction.F.members[1].dead = true")
    check(w.on() == ["dolg", "freedom"], "one death ended it")
    w.run("fotz_faction.F.members[2] = nil")
    check(w.on() == ["dolg"], "no Freedom member left, still on: %s" % w.on())
    # at war with Duty: off; a truce isn't a war
    w.run('fotz_politics.S.events["fotz_own/dolg"] = { kind = "war" }')
    check(w.on() == [], "on at war: %s" % w.on())
    w.run('fotz_politics.S.events["fotz_own/dolg"] = { kind = "truce" }')
    check(w.on() == ["dolg"], "off in a truce")
    # a faction with no pair (one that never changes) is never at war
    w.run('fotz_faction.F.members[6] = { mother = "monolith", name = "Lev" }')
    check(w.on() == ["dolg", "monolith"], "a faction that never changes: %s" % w.on())
    # MCM's switch
    w.run('OPTIONS["fotz/perks"] = false')
    check(w.on() == [], "on with the switch off")
    w.run('OPTIONS["fotz/perks"] = true')
    check(w.on() == ["dolg", "monolith"], "off with the switch on")
    # worked out again once the cache's time is past
    w.run("wait(5000); fotz_perks.active(); fotz_faction.F.members[6].dead = true; wait(1500)")
    check("monolith" in w.env.active(), "the cache expired early")
    w.run("wait(1000)")
    check("monolith" not in w.env.active(), "a stale perk after the cache's time")
    # disbanded
    w.run("fotz_faction.F = nil")
    check(w.on() == [], "perks after disbanding")


def curve(src):
    """positive returns: each step adds more than the one before, and a settlement's worth reaches
    the cap; the settlement's worth is Homestead's cap on a player camp's residents (its MCM's), the
    config's without Homestead or with a cap under 1; the config's curve"""
    w = World(src)
    w.run('lead({})')
    sizes = []
    for n in range(1, 18):
        w.run('add("army", 1); wait(5000)')
        sizes.append(w.env.size("army"))
    want = [0.30 * share(n) for n in range(1, 18)]
    check(all(near(a, b) for a, b in zip(sizes, want)), "the airlifts by members: %s" % sizes[:5])
    gains = [sizes[0]] + [sizes[i] - sizes[i - 1] for i in range(1, 15)]
    check(all(gains[i] > gains[i - 1] for i in range(1, 15)) and gains[14] > 5 * gains[0],
          "no positive returns: %s" % gains)
    check(near(sizes[14], 0.30) and near(sizes[16], 0.30), "past a full settlement: %s, %s" % (sizes[14], sizes[16]))
    # Homestead's cap on residents is the full settlement
    w = World(src, "stalker_camp_builder = { cfg = { max_survivors_player_camp = 10 } }")
    w.run('lead({}); add("army", 5); wait(5000)')
    check(near(w.env.size("army"), 0.30 * share(5, full=10)), "Homestead's cap of 10: %s" % w.env.size("army"))
    w = World(src, "stalker_camp_builder = { cfg = { max_survivors_player_camp = 0 } }")
    w.run('lead({}); add("army", 5); wait(5000)')
    check(near(w.env.size("army"), 0.30 * share(5)), "Homestead's cap of 0: %s" % w.env.size("army"))
    # the config's curve and settlement
    w = World(src, 'INI = { perks = { curve = "2", full_steps = "10" } }')
    w.run('lead({}); add("army", 5); wait(5000)')
    check(near(w.env.size("army"), 0.30 * 0.25), "the config's curve: %s" % w.env.size("army"))


def nearness_scenario(src):
    """where you are counts: members on your level in full, others less the farther away, by the
    global map; an online member is on your level; a level the map doesn't place counts half;
    politics' amplifier counts everyone wherever they are. The user's example: a Duty settlement in
    Rostok sways Rostok's Duty traders, and much less Cordon's"""
    w = World(src)
    w.run('lead({}); add("ecolog", 4, 1); wait(5000)')
    check(near(w.env.size("ecolog"), 0.15 * share(4)), "four Ecologists here in Yantar: %s" % w.env.size("ecolog"))
    w.run('add("ecolog", 4, 2); wait(5000)')
    f = nearness("pripyat", "yantar")
    check(near(w.env.near_weight("ecolog"), 4 + 4 * f) and w.env.weight("ecolog") == 8,
          "four more in Pripyat, seen from Yantar: %s of %s" % (w.env.near_weight("ecolog"), w.env.weight("ecolog")))
    check(near(w.env.size("ecolog"), 0.15 * share(4 + 4 * f)), "the size from Yantar: %s" % w.env.size("ecolog"))
    # you go to Pripyat: the other way round
    w.run('HERE = "l11_pripyat"; wait(5000)')
    check(near(w.env.near_weight("ecolog"), 4 * f + 4), "from Pripyat: %s" % w.env.near_weight("ecolog"))
    # a level the global map doesn't place counts half; an online member is here, whatever their server object says
    w.run('add("ecolog", 2, 4); ONLINE[add("ecolog", 1, 3)] = { rank = "professional" }; wait(5000)')
    check(near(w.env.near_weight("ecolog"), 4 * f + 4 + 2 * 0.5 + 1), "unknown and online: %s" % w.env.near_weight("ecolog"))
    # a member whose level can't be read counts as an unplaced one
    w.run('add("ecolog", 1, 666); wait(5000)')
    check(near(w.env.near_weight("ecolog"), 4 * f + 4 + 3 * 0.5 + 1), "an unreadable level: %s" % w.env.near_weight("ecolog"))
    # relations here by the near; politics' by everyone
    check(near(w.env.amp("ecolog"), 1 + share(4 * f + 6.5)) and near(w.env.amp_all("ecolog"), 1 + share(12)),
          "amp here %s, everywhere %s" % (w.env.amp("ecolog"), w.env.amp_all("ecolog")))
    # the user's example: five Duty men in a Rostok settlement, at Rostok's Duty trader and at Cordon's
    w = World(src, 'HERE = "l06_rostok"')
    w.run('lead({}); add("dolg", 5, 5); TALKING = npc("dolg", "bar_dolg_general_petrenko_stalker")')
    w.run('fire("ActorMenu_on_trade_started"); wait(5000)')
    at_rostok = w.eval('price("sewing_kit_a", 2, 1000)')
    w.run('HERE = "l01_escape"; wait(5000)')
    at_cordon = w.eval('price("sewing_kit_a", 2, 1000)')
    r = nearness("rostok", "cordon")
    check(near(at_rostok, 1000 * (1 - 0.15 * share(5))) and near(at_cordon, 1000 * (1 - 0.15 * share(5 * r))),
          "Rostok %s, Cordon %s (a Rostok member counts %.2f in Cordon)" % (at_rostok, at_cordon, r))


def by_rank(src):
    """a member counts by their rank: a novice half a step, a legend two, unknown as a professional"""
    w = World(src)
    w.run('lead({ [1] = { mother = "freedom", name = "Vova" } }); SE[1] = { rank = "novice" }')
    w.run('TALKING = npc("freedom", "mil_freedom_trader") fire("ActorMenu_on_trade_started")')
    w.run("wait(5000)")
    got = w.eval('price("mutant_part_dog_tail", 2, 1000)')
    check(near(got, 1000 * (1 - 0.15 * share(0.5))), "a novice offline: %s" % got)
    # a legend online beside them: 2.5 steps
    w.run('fotz_faction.F.members[2] = { mother = "freedom", name = "Anya" }; ONLINE[2] = { rank = "legend" }; wait(5000)')
    got = w.eval('price("mutant_part_dog_tail", 2, 1000)')
    check(near(got, 1000 * (1 - 0.15 * share(2.5))), "a novice and a legend: %s" % got)
    check(w.env.weight("freedom") == 2.5 and w.env.count("freedom") == 2, "weight %s, count %s" % (w.env.weight("freedom"), w.env.count("freedom")))
    # a rank that can't be read counts as a professional's step
    w.run('ONLINE[2] = { broken = true }; wait(5000)')
    check(w.env.weight("freedom") == 1.5, "an unreadable rank: %s" % w.env.weight("freedom"))
    w.run('for i = 3, 6 do fotz_faction.F.members[i] = { mother = "freedom", name = "L" .. i }; ONLINE[i] = { rank = "legend" } end; wait(5000)')
    got = w.eval('price("mutant_part_dog_tail", 2, 1000)')
    check(near(got, 1000 * (1 - 0.15 * share(9.5))), "four legends more: %s" % got)
    # the config's weights
    w = World(src, 'INI = { perks = { rank_weights = "1, 1, 1, 1, 1, 1, 1, 3" } }')
    w.run('lead({ [1] = { mother = "army", name = "Sgt" } }); ONLINE[1] = { rank = "legend" }; wait(5000)')
    check(near(w.env.size("army"), 0.30 * share(3)), "the config's legend weight: %s" % w.env.size("army"))


def relations(src):
    """members from a faction move your goodwill with it more, for better or worse, at war or not:
    a change is followed by its share more, once (never compounding), a story-sized jump and the
    first look after a load left alone; the cap on the curve, and its slider"""
    w = World(src)
    check(w.env.amp("dolg") == 1, "an amplifier without a faction")
    w.run('lead({}); add("dolg", 5); GW.dolg = 300; GW.freedom = 100')
    w.run('wait(5000)')
    a = 1 + share(5)
    check(near(w.env.amp("dolg"), a) and w.env.amp("freedom") == 1, "amp %s, %s" % (w.env.amp("dolg"), w.env.amp("freedom")))
    # the first look reads; a task's +100 comes with its share more; then nothing until the next change
    w.run('fire("actor_on_update")')
    check(w.eval("GW.dolg") == 300 and w.eval("GW_CHANGES") == 0, "the first look changed goodwill: %s" % w.eval("GW.dolg"))
    up = round(100 * (a - 1))
    w.run('GW.dolg = GW.dolg + 100; GW.freedom = GW.freedom + 100; wait(1000); fire("actor_on_update")')
    check((w.eval("GW.dolg"), w.eval("GW.freedom")) == (400 + up, 200), "after a task: %s, %s (+%s)" % (w.eval("GW.dolg"), w.eval("GW.freedom"), up))
    w.run('wait(1000); fire("actor_on_update"); wait(1000); fire("actor_on_update")')
    check(w.eval("GW.dolg") == 400 + up, "compounded: %s" % w.eval("GW.dolg"))
    # for worse: a kill's -40 comes with its share more
    down = round(40 * (a - 1))
    w.run('GW.dolg = GW.dolg - 40; wait(1000); fire("actor_on_update")')
    check(w.eval("GW.dolg") == 360 + up - down, "after a kill: %s" % w.eval("GW.dolg"))
    # a story setting it far off is left alone
    w.run('GW.dolg = -1500; wait(1000); fire("actor_on_update")')
    check(w.eval("GW.dolg") == -1500, "a jump amplified: %s" % w.eval("GW.dolg"))
    # at war with Duty: still (for better or worse), though Duty's perk is off
    w.run('fotz_politics.S.events["fotz_own/dolg"] = { kind = "war" }; wait(5000); fire("actor_on_update")')
    w.run('GW.dolg = GW.dolg - 100; wait(1000); fire("actor_on_update")')
    check(w.eval("GW.dolg") == -1600 - round(100 * (a - 1)) and not w.env.on("dolg"), "at war: %s" % w.eval("GW.dolg"))
    # a full settlement's worth: twice the change at most, or what the slider says
    w.run('add("dolg", 12); wait(5000)')
    check(w.env.amp("dolg") == 2, "the cap: %s" % w.env.amp("dolg"))
    w.run('OPTIONS["fotz/perks_relations_max"] = 30')
    check(near(w.env.amp("dolg"), 1.3), "the slider at 30: %s" % w.env.amp("dolg"))
    # the perks off: nothing
    w.run('OPTIONS["fotz/perks"] = false; wait(5000); x = GW.dolg; GW.dolg = GW.dolg + 100; wait(1000); fire("actor_on_update")')
    check(w.eval("GW.dolg") == w.eval("x") + 100, "with the perks off: %s" % w.eval("GW.dolg"))
    check(any(("goodwill 100, and %s more" % up) in l for l in w.eval("LOG").values()), "no log line")


def trade(src):
    w = World(src)
    w.run('lead({ [1] = { mother = "freedom", name = "Vova" }, [2] = { mother = "stalker", name = "Tolik" },'
          ' [3] = { mother = "dolg", name = "Petro" } })')
    one = 1 - 0.15 * share(1)
    # no trade window: nothing
    check(w.eval('price("mutant_part_dog_tail", 2, 1000)') is None, "a price outside a trade")
    # a Freedom trader: mutant parts and meat off by its members when you buy, after other mods' change
    w.run('TALKING = npc("freedom", "mil_freedom_trader") fire("ActorMenu_on_trade_started")')
    got = (w.eval('price("mutant_part_dog_tail", 2, 1000)'), w.eval('price("mutant_part_flesh_meat", 2, 1000, 800)'))
    check(near(got[0], 1000 * one) and near(got[1], 800 * one), "Freedom's mutant parts, one member: %s" % (got,))
    w.run('add("freedom", 1); wait(5000)')
    got = w.eval('price("mutant_part_dog_tail", 2, 1000)')
    check(near(got, 1000 * (1 - 0.15 * share(2))), "two members: %s" % got)
    w.run('add("freedom", 18); wait(5000)')
    check(near(w.eval('price("mutant_part_dog_tail", 2, 1000)'), 850), "twenty members: %s" % w.eval('price("mutant_part_dog_tail", 2, 1000)'))
    # MCM's slider sets the cap, in percent
    w.run('OPTIONS["fotz/perks_trade_max"] = 5')
    check(near(w.eval('price("mutant_part_dog_tail", 2, 1000)'), 950), "the slider at 5%%: %s" % w.eval('price("mutant_part_dog_tail", 2, 1000)'))
    w.run('OPTIONS["fotz/perks_trade_max"] = 0')
    check(w.eval('price("mutant_part_dog_tail", 2, 1000)') == 1000, "the slider at 0: %s" % w.eval('price("mutant_part_dog_tail", 2, 1000)'))
    w.run('OPTIONS["fotz/perks_trade_max"] = nil')
    # selling to them, or their food: as it was
    got = (w.eval('price("mutant_part_dog_tail", 1, 1000)'), w.eval('price("bread", 2, 1000, 900)'))
    check(got == (None, 900), "selling or other goods changed: %s" % (got,))
    # trade closed: nothing
    w.run('fire("ActorMenu_on_trade_closed")')
    check(w.eval('price("mutant_part_dog_tail", 2, 1000)') is None, "a price after the window closed")
    # Sidorovich, a "trader" by community: the Loners' by Factions' table
    w.run('TALKING = npc("trader", "esc_2_12_stalker_trader") fire("ActorMenu_on_trade_started")')
    got = (w.eval('price("bread", 2, 100)'), w.eval('price("vodka", 2, 200)'), w.eval('price("medkit", 2, 300)'))
    check(near(got[0], 100 * one) and near(got[1], 200 * one) and got[2] is None, "Sidorovich: %s" % (got,))
    # Duty's goods by kind and by prefix, at a Duty trader by their own faction
    w.run('TALKING = npc("dolg", "bar_some_mechanic") fire("ActorMenu_on_trade_started")')
    got = tuple(w.eval('price("%s", 2, 1000)' % s) for s in ("sewing_kit_a", "gun_oil_ru", "toolkit_2", "prt_w_barrel_1", "wpn_ak74"))
    check(all(near(g, 1000 * one) for g in got[:3]) and got[3:] == (None, None), "Duty's goods: %s" % (got,))
    # a trader of a faction no member came from: nothing
    w.run('TALKING = npc("csky", "mar_trader") fire("ActorMenu_on_trade_started")')
    check(w.eval('price("prt_w_barrel_1", 2, 1000)') is None, "Clear Sky's parts without a member")
    # the config's cap and goods, on a straight line of two members
    w = World(src, 'INI = { perks = { trade_max = "0.08", goods_food = "i_food", curve = "1", full_steps = "2" } }')
    w.run('lead({ [1] = { mother = "stalker", name = "Tolik" } })')
    w.run('TALKING = npc("stalker", "owl") fire("ActorMenu_on_trade_started")')
    got = (w.eval('price("bread", 2, 100)'), w.eval('price("vodka", 2, 100)'))
    check(near(got[0], 96) and got[1] is None, "the config's cap and goods: %s" % (got,))
    w.run('add("stalker", 1); wait(5000)')
    check(near(w.eval('price("bread", 2, 100)'), 92), "the config's cap: %s" % w.eval('price("bread", 2, 100)'))


def airlift(src):
    w = World(src)
    w.run('fire("actor_on_first_update"); fotz_perks.hook()')
    fare = w.eval('function(g) return game_guide_travel.get_guidespot_fare(g, "spot", "x", "y") end')
    check(fare("esc_3_16_military_trader") == 5000, "an airlift off without the perk")
    w.run('lead({ [1] = { mother = "army", name = "Sgt" } })')
    w.run("wait(5000)")
    got = (fare("esc_3_16_military_trader"), fare("mil_freedom_guid"))
    check(got == (int(5000 * (1 - 0.30 * share(1)) + 0.5), 4500), "the airlift and another guide, one member: %s" % (got,))
    w.run('add("army", 2); wait(5000)')
    check(fare("esc_3_16_military_trader") == int(5000 * (1 - 0.30 * share(3)) + 0.5), "three members: %s" % fare("esc_3_16_military_trader"))
    w.run('add("army", 12); wait(5000)')
    check(fare("esc_3_16_military_trader") == 3500, "fifteen members: %s" % fare("esc_3_16_military_trader"))
    w.run('OPTIONS["fotz/perks_airlift_max"] = 10')
    check(fare("esc_3_16_military_trader") == 4500, "the slider at 10%%: %s" % fare("esc_3_16_military_trader"))


def mercs(src):
    w = World(src)
    w.run('fire("actor_on_first_update")')
    ask = w.eval("function(n) return txr_paid_companions.is_squad_competent(db_actor, n) end")
    vet = w.eval('npc("killer", "merc", "killer_sim_squad_veteran", 71)')
    adv = w.eval('npc("killer", "merc", "killer_sim_squad_advanced", 72)')
    nov = w.eval('npc("killer", "merc", "killer_sim_squad_novice", 73)')
    lon = w.eval('npc("stalker", "loner", "stalker_sim_squad_veteran", 74)')
    check(ask(vet) is False, "a merc squad took it without the perk")
    # one member: under 2 in 100; the veteran squad rolls 30, the advanced 1
    w.run('lead({ [1] = { mother = "killer", name = "Merc" } })')
    w.run("wait(5000); NEXT_ROLL = 30")
    first = ask(vet)
    w.run("NEXT_ROLL = 1")
    got = (first, ask(adv))
    check(got == (False, True), "one member, rolls 30 and 1: %s" % (got,))
    # the roll is kept: the dialog's second check, and later, agree
    check(ask(vet) is False, "the veteran squad rolled again")
    # seven members: about 32 in 100, the same roll of 30 now takes it
    w.run('add("killer", 6); wait(5000)')
    check(near(w.env.size("killer"), 100 * share(7)) and ask(vet) is True, "seven members, the roll of 30: %s" % w.env.size("killer"))
    # a full settlement: certain, but never a novice squad or another faction's
    w.run('add("killer", 8); wait(5000); NEXT_ROLL = 100')
    got = (ask(nov), ask(lon), w.env.size("killer"))
    check(got == (False, False, 100), "novice, Loner, the chance: %s" % (got,))
    w.run("ROLLED = true")
    check(ask(lon) is True, "the game's own yes lost")
    # the mercs' cap: MCM's slider, never past 100
    w.run('OPTIONS["fotz/perks_merc_max"] = 30')
    check(w.env.size("killer") == 30, "the slider at 30: %s" % w.env.size("killer"))
    w.run('OPTIONS["fotz/perks_merc_max"] = 150; add("killer", 4); wait(5000)')
    check(w.env.size("killer") == 100, "the slider past 100: %s" % w.env.size("killer"))


def pda_map(src):
    w = World(src)
    w.run('fire("actor_on_first_update")')
    see = w.eval("function(c) return item_milpda.actor_pda_can_see_mapspot(c) end")
    check(see("bandit") is False, "Bandits shown without the perk")
    w.run('lead({ [1] = { mother = "bandit", name = "Fima" } })')
    w.run("wait(5000)")
    check((see("bandit"), see("army")) == (True, False), "Bandits and the Military: %s, %s" % (see("bandit"), see("army")))
    w.run('BLACKLIST.bandit = true')
    check(see("bandit") is False, "a blacklisted faction shown")
    w.run('BLACKLIST.bandit = nil; PDA_ALLIES = false')
    check(see("bandit") is False, "shown on a PDA that shows no allies")


def radio(src):
    w = World(src)
    w.run('lead({ [1] = { mother = "monolith", name = "Yuri" }, [2] = { mother = "greh", name = "Bor" } })')
    w.run('fire("actor_on_first_update")')
    # the radio isn't up for a while after a load: the manager is never asked for early
    w.run('wait(30000); fire("actor_on_update")')
    check(w.eval("MADE") == 0, "the manager was made early")
    w.run('wait(15000); fire("actor_on_update")')
    ch = w.eval("CHANNELS.channel_status")
    check((ch.monolith, ch.greh, ch.isg) == (True, True, False), "channels with the perk: %s" % ((ch.monolith, ch.greh, ch.isg),))
    # the members gone: Monolith's closes, Sin's (the game's own) stays
    w.run('fotz_faction.F.members = {}; wait(15000); fire("actor_on_update")')
    check((ch.monolith, ch.greh, ch.stalker) == (False, True, True), "after: %s" % ((ch.monolith, ch.greh, ch.stalker),))
    check(any("radio chatter on" in l for l in w.eval("LOG").values()), "no log line")


def others(src):
    w = World(src)
    check(w.env.outpost_bonus() == 0, "an outpost bonus without the perk")
    w.run('lead({ [1] = { mother = "renegade", name = "Ren" } })')
    w.run("wait(5000)")
    check(near(w.env.outpost_bonus(), 15 * share(1)), "the Renegades' bonus, one member: %s" % w.env.outpost_bonus())
    w.run('add("renegade", 14); wait(5000)')
    check(w.env.outpost_bonus() == 15, "the Renegades' bonus, fifteen members: %s" % w.env.outpost_bonus())
    w.run('OPTIONS["fotz/perks_outpost_max"] = 4')
    check(w.env.outpost_bonus() == 4, "the slider at 4: %s" % w.env.outpost_bonus())
    w.run('OPTIONS["fotz/perks_outpost_max"] = nil')
    w.run('add("stalker", 8); add("army", 1); add("killer", 2); add("monolith", 1); wait(5000)')
    got = tuple(w.env.pct(f) for f in ("stalker", "csky", "army", "killer", "renegade", "monolith"))
    want = (int(15 * share(8) + 0.5), 0, int(30 * share(1) + 0.5), int(100 * share(2) + 0.5), 15, None)
    check(got == want, "percents: %s, not %s" % (got, want))
    w.run('fire("actor_on_update")')
    check(any("renegade's perk on (outposts, 15): Ren" in l for l in w.eval("LOG").values()), "no log line for a perk")


def shipped(src):
    """the shipped [perks] config and MCM's sliders' defaults are the script's defaults"""
    import re
    ltx = io.open(os.path.join(HERE, "..", "gamedata", "configs", "plugins", "fotz_politics.ltx"), encoding="ascii").read()
    sec = ltx.split("[perks]", 1)[1].split("\n[", 1)[0]
    cfg = {}
    for ln in sec.splitlines():
        m = re.match(r"\s*(\w+)\s*=\s*([^;]*?)\s*(;|$)", ln)
        if m:
            cfg[m.group(1)] = m.group(2)
    w = World(src)
    d = w.env.DEFAULTS
    for k in d.keys():
        v = d[k]
        got = cfg.get(k)
        same = (got is not None) and (float(got) == v if isinstance(v, (int, float)) else got == v)
        check(same, "[perks] %s is %r, the script's %r" % (k, got, v))
    mcm = io.open(os.path.join(HERE, "..", "gamedata", "scripts", "fotz_mcm.script"), encoding="utf-8").read()
    for perk, scale in (("trade", 100), ("airlift", 100), ("merc", 1), ("outpost", 1), ("relations", 100)):
        m = re.search(r'id = "perks_%s_max", type = "track".*?def = ([\d.]+)' % perk, mcm)
        check(m and float(m.group(1)) == d[perk + "_max"] * scale,
              "MCM's %s slider: %s, not %s" % (perk, m and m.group(1), d[perk + "_max"] * scale))


def run(src):
    shipped(src)
    gate(src)
    curve(src)
    nearness_scenario(src)
    by_rank(src)
    relations(src)
    trade(src)
    airlift(src)
    mercs(src)
    pda_map(src)
    radio(src)
    others(src)
    return "12 scenarios: the config, the gate, the curve, nearness, ranks, relations, trade, airlifts, mercs, the map, the radio, the rest"


def main():
    src = io.open(SCRIPT, encoding="utf-8").read().replace("\r\n", "\n")
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
