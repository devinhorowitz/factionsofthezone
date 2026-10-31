# Factions of the Zone

**The Zone's factions as living powers.** They hold ground, grow or bleed, make war and truces,
and talk about it on the PDA. You can stand with one, broker between them, or stay out of it.

A mod for the S.T.A.L.K.E.R. Anomaly modpack G.A.M.M.A. (Anomaly 1.5.3 with Modded Exes), a
sibling to [Seasons of the Zone](https://github.com/devinhorowitz/seasonsofthezone) and
[Arsenal](https://github.com/devinhorowitz/GAMMA-Arsenal-App).

## Status

Early development; 0.2.0 is the first version that changes your game. The plan is in
[docs/DESIGN.md](docs/DESIGN.md).

**Politics.** Kills between two factions, ground one takes from the other, fronts where both are
fighting, and a common enemy push each pair's relation. Once a game day the push moves it, within a
daily limit, and old grudges fade. When a pair crosses into enmity, they go to war; after quiet
days, a truce; when a common enemy brings two factions close, an alliance. Each is news on your
PDA in the faction's own voice. Monolith, Sin, ISG, Renegades and the base game's lore pairs (Duty
and Freedom, the Military and the Loners, and others) never change, and every other pair has
limits. It steps aside while the base game's dynamic relations, Fluid Relations, Dynamic Faction
Relations Customizer, or Warfare mode handle relations.

**What it saves.** One key in your save holds each pair's change from where the game started it.
Every load sets the relations again from that, so turning politics off in MCM, or removing the
mod, puts every faction back.

**Census.** Once a game day, and once after each load, it counts every faction's squads and
fighters by tier, rank and level, which faction holds each smart terrain and which are contested,
and the relations between the factions and toward you. With its log on, each census is one line
in `fotz_census.jsonl` in the game's appdata folder (`<Anomaly>\appdata`).
`_tools/census_report.py` reads that file and prints the latest census and each day's changes:

```
python _tools/census_report.py "<Anomaly>\appdata\fotz_census.jsonl"
```

MCM, under Factions of the Zone: politics on or off, PDA news (off, wars and truces, or
everything), and the census log.

## Install

With Claude Code, see [INSTALL-WITH-CLAUDE.md](INSTALL-WITH-CLAUDE.md). By hand: put the
`gamedata` folder in a new MO2 mod and enable it anywhere in the list. It ships only files of its
own (`fotz_*`), so its position doesn't matter. Uninstall by disabling it.

## Development

- `_tools/build.py` writes the Russian string tables, compiles every script under LuaJIT 2.0, runs
  the tests, and installs into an MO2 mods folder (`--check` only checks).
- `_tools/test_census.py` runs the census against a made-up alife, `test_politics.py` runs the
  politics engine through wars, truces, alliances, saves and stand-downs, and `test_text.py`
  checks the Russian tables' build.
- `_tools/mutants.py` runs each test against broken copies of what it tests (58 so far); every
  one must fail.
- Russian text lives in `_tools/lang/ru.po`, keyed by string id.

## License

MIT. By Devin Horowitz.
