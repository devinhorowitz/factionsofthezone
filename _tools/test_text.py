"""Check build_text.py: Russian is kept whole (an id with no Russian, or whose English changed, stops
the build), Portuguese leaves such an id out for the game's English and reports it, and every table
is written in its language's code page, under its folder, with the ids in the English order, escaped.

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
    "utf8": ('.encode(cp)', '.encode("utf-8")'),
    "ru_lenient": ('"Russian", True', '"Russian", False'),
    "pt_whole": ('"Portuguese", False', '"Portuguese", True'),
    "pt_cp1251": ('"ptb", "cp1252"', '"ptb", "cp1251"'),
    "pt_folder": ('("pt.po", "ptb"', '("pt.po", "rus"'),
    "header_fixed": ('"windows-%s"?>\' % cp[2:]', '"windows-1251"?>\''),
    "notes_dropped": ("(problems if whole else notes)", "(problems if whole else [])"),
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
PT = '''msgctxt "a_one"
msgid "One"
msgstr "Uma facção"

msgctxt "b_two"
msgid "Two & more"
msgstr "Dois & mais"

msgctxt "d_changed"
msgid "Changed before"
msgstr "Mudou antes"

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
        open(os.path.join(tools, "lang", "pt.po"), "w", encoding="utf-8").write(PT)
        spec = importlib.util.spec_from_file_location("bt", os.path.join(tools, "build_text.py"))
        bt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bt)
        problems, notes, outputs = bt.build()

        # Russian: every gap stops the build
        check(any("c_new has no Russian" in p for p in problems), "a missing Russian passed: %s" % problems)
        check(any("rus/st_test.xml: d_changed's English changed" in p for p in problems),
              "a changed English passed: %s" % problems)
        check(any("e_empty has no Russian" in p for p in problems), "an empty Russian passed: %s" % problems)
        check(len(problems) == 3, "problems %s" % problems)
        check("rus/st_test.xml" in outputs, "no Russian table: %s" % sorted(outputs))
        data = outputs["rus/st_test.xml"]
        try:
            text = data.decode("cp1251")
        except UnicodeDecodeError:
            raise Fail("the Russian table isn't windows-1251")
        check("Один" in text, "the Russian isn't readable as windows-1251")
        check('encoding="windows-1251"' in text, "the Russian table's header: %s" % text.splitlines()[0])
        check(text.index('"b_two"') < text.index('"a_one"'), "Russian ids out of the English order")
        check("Два &amp; больше" in text, "the & wasn't escaped")

        # Portuguese: a gap is reported and left out, for the game's English
        check(any("ptb/st_test.xml: c_new has no Portuguese" in n for n in notes), "a missing Portuguese unreported: %s" % notes)
        check(any("ptb/st_test.xml: d_changed's English changed" in n for n in notes), "a changed English unreported: %s" % notes)
        check(any("e_empty has no Portuguese" in n for n in notes), "an empty Portuguese unreported: %s" % notes)
        check(len(notes) == 3, "notes %s" % notes)
        check("ptb/st_test.xml" in outputs, "no Portuguese table: %s" % sorted(outputs))
        data = outputs["ptb/st_test.xml"]
        try:
            text = data.decode("cp1252")
        except UnicodeDecodeError:
            raise Fail("the Portuguese table isn't windows-1252")
        check("Uma facção" in text, "the Portuguese isn't readable as windows-1252")
        check('encoding="windows-1252"' in text, "the Portuguese table's header: %s" % text.splitlines()[0])
        check(text.index('"b_two"') < text.index('"a_one"'), "Portuguese ids out of the English order")
        check("Dois &amp; mais" in text, "the & wasn't escaped in Portuguese")
        for sid in ("c_new", "d_changed", "e_empty"):
            check('"%s"' % sid not in text, "%s is in the Portuguese table, not left to English" % sid)
        return "compared 5 ids in 2 languages: 3 refused in Russian, 3 left to English in Portuguese"
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
        print("FAIL (error): %s: %s" % (type(e).__name__, " | ".join(str(e).splitlines())))
        return 1


if __name__ == "__main__":
    sys.exit(main())
