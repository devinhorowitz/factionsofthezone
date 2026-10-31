"""Read the census log and print what the factions hold and how it changed.

    census_report.py [fotz_census.jsonl]      the latest census, then each day's changes
    census_report.py --all [file]             every census in full

With no file it reads the game's appdata folder (D:\\ANOMALY\\appdata here). Censuses taken after
a load on the same game date as the one before are folded into it: a reload doesn't move the
world.
"""
import json
import os
import sys

DEFAULT = r"D:\ANOMALY\appdata\fotz_census.jsonl"


def load(path):
    out = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError as e:
                print("line %d unreadable: %s" % (n, e))
    return out


def by_day(censuses):
    """The last census of each game date, in the order the dates were first seen."""
    days = {}
    for c in censuses:
        days[c["date"][:10]] = c
    return list(days.values())


def table(c):
    rows = []
    for f, e in sorted(c["factions"].items(), key=lambda kv: -kv[1]["fighters"]):
        held = sum(1 for h in c["smarts"].values() if h == f)
        tiers = "/".join(str(e["tiers"].get(t, 0)) for t in ("novice", "advanced", "veteran", "other"))
        rows.append("  %-9s %5d squads %6d fighters %4d smarts  tiers n/a/v/o %s  levels %d"
                    % (f, e["squads"], e["fighters"], held, tiers, len(e["levels"])))
    return "\n".join(rows)


def changes(a, b):
    lines = []
    for f in sorted(set(a["factions"]) | set(b["factions"])):
        fa = a["factions"].get(f, {"squads": 0, "fighters": 0})
        fb = b["factions"].get(f, {"squads": 0, "fighters": 0})
        ds, df = fb["squads"] - fa["squads"], fb["fighters"] - fa["fighters"]
        if ds or df:
            lines.append("  %-9s squads %+d, fighters %+d" % (f, ds, df))
    moved = []
    for s in sorted(set(a["smarts"]) | set(b["smarts"])):
        if a["smarts"].get(s) != b["smarts"].get(s):
            moved.append("  %s: %s -> %s" % (s, a["smarts"].get(s, "-"), b["smarts"].get(s, "-")))
    if moved:
        lines.append("  %d smarts changed hands:" % len(moved))
        lines += ["  " + m for m in moved]
    for x in sorted(b["relations"]):
        for y in sorted(b["relations"][x]):
            va, vb = a["relations"].get(x, {}).get(y), b["relations"][x][y]
            if va != vb:
                lines.append("  relation %s -> %s: %s -> %s" % (x, y, va, vb))
    return "\n".join(lines) or "  nothing"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DEFAULT
    if not os.path.exists(path):
        print("no census log at %s" % path)
        return 1
    cs = load(path)
    if not cs:
        print("the census log is empty")
        return 1
    if "--all" in sys.argv:
        for c in cs:
            print("%s (%s), %s ms" % (c["date"], c["cause"], c["ms"]))
            print(table(c))
        return 0
    days = by_day(cs)
    last = days[-1]
    print("%d censuses over %d game days; latest %s (%s), %.1f ms, %d smarts held, %d contested"
          % (len(cs), len(days), last["date"], last["cause"], last["ms"], last["held"], len(last["contested"])))
    print(table(last))
    if last["contested"]:
        print("  contested: " + ", ".join(last["contested"]))
    for a, b in zip(days, days[1:]):
        print("%s -> %s" % (a["date"], b["date"]))
        print(changes(a, b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
