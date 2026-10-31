# Changelog

## Unreleased

### 0.4.0: territory

- **Fronts on the Factions page.** The Zone's fronts from the last census: each level two
  factions at war both have fighters on, with each side's count, the bigger side first. Your own
  faction's fronts come first, then the biggest, five in all. To make room, the war log shows its
  last six events and your members list five.
- **News from the fronts.** When a side takes the upper hand on a front (two thirds of the
  fighters there), it says so in its own voice, with PDA news set to everything. Only a front that
  was there at the last census and has at least 10 fighters on it counts, and at most two such
  news a day, the biggest fronts first. Loading a save never sets it off.
- **Squads lean toward winning fronts.** When a squad picks where to go next, a smart held by a
  faction its own is at war with weighs more where its faction outnumbers the holder on that
  level, and less where it's outnumbered (from 0.6 to 1.5 times), on levels both sides are on. It's a bias in the game's own
  choice, not an order: no squad is sent anywhere, no squads are added, and story squads, squads
  on a scripted errand, your companions and Homestead's garrisons are left alone. "At war" is the
  game's own enmity, so pairs G.A.M.M.A. starts as enemies (Duty and the Mercenaries) count, and
  so do the wars politics declares. MCM can turn it off, and it's off in Warfare mode. Nothing
  goes into your save.

### 0.3.0: a faction of your own (first part)

- In MCM, found a faction of your own and name it. It is a real faction to the game: it starts
  with the friends and enemies of the faction you came from, and you lead it from your old
  faction, keeping its traders, tasks and dialogs. "You join it" puts you in it yourself; it's off
  unless you choose it, since G.A.M.M.A. doesn't know the faction (the disguise system thinks
  you're in disguise, and content tied to your old faction goes quiet). Your companions join it,
  and leave it when they leave you. Turn it off to disband it: everyone goes back to their old
  faction.
- **Removing the mod is always safe.** No save ever holds your faction: just before each save,
  every member (online, offline or dead) and you are returned to your old factions in the save
  itself, and get your faction back as you play on. Loading a save without the mod finds everyone
  in their old faction. That holds when another mod spreads the faction too: anyone else in it is
  saved in your old faction, and Homestead's saved camp records get the old faction in place of
  yours (it caches a settler's faction when it recruits them, and gives its traders the camp's).
- News when you found or disband it, and when someone joins or leaves. English and Russian.
- **Your faction in politics.** It's a side like any other: its members' kills, and yours while
  you lead it, push its relation with each faction, and it goes to war, makes truces and allies in
  its own name. It starts from the relations it was founded with; a disbanded faction's relations
  are dropped, and a new one starts from its own.
- **The Factions page.** Your side, each faction's standing with it in words and colors, how far
  politics has moved it and which way on its last day, its leader (or that he's dead), the ground
  and fighters from the last census, the war log, your members, and "Restore relations", which
  puts every pair back where it started after a second click. English and Russian.
- **Open it your way:** a PDA tab of its own (Modded Exes' tab registry), its tile in Mod App
  Creator's launcher, or a key in MCM (unbound by default) that opens it in a window of its own.
  Mod App Creator is optional: without it the page has its tab; with it, the tile, or the tab if
  MCM's "Its own PDA tab" is on. From the tile, the page has Back to the launcher.
- Still to come in 0.3.0: settlers who may join as their loyalty grows.

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
