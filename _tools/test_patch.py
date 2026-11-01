"""Run fotz_patch.script under LuaJIT 2.0 against a stand-in for the actor, the item config and the
game's news, and check your faction's patches as Sidorovich sells them.

Checked: the dialog only while you lead a faction; a count offered only when you can pay for it;
buying takes the money and gives that many patches, with the game's news for both, and nothing
when you can't pay; the price is the item's own cost (650 without one); Sidorovich's offer and
each count's line, "One" for one; the strings exist.

    python test_patch.py            the real script
    python test_patch.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import io
import os
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(HERE, "..", "gamedata", "scripts")
ENG = os.path.join(HERE, "..", "gamedata", "configs", "text", "eng", "st_fotz.xml")
MODULES = ("fotz_patch", "modxml_fotz_patch")

#: name -> (text in the script, its broken replacement); each must make this test fail
MUTANTS = {
    "anyone_buys": ("    return fotz_faction ~= nil and fotz_faction.F ~= nil", "    return true"),
    "unpaid": ("    if not can_buy(n) then\n        return\n    end\n", ""),
    "free": ("    db.actor:give_money(-cost)\n", ""),
    "one_patch": ("    for _ = 1, n do", "    for _ = 1, 1 do"),
    "price_fixed": ('    return math.floor(tonumber(ini_sys:r_float_ex(SECTION, "cost")) or 650)', "    return 650"),
    "no_default": ('    return math.floor(tonumber(ini_sys:r_float_ex(SECTION, "cost")) or 650)',
                   '    return math.floor(tonumber(ini_sys:r_float_ex(SECTION, "cost")))'),
    "one_as_many": ('n == 1 and "st_fotz_patch_buy_one" or "st_fotz_patch_buy"', '"st_fotz_patch_buy"'),
    "five_is_one": ("function buy_5() buy(5) end", "function buy_5() buy(1) end"),
    "ten_unchecked": ("function can_buy_10() return can_buy(10) end", "function can_buy_10() return true end"),
    "no_money_news": ('        news_manager.relocate_money(db.actor, "out", cost)\n', ""),
    "dxml_any_file": ("    if name ~= [[gameplay\\dialogs.xml]] and name ~= [[gameplay/dialogs.xml]] then",
                      "    if false then", "modxml_fotz_patch"),
    "dxml_twice": ('    if #xml:query("dialog[id=" .. DIALOG .. "]") > 0 then', "    if false then", "modxml_fotz_patch"),
    "anyone_talks": ("    if character_id ~= TRADER or list:has(DIALOG) then", "    if list:has(DIALOG) then", "modxml_fotz_patch"),
    "talk_twice": ("    if character_id ~= TRADER or list:has(DIALOG) then", "    if character_id ~= TRADER then", "modxml_fotz_patch"),
    "no_more": ("            <text>st_fotz_patch_done</text>]] .. CHOICES .. [[", "            <text>st_fotz_patch_done</text>]] .. [[",
                "modxml_fotz_patch"),
    "count_unpriced": ("            <precondition>fotz_patch.can_buy_]] .. n .. [[</precondition>\n", "", "modxml_fotz_patch"),
    "release_anything": ("        if se and se:section_name() == SECTION then", "        if se then"),
    "release_short": ("    for id = 1, 65534 do", "    for id = 1, 65533 do"),
    "switch_stays": ('    ui_mcm.set("fotz/remove_patches", false)\n', ""),
    "no_game_ignored": ('ui_mcm.get("fotz/remove_patches") == true and alife()) then', 'ui_mcm.get("fotz/remove_patches") == true) then'),
    "menu_switch_lost": ('    RegisterScriptCallback("actor_on_first_update", removal)\n', ""),
    "item_news_count": ('        news_manager.relocate_item(db.actor, "in", SECTION, n)', '        news_manager.relocate_item(db.actor, "in", SECTION, 1)'),
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
COST = 650
ini_sys = { r_float_ex = function(self, section, key)
    if section == "fotz_own_patch" and key == "cost" then return COST end
end }
MONEY = 3000
db = { actor = { money = function(self) return MONEY end, give_money = function(self, n) MONEY = MONEY + n end } }
ITEMS, NEWS = {}, {}
function alife_create_item(section, obj) ITEMS[#ITEMS + 1] = section end
news_manager = {
    relocate_money = function(actor, dir, n) NEWS[#NEWS + 1] = "money " .. dir .. " " .. n end,
    relocate_item = function(actor, dir, section, n) NEWS[#NEWS + 1] = "item " .. dir .. " " .. section .. " " .. n end,
}
fotz_faction = { F = nil }
-- the alife, with patches and other things, and MCM's switch
OBJECTS, RELEASED, TIPS, MCM, CALLBACKS = {}, {}, {}, {}, {}
function thing(id, section) OBJECTS[id] = { id = id, section_name = function() return section end } end
SIM = { object = function(self, id) return OBJECTS[id] end }
function alife() return SIM end
function alife_release(se) RELEASED[#RELEASED + 1] = se.id; OBJECTS[se.id] = nil end
ui_mcm = { get = function(id) return MCM[id] end, set = function(id, v) MCM[id] = v end }
function RegisterScriptCallback(name, fn) CALLBACKS[name] = fn end
news_manager.send_tip = function(actor, text) TIPS[#TIPS + 1] = text end
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
            self.g.STR[s.get("id")] = s.findtext("text")
        load = self.lua.eval("function(src, name) local env = setmetatable({}, { __index = _G }) "
                             "local f = assert(loadstring(src, name)) setfenv(f, env) f() return env end")
        self.env = load(srcs["fotz_patch"], "fotz_patch")
        self.dxml = load(srcs["modxml_fotz_patch"], "modxml_fotz_patch")

    def run(self, code):
        return self.lua.execute(code)

    def items(self):
        return list(self.g.ITEMS.values())

    def news(self):
        return list(self.g.NEWS.values())


def not_leading(srcs):
    w = World(srcs)
    e = w.env
    check(not e.leading() and not e.can_buy_1(), "the dialog without a faction")
    e.buy_1()
    check(w.items() == [] and w.g.MONEY == 3000, "bought without a faction: %s" % w.items())


def buying(srcs):
    w = World(srcs)
    w.run("fotz_faction.F = { name = 'Wolves' }")
    e = w.env
    check(e.leading() and e.can_buy_1() and not e.can_buy_5() and not e.can_buy_10() and not e.can_buy_20(),
          "3000 RU at 650: one yes, five, ten and twenty no")
    e.buy_1()
    check(w.g.MONEY == 2350 and w.items() == ["fotz_own_patch"], "one: %s RU, %s" % (w.g.MONEY, w.items()))
    check(w.news() == ["money out 650", "item in fotz_own_patch 1"], "news %s" % w.news())
    e.buy_5()
    check(w.g.MONEY == 2350 and len(w.items()) == 1, "five unpaid: %s RU, %d" % (w.g.MONEY, len(w.items())))
    w.run("MONEY = 20000; ITEMS = {}; NEWS = {}")
    check(e.can_buy_10() and e.can_buy_20(), "20000 RU: ten and twenty")
    e.buy_10()
    check(w.g.MONEY == 13500 and len(w.items()) == 10, "ten: %s RU, %d" % (w.g.MONEY, len(w.items())))
    check(w.news() == ["money out 6500", "item in fotz_own_patch 10"], "news %s" % w.news())
    e.buy_5()
    check(w.g.MONEY == 10250 and len(w.items()) == 15, "five: %s RU, %d" % (w.g.MONEY, len(w.items())))
    check(not e.can_buy_20(), "twenty for 13000 with 10250")


def words(srcs):
    w = World(srcs)
    w.run("fotz_faction.F = { name = 'Wolves' }")
    e = w.env
    got = [e.text_1(), e.text_5(), e.text_10(), e.text_20()]
    check(got == ["One, for 650 RU.", "5, for 3250 RU.", "10, for 6500 RU.", "20, for 13000 RU."], "counts %s" % got)
    check("650 RU apiece" in e.offer_text(), "offer %s" % e.offer_text())
    # the price is the item's cost, and 650 without one
    w.run("COST = 700")
    check(e.text_10() == "10, for 7000 RU." and e.price() == 700, "cost 700: %s" % e.text_10())
    w.run("COST = nil")
    check(e.price() == 650, "no cost: %s" % e.price())


def removal(srcs):
    w = World(srcs)
    w.env.on_game_start()
    w.run('thing(10, "fotz_own_patch"); thing(15, "stalker_patch"); thing(20, "fotz_own_patch"); thing(65534, "fotz_own_patch")')
    # the switch off: nothing goes
    w.g.CALLBACKS["on_option_change"]()
    check(len(w.g.RELEASED) == 0, "released with the switch off")
    # set from the main menu, with no game: it waits, still on
    w.run('MCM["fotz/remove_patches"] = true; SIM_SAVED = SIM; alife = function() return nil end')
    w.g.CALLBACKS["on_option_change"]()
    check(len(w.g.RELEASED) == 0 and w.g.MCM["fotz/remove_patches"] is True, "released with no game")
    # in game: every patch of yours goes, nothing else, the switch goes off, and it says how many
    w.run("alife = function() return SIM_SAVED end")
    w.g.CALLBACKS["actor_on_first_update"]()
    released = sorted(w.g.RELEASED.values())
    check(released == [10, 20, 65534] and w.g.MCM["fotz/remove_patches"] is False,
          "released %s, switch %s" % (released, w.g.MCM["fotz/remove_patches"]))
    check(list(w.g.TIPS.values()) == ["Your faction's patches taken out of the game: 3."], "tips %s" % list(w.g.TIPS.values()))


#: a DXML document and a dialog list, as far as the edit and the talk read them
FAKES = """
function fake_xml(has)
    local x = { inserted = {} }
    function x:query(q) return has and { q } or {} end
    function x:insertFromXMLString(s) self.inserted[#self.inserted + 1] = s end
    return x
end
function fake_list(ids)
    local l = { ids = ids or {} }
    function l:has(id) for _, v in ipairs(self.ids) do if v == id then return true end end return false end
    function l:add(id) self.ids[#self.ids + 1] = id end
    return l
end
"""


def dialog(srcs):
    w = World(srcs)
    w.run(FAKES)
    d = w.dxml
    root = ET.fromstring(d.XML)
    phrases = {p.get("id"): p for p in root.iter("phrase")}

    def nexts(pid):
        return [n.text for n in phrases[pid].findall("next")]
    check(root.get("id") == "fotz_patch_order" and root.findtext("precondition") == "fotz_patch.leading", "the dialog")
    choices = ["11", "12", "13", "14", "19"]
    check(nexts("0") == ["1"] and nexts("1") == choices and nexts("2") == choices and nexts("19") == [],
          "the loop: %s %s %s" % (nexts("1"), nexts("2"), nexts("19")))
    for pid, n in (("11", 1), ("12", 5), ("13", 10), ("14", 20)):
        p = phrases[pid]
        check(p.findtext("precondition") == "fotz_patch.can_buy_%d" % n and p.findtext("action") == "fotz_patch.buy_%d" % n
              and p.findtext("script_text") == "fotz_patch.text_%d" % n and nexts(pid) == ["2"], "count %d" % n)
    # every function it names is fotz_patch's, every text is in the table
    import re
    for name in re.findall(r"fotz_patch\.(\w+)", d.XML):
        check(w.lua.eval("type")(w.env[name]) == "function", "fotz_patch.%s isn't a function" % name)
    root_t = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root_t.iter("string")}
    texts = [p.findtext("text") for p in phrases.values() if p.findtext("text")]
    check(texts and set(texts) <= have, "texts %s" % texts)
    # into the game's dialogs once, nowhere else
    x = w.lua.eval("fake_xml(false)")
    check(d.edit("gameplay\\dialogs.xml", x) is True and len(x.inserted) == 1, "the dialogs: %d" % len(x.inserted))
    y = w.lua.eval("fake_xml(true)")
    check(d.edit("gameplay\\dialogs.xml", y) is False and len(y.inserted) == 0, "inserted twice")
    z = w.lua.eval("fake_xml(false)")
    check(d.edit("gameplay\\dialogs_escape.xml", z) is False and len(z.inserted) == 0, "inserted in dialogs_escape.xml")
    # Sidorovich's talk only, once
    sid = w.lua.eval('fake_list({ "dm_init_trader" })')
    check(d.add_talk("esc_2_12_stalker_trader", sid) is True and d.add_talk("esc_2_12_stalker_trader", sid) is False
          and list(sid.ids.values()) == ["dm_init_trader", "fotz_patch_order"], "Sidorovich: %s" % list(sid.ids.values()))
    other = w.lua.eval('fake_list({ "dm_init_trader" })')
    check(d.add_talk("bar_visitors_barman_stalker_trader", other) is False and len(other.ids) == 1, "Barkeep got it")


def item():
    """The item names its own art, and the files are there: the icon, and Wearable Devices' bracer
    patch (inherited, it would be Clear Sky's)."""
    import re
    import struct
    gd = os.path.join(HERE, "..", "gamedata")
    ltx = open(os.path.join(gd, "configs", "mod_system_fotz_patch.ltx"), encoding="cp1251").read()
    body = ltx.split("[fotz_own_patch]:csky_patch", 1)[1]
    keys = dict(re.findall(r"(?m)^(\w+)\s*=\s*(\S+)", body))
    for key, size, mips in (("icons_texture", 100, False), ("wd_bracer_patch", 512, True)):
        check(key in keys, "no %s: the patch would show Clear Sky's" % key)
        path = os.path.join(gd, "textures", keys[key].replace("\\", os.sep) + ".dds")
        check(os.path.isfile(path), "%s names %s, which isn't there" % (key, keys[key]))
        head = open(path, "rb").read(128)
        h, w, levels = struct.unpack("<I", head[12:16])[0], struct.unpack("<I", head[16:20])[0], struct.unpack("<I", head[28:32])[0]
        check((w, h) == (size, size) and (levels > 1) == mips, "%s: %dx%d, %d levels" % (keys[key], w, h, levels))


def strings(srcs):
    import re
    root = ET.fromstring(open(ENG, "rb").read().decode("cp1251").split("?>", 1)[1])
    have = {s.get("id") for s in root.iter("string")}
    want = set(re.findall(r'"(st_fotz_\w+)"', srcs["fotz_patch"])) | {"st_fotz_patch", "st_fotz_patch_descr",
                                                                      "st_fotz_patch_ask", "st_fotz_patch_done",
                                                                      "st_fotz_patch_not_now"}
    check(want <= have, "missing: %s" % sorted(want - have))


def run(srcs):
    strings(srcs)
    item()
    not_leading(srcs)
    buying(srcs)
    words(srcs)
    removal(srcs)
    dialog(srcs)
    return "5 scenarios"


def main():
    srcs = {m: io.open(os.path.join(SCRIPTS_DIR, m + ".script"), encoding="utf-8").read() for m in MODULES}
    if len(sys.argv) > 1:
        name = sys.argv[1]
        m = MUTANTS[name]
        old, new, module = m[0], m[1], (m[2] if len(m) > 2 else "fotz_patch")
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
