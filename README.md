# Factions of the Zone

**The Zone's factions as living powers.** They hold ground, grow or bleed, make war and truces,
and talk about it on the PDA. You can stand with one, broker between them, or stay out of it.

A mod for the S.T.A.L.K.E.R. Anomaly modpack G.A.M.M.A. (Anomaly 1.5.3 with Modded Exes), a
sibling to [Seasons of the Zone](https://github.com/devinhorowitz/seasonsofthezone) and
[Arsenal](https://github.com/devinhorowitz/GAMMA-Arsenal-App).

## Status

Early development. The plan is in [docs/DESIGN.md](docs/DESIGN.md).

**Your own faction** (0.3.0, first part). Today you're a loner tied to one faction and its
alliances. In MCM you can found a faction of your own and name it. It's a real faction to the game:
it starts with the friends and enemies of the faction you came from, you lead it from your old
faction (keeping its traders and tasks; you can choose to join it instead), and your companions
join it. Disband it and
everyone goes back to their old faction. Coming next: settlers who may join as their loyalty
grows.

**Politics.** Kills between two factions, ground one takes from the other, fronts where both are
fighting, and a common enemy push each pair's relation. Once a game day the push moves it, within a
daily limit, and old grudges fade. When a pair crosses into enmity, they go to war; after quiet
days, a truce; when a common enemy brings two factions close, an alliance. Each is news on your
PDA in the faction's own voice. Monolith, Sin, ISG, Renegades and the base game's lore pairs (Duty
and Freedom, the Military and the Loners, and others) never change, and every other pair has
limits. The faction you lead is a side too: its members' kills and yours move its relations, and
it goes to war and makes peace in its own name. It steps aside while the base game's dynamic
relations, Fluid Relations, Dynamic Faction Relations Customizer, or Warfare mode handle relations.

**Territory.** Factions at war lean toward the fronts they're winning. When a squad picks where to
go next, ground held by an enemy weighs more where its faction outnumbers that enemy on the level,
and less where it's outnumbered. It's only a bias in the game's own choice: nothing is ordered or
spawned, and story squads, squads on a scripted errand, your companions and Homestead's garrisons
are left alone. The Factions page lists the fronts with each side's fighters, and a side that takes
the upper hand on one says so on your PDA.

**What it saves, and removing it.** Two keys in your save: each pair's change from where the game
started it, and your faction's roster. No character in a save is ever in your faction: just before
each save, everyone is put back in their old faction in the save itself, and gets your faction
back as you play on. Anyone another mod put in your faction is saved in your old one too, and
Homestead's camp records get your old faction in place of it. So removing the mod is always safe,
with no step first: a save loads with every faction's relations as the game had them and everyone
in their old faction.

**Census.** Once a game day, and once after each load, it counts every faction's squads and
fighters by tier, rank and level, which faction holds each smart terrain and which are contested,
and the relations between the factions and toward you. With its log on, each census is one line
in `fotz_census.jsonl` in the game's appdata folder (`<Anomaly>\appdata`).
`_tools/census_report.py` reads that file and prints the latest census and each day's changes:

```
python _tools/census_report.py "<Anomaly>\appdata\fotz_census.jsonl"
```

**The Factions page.** Your side (the faction you lead, or your own), each faction's standing with
it, how far and which way it has moved, its leader, the ground and fighters the census found, the
war log, the fronts, your members, and a button that puts every relation back where it started.

Open it your way: from a PDA tab of its own, from its tile in Mod App Creator's launcher, or with a
key that opens it in a window of its own (sharper than the 3D PDA). Mod App Creator is optional:
without it the page has its tab; with it, the tile, or the tab if you choose it in MCM. The key
works either way.

MCM, under Factions of the Zone: your faction (found or disband it, its name, whether you join it
yourself, off unless you choose it, and whether companions join), politics on or off, the
territory steer, PDA news (off, wars and truces, or everything), the census log, the Factions
page key, and, with Mod App Creator, the page's own PDA tab.

## Install

With Claude Code, see [INSTALL-WITH-CLAUDE.md](INSTALL-WITH-CLAUDE.md). By hand: put the
`gamedata` folder in a new MO2 mod and enable it anywhere in the list. It ships only files of its
own (`fotz_*`), so its position doesn't matter. Uninstall by disabling it.

## Development

- `_tools/build.py` writes the Russian string tables, compiles every script under LuaJIT 2.0, runs
  the tests, and installs into an MO2 mods folder (`--check` only checks).
- `_tools/test_census.py` runs the census against a made-up alife, `test_politics.py` runs the
  politics engine through wars, truces, alliances, saves and stand-downs, `test_faction.py` runs
  your faction through founding, saves (byte-level packets), loads, disguise and disbanding,
  `test_tab.py` checks what the Factions page shows on top of the real politics engine and the
  ways in, `test_territory.py` runs the territory steer against a stand-in for the game's target
  scoring, and `test_text.py` checks the Russian tables' build.
- `_tools/mutants.py` runs each test against broken copies of what it tests (165 so far); every
  one must fail.
- Russian text lives in `_tools/lang/ru.po`, keyed by string id.

## License

MIT. By Devin Horowitz.
