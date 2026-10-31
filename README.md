# Factions of the Zone

**The Zone's factions as living powers.** They hold ground, grow or bleed, make war and truces,
and talk about it on the PDA. You can stand with one, broker between them, or stay out of it.

A mod for the S.T.A.L.K.E.R. Anomaly modpack G.A.M.M.A. (Anomaly 1.5.3 with Modded Exes), a
sibling to [Seasons of the Zone](https://github.com/devinhorowitz/seasonsofthezone) and
[Arsenal](https://github.com/devinhorowitz/GAMMA-Arsenal-App).

## Status

Early development. **0.1.0 is a census only:** it watches the factions and changes nothing in
your game. The plan is in [docs/DESIGN.md](docs/DESIGN.md).

Once a game day, and once after each load, the census counts every faction's squads and
fighters by tier, rank and level, which faction holds each smart terrain and which are
contested, and the relations between the factions and toward you. Each census is one line in
`fotz_census.jsonl` in the game's appdata folder (`<Anomaly>\appdata`). It writes nothing to your
save. Turn it off in MCM under Factions of the Zone.

`_tools/census_report.py` reads that file and prints the latest census and each day's changes:

```
python _tools/census_report.py "<Anomaly>\appdata\fotz_census.jsonl"
```

## Install

With Claude Code, see [INSTALL-WITH-CLAUDE.md](INSTALL-WITH-CLAUDE.md). By hand: put the
`gamedata` folder in a new MO2 mod and enable it anywhere in the list. It ships only files of its
own (`fotz_*`), so its position doesn't matter. Uninstall by disabling it.

## Development

- `_tools/build.py` writes the Russian string tables, compiles every script under LuaJIT 2.0, runs
  the tests, and installs into an MO2 mods folder (`--check` only checks).
- `_tools/test_census.py` runs the census against a made-up alife; `test_text.py` checks the
  Russian tables' build.
- `_tools/mutants.py` runs each test against broken copies of what it tests (21 so far); every
  one must fail.
- Russian text lives in `_tools/lang/ru.po`, keyed by string id.

## License

MIT. By Devin Horowitz.
