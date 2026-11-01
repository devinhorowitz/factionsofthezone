"""Package Factions of the Zone for a release: build/FactionsOfTheZone-<version>.zip, one folder
"Factions of the Zone" holding gamedata/ (the mod, as build.py would install it), README.md,
CHANGELOG.md and LICENSE, so MO2's quick installer finds gamedata/ and installs it like any mod.

It refuses to package unless build.py --check passes (the Russian tables, every script compiling,
every test), the changelog has a section for this version (not only "Unreleased"), and the zip,
read back, matches its sources byte for byte with gamedata/ holding the mod's files and nothing
else. The README's links to other files of the repo point at GitHub, since the zip carries only
these. It publishes nothing.

    python release.py
"""
import hashlib
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GD = os.path.join(ROOT, "gamedata")
TOP = "Factions of the Zone"
REPO = "https://github.com/devinhorowitz/factionsofthezone/blob/main/"
RAW = "https://raw.githubusercontent.com/devinhorowitz/factionsofthezone/main/"


def version():
    src = open(os.path.join(HERE, "build.py"), encoding="utf-8").read()
    return re.search(r'^VERSION = "([^"]+)"', src, re.M).group(1)


# links to the repo's own files ("](INSTALL-WITH-CLAUDE.md)", "](docs/DESIGN.md)") as GitHub links
def readme_for_zip():
    text = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    # pictures ("![...](media/page.jpg)") as their raw files, so a viewer shows them; then links
    text = re.sub(r"(!\[[^\]]*\])\((?!https?:|#)([^)]+)\)", lambda m: m.group(1) + "(" + RAW + m.group(2) + ")", text)
    return re.sub(r"\]\((?!https?:|#)([^)]+)\)", lambda m: "](" + REPO + m.group(1) + ")", text)


def main():
    r = subprocess.run([sys.executable, os.path.join(HERE, "build.py"), "--check"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.rstrip())
    if r.returncode != 0:
        raise SystemExit("refusing to package: build.py --check failed\n" + r.stderr)

    v = version()
    changelog = open(os.path.join(ROOT, "CHANGELOG.md"), "rb").read()
    if not re.search(rb"(?m)^## " + re.escape(v.encode()) + rb"\b", changelog):
        raise SystemExit('refusing to package: CHANGELOG.md has no "## %s" section' % v)

    entries = []                          # (archive name, bytes)
    for base, _, names in os.walk(GD):
        for n in names:
            p = os.path.join(base, n)
            entries.append((TOP + "/gamedata/" + os.path.relpath(p, GD).replace(os.sep, "/"), open(p, "rb").read()))
    entries.sort()
    mod_files = len(entries)
    readme = readme_for_zip()
    entries.append((TOP + "/README.md", readme.encode("utf-8")))
    entries.append((TOP + "/CHANGELOG.md", changelog))
    entries.append((TOP + "/LICENSE", open(os.path.join(ROOT, "LICENSE"), "rb").read()))

    out = os.path.join(ROOT, "build")
    os.makedirs(out, exist_ok=True)
    zp = os.path.join(out, "FactionsOfTheZone-%s.zip" % v)
    tmp = zp + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in entries:
            z.writestr(name, data)

    with zipfile.ZipFile(tmp) as z:
        names = z.namelist()
        bad = [n for n, data in entries if z.read(n) != data]
    in_gd = [n for n in names if n.startswith(TOP + "/gamedata/")]
    problems = []
    if bad:
        problems.append("differs from its source: %s" % bad)
    if len(in_gd) != mod_files:
        problems.append("gamedata/ holds %d files, the mod has %d" % (len(in_gd), mod_files))
    if {n.split("/", 1)[0] for n in names} != {TOP}:
        problems.append("more than one top folder")
    for need in ("scripts/fotz_territory.script", "scripts/fotz_map.script", "configs/text/rus/st_fotz.xml"):
        if TOP + "/gamedata/" + need not in names:
            problems.append("no gamedata/" + need)
    if re.search(r"\]\((?!https?:|#)", readme):
        problems.append("the README still links a file the zip doesn't carry")
    if problems:
        os.remove(tmp)
        raise SystemExit("refusing to package: " + "; ".join(problems))
    os.replace(tmp, zp)
    digest = hashlib.sha256(open(zp, "rb").read()).hexdigest()
    print("%s\n  %d files (%d in gamedata/), %d bytes, sha256 %s" % (zp, len(names), len(in_gd),
                                                                     os.path.getsize(zp), digest))


if __name__ == "__main__":
    main()
