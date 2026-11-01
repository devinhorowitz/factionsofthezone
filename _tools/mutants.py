"""Run every test against its own mutants: each broken copy must make the test print FAIL and exit 1.

A test that passes on a mutant can't catch that defect. A mutant whose text isn't in the script
exactly once also exits non-zero, which would read as "caught", so it is reported apart.
Each test runs once unmutated first, as the control.

    python mutants.py
"""
import importlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ["test_census", "test_text", "test_politics", "test_faction", "test_tab", "test_territory", "test_map", "test_patch", "test_loyalty", "test_outposts"]


def run(test, mutant=None):
    """The exit code and the run's verdict line: its FAIL line if any, else its last line."""
    args = [sys.executable, os.path.join(HERE, test + ".py")] + ([mutant] if mutant else [])
    r = subprocess.run(args, capture_output=True, text=True, cwd=HERE)
    lines = r.stdout.strip().splitlines() or [r.stderr.strip()[-200:]]
    fails = [l for l in lines if l.startswith("FAIL")]
    return r.returncode, (fails or lines)[-1]


def main():
    sys.path.insert(0, HERE)
    bad = 0
    for test in TESTS:
        code, last = run(test)
        print("%-14s control      %s" % (test, last))
        if code != 0:
            bad += 1
            continue
        for name in importlib.import_module(test).MUTANTS:
            code, last = run(test, name)
            if code == 1 and last.startswith("FAIL"):
                verdict = "caught"
            elif code == 2:
                verdict = "DOES NOT APPLY"
                bad += 1
            else:
                verdict = "SURVIVED"
                bad += 1
            print("%-14s %-16s %-14s %s" % (test, name, verdict, last[:90]))
    print("mutants: %s" % ("all caught" if not bad else "%d problems" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
