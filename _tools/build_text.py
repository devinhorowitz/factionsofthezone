"""Write the translated string tables from lang/*.po and the English tables.

Each English table in gamedata/configs/text/eng/ gets a twin in every language's folder, with the
same ids in the same order, in the code page the game reads that language in:

    lang/ru.po   text/rus/   windows-1251   Russian, kept whole: an id with no Russian yet, or whose
                                            English changed since it was translated (the .po's msgid
                                            differs), stops the build
    lang/pt.po   text/ptb/   windows-1252   Brazilian Portuguese, by cuph0332 (ptb is the language
                                            GAMMA's Portuguese pack sets): such an id is left out of
                                            the table, and the game shows its English

    build_text.py           write the tables
    build_text.py --check   only report whether they are up to date
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEXT = os.path.join(ROOT, "gamedata", "configs", "text")
ENG = os.path.join(TEXT, "eng")

# the .po, the folder it writes, its code page, the language's name, and whether a gap stops the build
LANGS = [
    ("ru.po", "rus", "cp1251", "Russian", True),
    ("pt.po", "ptb", "cp1252", "Portuguese", False),
]


def unquote(s):
    return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), s)


def read_po(path):
    """{id: (english, translation)} from msgctxt/msgid/msgstr entries (continued lines allowed)."""
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


def render(rows, cp):
    out = ['<?xml version="1.0" encoding="windows-%s"?>' % cp[2:], "<string_table>"]
    for sid, text in rows:
        out += ['\t<string id="%s">' % sid, "\t\t<text>%s</text>" % escape(text), "\t</string>"]
    out.append("</string_table>")
    return ("\n".join(out) + "\n").encode(cp)


def build():
    """(problems that stop the build, ids left to English, {"<folder>/<table>": bytes})"""
    tables = [(name, read_table(os.path.join(ENG, name)))
              for name in sorted(os.listdir(ENG)) if name.endswith(".xml")]
    problems, notes, outputs = [], [], {}
    for po_name, folder, cp, lang, whole in LANGS:
        po = read_po(os.path.join(HERE, "lang", po_name))
        for name, table in tables:
            rows, gaps = [], []
            for sid, eng in table:
                if sid not in po or not po[sid][1]:
                    gaps.append("%s/%s: %s has no %s" % (folder, name, sid, lang))
                elif po[sid][0] != eng:
                    gaps.append("%s/%s: %s's English changed since it was translated" % (folder, name, sid))
                else:
                    rows.append((sid, po[sid][1]))
            (problems if whole else notes).extend(gaps)
            outputs[folder + "/" + name] = render(rows, cp)
    return problems, notes, outputs


def main():
    problems, notes, outputs = build()
    if problems:
        print("\n".join(problems))
        return 1
    for n in notes:
        print("left to English: " + n)
    stale = [n for n, data in outputs.items()
             if not os.path.exists(os.path.join(TEXT, n)) or open(os.path.join(TEXT, n), "rb").read() != data]
    if "--check" in sys.argv:
        print("text: %d tables, %s" % (len(outputs), "stale: " + ", ".join(stale) if stale else "up to date"))
        return 1 if stale else 0
    for n in stale:
        os.makedirs(os.path.dirname(os.path.join(TEXT, n)), exist_ok=True)
        with open(os.path.join(TEXT, n), "wb") as f:
            f.write(outputs[n])
    print("text: %d tables, %d written" % (len(outputs), len(stale)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
