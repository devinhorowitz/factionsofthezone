"""Run fotz_bridges.script under LuaJIT 2.0 against stand-ins for the game's string table, G.A.M.M.A.'s
NPC Loot Claim, Homestead and the game's callbacks and timed events, and check the bridges.

Checked: while you lead a faction its name stands in for fotz_own and actor_fotz_own, and only
for them, never a blank name, with every other string as the game gives it, through one wrapper
however often it's hooked; a member's kill is freed for you to loot once their claim is made,
from the claim table as it is then, and no one else's kill or claim is; Homestead gets the
provider (your faction while you lead one, a member's old faction to save), a member is kept from
moving on and no one else, the callback is registered once and only with a Homestead that sends
it, and a game without Homestead or the loot claim is left alone.

    python test_bridges.py            the real script
    python test_bridges.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import sys

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "gamedata", "scripts", "fotz_bridges.script")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "names_any_id": ("    if f and OWN_IDS[id] and type(f.name)", "    if f and type(f.name)"),
    "names_blank": ('type(f.name) == "string" and f.name ~= "" then', 'type(f.name) == "string" then'),
    "names_not_leading": ("    local f = F()\n    if f and OWN_IDS", "    local f = F() or { name = \"Wolves\" }\n    if f and OWN_IDS"),
    "double_wrap": ("    if original_translate or not (game and game.translate_string) then",
                    "    if not (game and game.translate_string) then"),
    "args_dropped": ("    return original_translate(id, ...)", "    return original_translate(id)"),
    "loot_now": ('    CreateTimeEvent("fotz_bridges", "loot_" .. vid, 0, function()\n        if free_kill(vid, kid) then',
                 '    free_kill(vid, kid)\n    CreateTimeEvent("fotz_bridges", "loot_" .. vid, 0, function()\n        if false then'),
    "loot_any_killer": ("    if not (kid and f.members[kid]) then", "    if not kid then"),
    "loot_others_claim": ("claimed[victim_id] == killer_id then", "claimed[victim_id] ~= nil then"),
    "loot_cached_table": ('    CreateTimeEvent("fotz_bridges", "loot_" .. vid, 0, function()\n        if free_kill(vid, kid) then',
                          '    local held = grok_loot_claim and grok_loot_claim.claimed\n'
                          '    CreateTimeEvent("fotz_bridges", "loot_" .. vid, 0, function()\n'
                          '        if held and held[vid] == kid then held[vid] = nil end\n        if false then'),
    "provider_always": ("        return F() and fotz_faction.OWN or nil", "        return fotz_faction.OWN"),
    "provider_unsafe": ("        return fotz_faction.saved_faction(comm, npc_id)", "        return comm"),
    "keep_anyone": ("    if f and id and f.members[id] and type(flags)", "    if f and id and type(flags)"),
    "keep_id_string": ("    local f, id = F(), tonumber(npc_id)", "    local f, id = F(), npc_id"),
    "old_homestead_registers": ('    if not registered and type(hs.send_settler_callback) == "function" then',
                                "    if not registered then"),
    "registers_twice": ("        registered = true\n", ""),
    "no_provider": ("    hs.faction_provider = provider\n", ""),
}

WORLD = r"""
LOG = {}
function printf(fmt, ...)
    local p, i = { ... }, 0
    fmt = string.gsub(tostring(fmt), "%%s", function() i = i + 1 return tostring(p[i]) end)
    LOG[#LOG + 1] = fmt
end

CALLBACKS, REGISTERED = {}, {}
function RegisterScriptCallback(name, fn)
    CALLBACKS[name] = fn
    REGISTERED[name] = (REGISTERED[name] or 0) + 1
end

EVENTS = {}
function CreateTimeEvent(ev, act, delay, fn, ...)
    local args = { ... }
    EVENTS[ev .. "/" .. act] = function() return fn(unpack(args)) end
end
function run_events()
    for k, fn in pairs(EVENTS) do
        if fn() then
            EVENTS[k] = nil
        end
    end
end

-- the game's string table: "<id>|<extra args>"
game = { translate_string = function(id, ...)
    local extra = select("#", ...) > 0 and ("|" .. table.concat({ ... }, ",")) or ""
    return "T:" .. tostring(id) .. extra
end }

function obj(id) return { id = function() return id end } end

fotz_faction = { OWN = "fotz_own", F = nil,
    saved_faction = function(comm, id) return "saved:" .. tostring(comm) .. ":" .. tostring(id) end }
function lead(name)
    fotz_faction.F = { name = name, members = { [501] = { mother = "stalker" } } }
end

-- G.A.M.M.A.'s NPC Loot Claim: claims a body an NPC killed, after Factions' own callback
grok_loot_claim = { claimed = {} }
function npc_dies(victim, killer)
    CALLBACKS.npc_on_death_callback(obj(victim), killer and obj(killer))
    grok_loot_claim.claimed[victim] = killer
end
function mutant_dies(victim, killer)
    CALLBACKS.monster_on_death_callback(obj(victim), killer and obj(killer))
    grok_loot_claim.claimed[victim] = killer
end
"""

HOMESTEAD_NEW = "stalker_camp_builder = { active_camps = {}, send_settler_callback = function() end }"
HOMESTEAD_OLD = "stalker_camp_builder = { active_camps = {} }"


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


class World:
    def __init__(self, src, setup=""):
        self.lua = L.LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute(WORLD)
        self.lua.execute(setup)
        self.env = self.lua.eval("function(src) local env = setmetatable({}, { __index = _G }) "
                                 "local f = assert(loadstring(src, 'fotz_bridges')) setfenv(f, env) f() return env end")(src)
        self.env.on_game_start()

    def run(self, code):
        self.lua.execute(code)

    def eval(self, code):
        return self.lua.eval(code)

    def tr(self, *args):
        # a wrapper that calls itself loops forever (a tail call): a runaway call is an error
        return self.lua.eval("""function(...)
            jit.off()
            debug.sethook(function() debug.sethook() error("translate_string never returns") end, "", 1000000)
            local r = game.translate_string(...)
            debug.sethook()
            return r
        end""")(*args)


def names(src):
    w = World(src)
    # not leading: the game's strings
    check(w.tr("fotz_own") == "T:fotz_own" and w.tr("actor_fotz_own") == "T:actor_fotz_own",
          "renamed while not leading: %s" % w.tr("fotz_own"))
    w.run('lead("Wolves")')
    got = (w.tr("fotz_own"), w.tr("actor_fotz_own"), w.tr("stalker"), w.tr("st_fotz_default_name"), w.tr(None))
    check(got == ("Wolves", "Wolves", "T:stalker", "T:st_fotz_default_name", "T:nil"), "names while leading: %s" % (got,))
    check(w.tr("st_x", "a", "b") == "T:st_x|a,b", "extra arguments lost: %s" % w.tr("st_x", "a", "b"))
    # a blank name, the box's default, leaves the string
    w.run('fotz_faction.F.name = ""')
    check(w.tr("fotz_own") == "T:fotz_own", "a blank name: %r" % w.tr("fotz_own"))
    # hooked again (another game start in the same state): still one wrapper over the game's own
    w.run('fotz_faction.F.name = "Wolves"')
    w.env.hook_names()
    check(w.tr("fotz_own") == "Wolves" and w.tr("dolg") == "T:dolg", "after a second hook: %s, %s" % (w.tr("fotz_own"), w.tr("dolg")))
    # disbanded: the strings again
    w.run("fotz_faction.F = nil")
    check(w.tr("actor_fotz_own") == "T:actor_fotz_own", "after disbanding: %s" % w.tr("actor_fotz_own"))


def loot(src):
    w = World(src)
    # not leading: nothing touched
    w.run("npc_dies(700, 501); run_events()")
    check(w.eval("grok_loot_claim.claimed[700]") == 501, "a claim dropped while not leading")
    w.run('lead("Wolves")')
    # a member's kill, a stalker and a mutant: claimed first, then freed on the next update
    w.run("npc_dies(701, 501); mutant_dies(702, 501)")
    check(w.eval("grok_loot_claim.claimed[701]") == 501, "the claim was never made, or dropped before it was")
    w.run("run_events()")
    check(w.eval("grok_loot_claim.claimed[701]") is None and w.eval("grok_loot_claim.claimed[702]") is None,
          "a member's kills still claimed: %s, %s" % (w.eval("grok_loot_claim.claimed[701]"), w.eval("grok_loot_claim.claimed[702]")))
    # someone else's kill stays theirs, and so does a claim someone else made on a member's kill
    w.run("npc_dies(703, 800); npc_dies(704, 501); grok_loot_claim.claimed[704] = 801; run_events()")
    check(w.eval("grok_loot_claim.claimed[703]") == 800 and w.eval("grok_loot_claim.claimed[704]") == 801,
          "others' claims: %s, %s" % (w.eval("grok_loot_claim.claimed[703]"), w.eval("grok_loot_claim.claimed[704]")))
    # a load replaces the claim table between the kill and the update
    w.run("npc_dies(705, 501); grok_loot_claim.claimed = { [705] = 501, [706] = 800 }; run_events()")
    check(w.eval("grok_loot_claim.claimed[705]") is None and w.eval("grok_loot_claim.claimed[706]") == 800,
          "after the table was replaced: %s" % w.eval("grok_loot_claim.claimed[705]"))
    check(any("yours to loot" in l for l in w.eval("LOG").values()), "no log line")
    # a kill by no one, and a game without the loot claim: no error
    w.run("CALLBACKS.npc_on_death_callback(obj(707), nil); grok_loot_claim = nil")
    w.run("CALLBACKS.npc_on_death_callback(obj(708), obj(501)); run_events()")


def homestead(src):
    # no Homestead: nothing, and no error
    w = World(src)
    w.run("CALLBACKS.actor_on_first_update()")
    check(w.eval("REGISTERED.homestead_on_before_settler_leave") is None, "registered without Homestead")
    # an older Homestead: the provider is set (it never reads it), the callback isn't asked for
    w = World(src, HOMESTEAD_OLD)
    w.run("CALLBACKS.actor_on_first_update()")
    check(w.eval("stalker_camp_builder.faction_provider") is not None, "no provider")
    check(w.eval("REGISTERED.homestead_on_before_settler_leave") is None, "registered with an older Homestead")
    # 1.3.4 and later
    w = World(src, HOMESTEAD_NEW)
    w.run("CALLBACKS.actor_on_first_update(); CALLBACKS.actor_on_first_update()")
    check(w.eval("REGISTERED.homestead_on_before_settler_leave") == 1,
          "registered %s times" % w.eval("REGISTERED.homestead_on_before_settler_leave"))
    p = w.eval("stalker_camp_builder.faction_provider")
    check(p.get_player_faction() is None, "the player's faction while not leading: %s" % p.get_player_faction())
    w.run('lead("Wolves")')
    check(p.get_player_faction() == "fotz_own", "the player's faction while leading: %s" % p.get_player_faction())
    check(p.save_safe_faction("fotz_own", 501) == "saved:fotz_own:501", "save_safe_faction: %s" % p.save_safe_faction("fotz_own", 501))
    # moving on: a member stays (an id as Homestead may give it, a string), anyone else goes
    keep = w.eval("function(id) local flags = {} CALLBACKS.homestead_on_before_settler_leave(id, {}, flags) return flags.keep end")
    check(keep(501) is True and keep("501") is True, "a member moved on: %s, %s" % (keep(501), keep("501")))
    check(keep(502) is None, "a non-member was kept")
    w.run("fotz_faction.F = nil")
    check(keep(501) is None, "kept while not leading")


def run(src):
    names(src)
    loot(src)
    homestead(src)
    return "3 scenarios: names, loot, Homestead"


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
