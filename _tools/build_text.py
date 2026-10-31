"""Write the Russian string tables from lang/ru.po and the English tables.

Each English table in gamedata/configs/text/eng/ gets a Russian twin in text/rus/ with the same ids
in the same order, in windows-1251 as the game reads them. An id with no Russian yet, or whose
English changed since it was translated (the .po's msgid differs), stops the build.

    build_text.py           write text/rus/
    build_text.py --check   only report whether text/rus/ is up to date
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENG = os.path.join(ROOT, "gamedata", "configs", "text", "eng")
RUS = os.path.join(ROOT, "gamedata", "configs", "text", "rus")
PO = os.path.join(HERE, "lang", "ru.po")


def unquote(s):
    return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def read_po(path):
    """{id: (english, russian)} from msgctxt/msgid/msgstr entries (continued lines allowed)."""
    entries, cur, key = {}, {}, None
    for line in open(path, encoding="utf-8").read().splitlines() + [""]:
        line = line.strip()
        m = re.match(r'(msgctxt|msgid|msgstr)\s+"(.*)"$', line)
        if m:
            key = m.group(1)
            cur[key] = unquote(m.group(2))
        elif line.startswith('"') and key:
            cur[key] += unquote(line[1:-1])
        elif not line:
            if "msgctxt" in cur:
                entries[cur["msgctxt"]] = (cur.get("msgid", ""), cur.get("msgstr", ""))
            cur, key = {}, None
    return entries


def read_table(path):
    raw = open(path, "rb").read().decode("cp1251")
    root = ET.fromstring(raw.split("?>", 1)[1] if raw.startswith("<?xml") else raw)
    return [(s.get("id"), s.findtext("text") or "") for s in root.iter("string")]


def render(rows):
    out = ['<?xml version="1.0" encoding="windows-1251"?>', "<string_table>"]
    for sid, text in rows:
        out += ['\t<string id="%s">' % sid, "\t\t<text>%s</text>" % escape(text), "\t</string>"]
    out.append("</string_table>")
    return ("\n".join(out) + "\n").encode("cp1251")


def build():
    po = read_po(PO)
    problems, outputs = [], {}
    for name in sorted(os.listdir(ENG)):
        if not name.endswith(".xml"):
            continue
        rows = []
        for sid, eng in read_table(os.path.join(ENG, name)):
            if sid not in po or not po[sid][1]:
                problems.append("%s: %s has no Russian" % (name, sid))
            elif po[sid][0] != eng:
                problems.append("%s: %s's English changed since it was translated" % (name, sid))
            else:
                rows.append((sid, po[sid][1]))
        outputs[name] = render(rows)
    return problems, outputs


def main():
    problems, outputs = build()
    if problems:
        print("\n".join(problems))
        return 1
    stale = [n for n, data in outputs.items()
             if not os.path.exists(os.path.join(RUS, n)) or open(os.path.join(RUS, n), "rb").read() != data]
    if "--check" in sys.argv:
        print("text/rus: %d tables, %s" % (len(outputs), "stale: " + ", ".join(stale) if stale else "up to date"))
        return 1 if stale else 0
    os.makedirs(RUS, exist_ok=True)
    for n in stale:
        with open(os.path.join(RUS, n), "wb") as f:
            f.write(outputs[n])
    print("text/rus: %d tables, %d written" % (len(outputs), len(stale)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
