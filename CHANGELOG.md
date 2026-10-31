# Changelog

## Unreleased

### 0.2.0: the politics engine

- Factions now change their relations. Kills between two factions (near you and offline), ground
  one takes from the other, fronts where both are fighting, and a third faction both are at war
  with all push a pair's relation. Once a game day the push moves it, within a daily limit, and
  what has built up fades back toward where the game started it.
- Crossing the game's lines makes events: a war at -1000 and an alliance at 1000. A war ends in a
  truce after two quiet days (or after two weeks of fighting), and the truce holds the line for
  five days. An alliance lapses when nothing holds it up.
- Factions announce wars, truces and alliances on the PDA in their own voices, with their own
  news icons. MCM sets the level: off, the events, or also the ground they take.
- Lore limits: Monolith, Sin, ISG, Renegades, traders, mutants and Zombified never change, nor do
  the base game's twelve lore pairs (Duty and Freedom, the Military and the Loners, and others).
  Every other pair has caps. All of it is in `configs/plugins/fotz_politics.ltx`, which DLTX can
  edit.
- Relations are rebuilt from the mod's own save data on every load, on top of what the game had,
  so turning the engine off in MCM, or removing the mod, puts every pair back.
- It steps aside while the base game's dynamic relations, Fluid Relations, Dynamic Faction
  Relations Customizer, or Warfare mode handle relations.
- The census also records fronts: which hostile pairs share contested smarts.

### 0.1.0: the census

- Once a game day and after each load, a census counts each faction's squads and fighters by
  tier, rank and level, who holds each smart terrain and which are contested, and the relations
  between factions and toward the player. It writes one JSON line to `fotz_census.jsonl` in the
  game's appdata folder and a summary line to the game's log. It changes nothing in the game and
  nothing in the save.
- MCM page with a switch for the census. English and Russian.
- `_tools/census_report.py` prints the latest census and each day's changes.
