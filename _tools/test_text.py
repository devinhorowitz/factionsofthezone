"""Check build_text.py: it refuses an id with no Russian or whose English changed, and writes the
Russian table in windows-1251 with the ids in the English order, escaped.

    python test_text.py            the real build_text.py
    python test_text.py MUTANT     a broken copy (see MUTANTS); the run must fail
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "build_text.py")

MUTANTS = {
    "no_missing": ('if sid not in po or not po[sid][1]:', 'if sid not in po:'),
    "no_stale": ("elif po[sid][0] != eng:", "elif False:"),
    "no_escape": ('escape(text)', 'text'),
    "utf8": ('.encode("cp1251")', '.encode("utf-8")'),
}

ENG = """<?xml version="1.0" encoding="windows-1251"?>
<string_table>
\t<string id="b_two"><text>Two &amp; more</text></string>
\t<string id="a_one"><text>One</text></string>
\t<string id="c_new"><text>New</text></string>
\t<string id="d_changed"><text>Changed now</text></string>
\t<string id="e_empty"><text>Not yet</text></string>
</string_table>
"""
PO = '''msgctxt "a_one"
msgid "One"
msgstr "Один"

msgctxt "b_two"
msgid "Two & more"
msgstr "Два & больше"

msgctxt "d_changed"
msgid "Changed before"
msgstr "Изменено"

msgctxt "e_empty"
msgid "Not yet"
msgstr ""
'''


class Fail(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Fail(what)


def run(src):
    root = tempfile.mkdtemp(prefix="fotz_text_")
    try:
        tools = os.path.join(root, "_tools")
        os.makedirs(os.path.join(tools, "lang"))
        eng = os.path.join(root, "gamedata", "configs", "text", "eng")
        os.makedirs(eng)
        open(os.path.join(tools, "build_text.py"), "w", encoding="utf-8").write(src)
        open(os.path.join(eng, "st_test.xml"), "wb").write(ENG.encode("cp1251"))
        open(os.path.join(tools, "lang", "ru.po"), "w", encoding="utf-8").write(PO)
        spec = importlib.util.spec_from_file_location("bt", os.path.join(tools, "build_text.py"))
        bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bt)
        problems, outputs = bt.build()
        check(any("c_new has no Russian" in p for p in problems), "a missing Russian passed: %s" % problems)
        check(any("d_changed's English changed" in p for p in problems), "a changed English passed: %s" % problems)
        check(any("e_empty has no Russian" in p for p in problems), "an empty Russian passed: %s" % problems)
        check(len(problems) == 3, "problems %s" % problems)
        data = outputs["st_test.xml"]
        try:
            text = data.decode("cp1251")
        except UnicodeDecodeError:
            raise Fail("the table isn't windows-1251")
        check("Один" in text, "the Russian isn't readable as windows-1251")
        check(text.index('"b_two"') < text.index('"a_one"'), "ids out of the English order")
        check("Два &amp; больше" in text, "the & wasn't escaped")
        return "compared 5 ids, 3 refused"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    src = io.open(SOURCE, encoding="utf-8").read()
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
        print("FAIL (error): %s: %s" % (type(e).__name__, e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
