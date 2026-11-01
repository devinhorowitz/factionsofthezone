"""Check Factions of the Zone and install it as an MO2 mod.

Writes the Russian string tables (build_text.py), then checks: every XML parses (string tables as
windows-1251), every script compiles under LuaJIT 2.0, the scripts' VERSION matches this build's,
and the tests pass. Only then mirrors gamedata/ into <mods>\\Factions of the Zone\\gamedata (files
no longer in the source are removed there) and writes its meta.ini.

    build.py                      check and install into D:\\GAMMA\\mods
    build.py --check              check only
    build.py --mods <folder>      install into another MO2 mods folder
"""
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from lua_jit import L

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GD = os.path.join(ROOT, "gamedata")
NAME = "Factions of the Zone"
VERSION = "0.4.1"
TESTS = ["test_census.py", "test_text.py", "test_politics.py", "test_faction.py", "test_tab.py", "test_territory.py", "test_map.py", "test_patch.py"]

META = """[General]
modid=0
version={version}
newestVersion=
category=
installationFile=
repository=
gameName=stalkeranomaly
comments=Factions of the Zone {version}: the factions as living powers.
notes="Built from the factionsofthezone repo by _tools/build.py. Do not edit here: rebuild."
url=https://github.com/devinhorowitz/factionsofthezone
hasCustomURL=true
"""


def check():
    bad = []
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_text.py")], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0:
        bad.append("build_text.py: " + r.stdout.strip())
    lua = L.LuaRuntime()
    compiles = lua.eval("function(s, n) local f, e = loadstring(s, n) return e end")
    n_xml = n_lua = 0
    for root, _, files in os.walk(GD):
        for f in files:
            p = os.path.join(root, f)
            if f.endswith(".xml"):
                text = open(p, "rb").read().decode("cp1251")
                # the engine's UI parser gives up on a file with anything before its root element,
                # and every widget it hands back is then nil: a fatal at the first use
                if os.path.basename(root) == "ui" and not text.lstrip().startswith("<w>"):
                    bad.append("%s: something before the root element <w>" % p)
                try:
                    ET.fromstring(text.split("?>", 1)[1] if text.startswith("<?xml") else text)
                    n_xml += 1
                except ET.ParseError as e:
                    bad.append("%s: %s" % (p, e))
            elif f.endswith(".script"):
                err = compiles(open(p, encoding="latin-1").read(), f)
                n_lua += 1
                if err:
                    bad.append("%s: %s" % (p, err))
                m = re.search(r'(?m)^VERSION = "([^"]+)"', open(p, encoding="latin-1").read())
                if m and m.group(1) != VERSION:
                    bad.append("%s's VERSION is %s, this build's is %s" % (f, m.group(1), VERSION))
    print("xml parse: %d, scripts compile: %d, version %s" % (n_xml, n_lua, VERSION))
    for t in TESTS:
        r = subprocess.run([sys.executable, os.path.join(HERE, t)], capture_output=True, text=True)
        last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]
        print("%-18s %s" % (t, last))
        if r.returncode != 0:
            bad.append(t + ": " + last)
    return bad


def install(mods):
    mod = os.path.join(mods, NAME)
    dst = os.path.join(mod, "gamedata")
    os.makedirs(dst, exist_ok=True)
    want = set()
    for root, _, files in os.walk(GD):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), GD)
            want.add(rel)
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copyfile(os.path.join(root, f), out)
    removed = 0
    for root, _, files in os.walk(dst):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), dst)
            if rel not in want:
                os.remove(os.path.join(root, f))
                removed += 1
    with open(os.path.join(mod, "meta.ini"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(META.format(version=VERSION))
    print("installed %d files to %s (%d stale removed)" % (len(want), mod, removed))


def main():
    # an install counts as a launch (the game lock), so a flag this doesn't know installs nothing
    args = sys.argv[1:]
    known = args in ([], ["--check"]) or (len(args) == 2 and args[0] == "--mods")
    if not known:
        print(__doc__)
        return 2
    bad = check()
    if bad:
        print("NOT installed:")
        print("\n".join(bad))
        return 1
    if "--check" not in sys.argv:
        mods = sys.argv[sys.argv.index("--mods") + 1] if "--mods" in sys.argv else r"D:\GAMMA\mods"
        install(mods)
    return 0


if __name__ == "__main__":
    sys.exit(main())
