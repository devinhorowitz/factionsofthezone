# Changelog

## 1.1.0 — 2026-11-08

Hooks for other mods, and every place in the news named. Install it over 1.0.0; saves carry on
as they are.

### Added

- **Hooks for other mods** (`fotz_api.script`, [docs/HOOKS.md](docs/HOOKS.md)), first for
  charlies' Zone Civil War:
  - callbacks when ground changes hands, a front tips, a war, truce or alliance starts or ends,
    and each census is done;
  - reads of who holds what, the fronts, where each pair stands, a faction's strength, the events
    and the war log;
  - grievances another mod puts on a pair, paced like kills, which can start a war with news of
    their own;
  - places of interest (`[places]` in the config, or set at run time): ground and fighting there
    count up to three times, a front's squads lean toward them a little more, and their taking
    always makes the news.

### Fixed

- **News names every place.** "We took {place}" and a war over ground or a front named most places
  by their raw ids ("We took ds2_lager_st from Loners"): the game's own names cover only 54. They
  now use the name the PDA map gives ("Darkscape - Cliffside Camp"), else the level's.

## 1.0.0 — 2026-11-07

The first full release: everything 0.1 to 0.6 built, checked over in a deep bug check,
and the Factions page rebuilt to list everything. Install it over 0.6.0; saves carry on as they
are. Reset relations is now in MCM.

### Changed

- **The Factions page lists everything.** It has four subpages under its header: Relations,
  Fighting, Members (while you lead a faction; it says how many are asking to join) and War log.
  Each scrolls, and every list is whole: every faction, fight, perk, member, join request and
  war log entry. No more "and N more", on the page or in the map's hints. The page remembers the
  subpage you chose until the next load.
- **Reset relations moved to MCM.** It's a one-time switch, "Reset relations to a new game's",
  under a warning: every faction's relations go back to a new game's (your faction's to its
  founding), wars, truces and alliances end, and it can't be undone. It acts only in a loaded
  game; set from the main menu, the next load clears it without resetting.
- **Freedom's and Clear Sky's trade perks cover goods their traders carry.** In G.A.M.M.A.,
  Freedom's traders stock no mutant parts and Spore no parts, so neither perk ever applied.
  Freedom's now covers cooked mutant meat, and Clear Sky's detectors and devices.
- **A war your settling causes has its own news,** from the faction whose ground it is: "Wolves
  settled on our ground and stayed." It used to read "took from us" with no place, sometimes in
  your own faction's voice.

### Fixed

- **Your members:**
  - Members on other levels are back in your faction right after every load and level change,
    not only once they come online, so their offline fights count for it.
  - A member's death is noticed however it comes: offline combat, an anomaly, a fall or a blast.
    The dead lose their perks, footprint and place on the page at once.
  - A member is known by name as well as profile: a stranger who gets a dead member's id isn't
    taken for them, and a settler renamed in Homestead stays a member.
  - After the game's own faction change (Duty to Freedom, say), your members treat you as they did
    at founding; before, they could turn hostile.
  - A fallen member's body drops your faction's patch, also after a save.
- **Settlers and outposts:**
  - A member Homestead re-creates after a save stays a member, oath and all.
  - A member whose trip between camps ends (leaving, disbanding, MCM off) no longer leaves their
    squad parked by your camp, and a traveller recruited by hand isn't recruited again.
  - A dead or departed member waiting for a camp no longer asks to join again.
  - A death Homestead handles itself (a raider job gone wrong) reads as a death, not "has left".
  - A sworn member who deserts an unhappy camp heads for another.
  - A traveller's death no longer costs the other travellers loyalty.
  - The news names the camp that fell, or says no camp took them in.
  - A ceasefire never touches whoever gets a dead garrison man's id, a silent knife kill ends it,
    and a companion member's goodwill comes back exactly after a save.
- **Footprint and consequences:**
  - Settling strains only factions whose relations with yours can change: not the Monolith, Sin,
    the ISG, the Renegades, or a faction your old faction's relation with is fixed. The page no
    longer lists the others, nor any strain while politics stands down.
  - Your companions don't count as settled.
  - Killing an arena fighter, a zombie or one of your members no longer costs the ground's holder
    goodwill.
  - A kill in the first seconds after a load or level change finds who holds the ground.
- **While politics stands down** (MCM off, Warfare, the game's dynamic relations), an old war no
  longer turns a perk off, weighs on loyalty, or shows on the page.
- **The page:** a perk at 0% is no longer listed, a tiny one shows "<1%", and the Bandits' map
  perk shows only with a PDA that shows them. The perks, footprint and strain sentences no longer
  run into the footer.
- A save loaded without the faction's declaration keeps its politics state for an install that
  has it.
- `fotz_politics.ltx` says that with MCM installed its sliders set the perk caps, footprint,
  encroach and instigate; the config's values count only without MCM.

## 0.6.0 — 2026-11-07

Install it over 0.5.1; saves carry on as they are.

- **Faction perks.** A member who came from another faction brings a small perk of theirs while
  your faction isn't at war with it: up to 15% off one kind of goods at that faction's traders
  (Loners' food and drink, Ecologists' medicine, Freedom's mutant parts, Duty's repair kits and
  tools, Clear Sky's weapon and armor parts) when you buy, never when you sell; up to 30% off the
  Military's airlifts; a merc squad that turned you down taking your contract after all; a beaten
  outpost up to 15 points likelier to come over (Renegades); and, with one member, Bandit squads
  on your PDA map (PDA 2 and up), or Monolith, Sin and ISG radio chatter. A perk grows with each
  member from that faction, by rank (a legend counts four times a novice; Homestead's promotions
  raise a settler's rank), with each member adding more than the one before, until a full
  Homestead settlement's worth of them reaches the cap. Members count where you are: in full on
  your level, about half a level over, little across the Zone, so a settlement of Duty men in
  Rostok sways Rostok's Duty traders, not Cordon's. The Factions page lists the perks where you
  are. MCM's "Faction perks" turns them off, and its sliders set each cap; the rest is in the
  `[perks]` section of `fotz_politics.ltx`.
- **Your footprint draws your enemies.** The other side of the perks: squads of factions hostile to
  your faction, or to the factions your members came from, are drawn to where your members are,
  from that level and the ones next to it, up to half again as likely to head there with a full
  settlement's worth near (an MCM slider). A Rostok settlement of Duty men brings Freedom's squads
  to Rostok; a small faction barely registers, a giant one draws an immune response, and a mix of
  members spreads the attention over many factions where twenty from one focus one enemy's. The
  Factions page says what your footprint draws where you are.
- **Consequences on others' ground.** Where another faction holds the ground, your members settled
  there strain your faction's relation with it a little each day, more the more of the ground it
  holds and the more members you have there (members who came from that faction don't count, and an
  ally doesn't mind); and a stalker you kill there costs you a little of its goodwill, unless it's
  at war with the victim's faction. The Factions page says what settling where you are strains;
  MCM's sliders set both.
- **Members make relations move more.** For better or worse, at war or not: with members from a
  faction near you, each change in its goodwill toward you (a task, a kill, help) comes with more,
  on the same curve, up to twice the change (an MCM slider), and your faction's relation with it
  moves faster in politics too, by all its members wherever they are.
- **Loyalty hears Homestead directly** (Homestead 1.3.4 and later). A promotion, an expedition
  back and a raid beaten off move your residents' loyalty the moment Homestead reports them, so a
  raid fought between Factions' checks counts too. With an older Homestead, Factions still finds
  them by looking.
- **Tagged Patches.** With Utjan's Tagged Patches, a fallen member's patch says who they were and
  how they died, as other factions' do.

## 0.5.1 — 2026-11-06

Install it over 0.5.0; saves carry on as they are.

- **Your faction's name, not "Your faction"** (asked in the Discord thread). While you lead a
  faction, its name stands in wherever the game names a faction from a script: the inventory's
  card, and other pages that show a faction.
- **Your members' kills are yours to loot** (asked in the thread). G.A.M.M.A.'s NPC Loot Claim kept
  you from looting what a member killed unless they followed you; now a member's kill is yours, as
  a companion's is.
- **Homestead 1.3.4 and later.** Factions hands Homestead your faction through its new faction
  provider: raids on your settlements come from your faction's enemies, and Homestead saves a
  member's old faction, never yours. A member never moves on from your camp when Homestead's
  "settlers move on" is on. With an older Homestead nothing changes.

### Changed

- **Your faction keeps your old faction's lore.** What never changes for the faction you came from
  never changes for yours: founded from the Loners, the Bandits and the Military stay your
  enemies. Before, a quiet spell could end a war with them in a truce, and with "You join it" on,
  they stopped shooting at you. Such a truce in an existing save ends at the next load.

## 0.5.0 — 2026-11-01

Install it over 0.4.1; saves carry on as they are.

- **Settlers who earn their place** (with Homestead). While you lead a faction, the residents of
  your camps grow loyal to it, 0 to 100, with a home, work, a comfortable camp, promotions and
  raids beaten off, and less with campmates lost and your wars against their faction. At 70 one
  asks to join, and you accept or decline on the Factions page, or MCM's "Accept join requests"
  takes every one. A member under 30 goes back to their own faction. A Master who keeps full
  loyalty for two weeks as a member is sworn for life and lifts their whole camp. When a camp
  falls, its sworn members and, at a roll of their loyalty, the others head for another of your
  camps with room, by way of a smart near it that no enemy of yours holds, and move in when they
  get there.
- **Outposts that give up** (with Homestead). Beat a rival outpost of a faction at war with you
  and its last fighters may come over to your faction and head for one of your camps, or
  surrender: a ceasefire of one to three game days before they're hostile again. The greener
  they are, the likelier both; veterans fight to the end. MCM's "Beaten outposts can give up"
  turns it off.

### Fixed

- **"You join it" after the game's own faction change.** Factions kept to the faction you founded
  yours from: once the game moved you to Freedom or Clear Sky, the switch stopped putting you in
  your faction, and a save or disbanding put you back among the faction you'd left. It now follows
  the faction you're in.

## 0.4.1 — 2026-11-01

Install it over 0.4.0; saves carry on as they are.

- **Your faction's patches from every faction's traders.** Sidorovich was the only one who sewed
  them, and a player whose faction is at war with the Loners couldn't get to him. Now each
  faction's own traders at the bases its players start from take the order too (the README lists
  them); the Renegades, who have no trader, buy from the Bandits'. The offer and the patch's
  description no longer place it in Cordon.
- **Your own emblem on the patch.** A guide, `docs/CUSTOM-PATCH.md`, with templates and
  `_tools/make_patch.py`, which makes the files from one picture.

## 0.4.0 — 2026-11-01

The first release: everything below, from the census (0.1.0) to territory (0.4.0).

### Fixed before the first release (a bug sweep)

- **Relations no longer drift further on every load.** The base game puts back relations other
  scripts saved (Banjaji's disguise saves copies of live ones) before Factions read its starting
  values, so Factions' change could count twice and grow load after load, and stay after removing
  the mod. Each relation's last value now goes with the save, and before each save a copy of
  Factions' own value in that store goes back to where the game had it.
- **Another script's change is respected.** A story ceasefire that sets two factions' relations
  ends Factions' war between them and the pair starts over from there, instead of being undone the
  next day; a disguise's change to how your faction sees you holds while you wear it.
- A faction founded with the name box left blank keeps its default name (an options Accept no
  longer renames it to nothing).
- After a save, your members are back in your faction for the rest of the game too (A-Life, offline
  fights and kill credit saw their old faction until they next came near).
- A day whose census log can't be written still counts (politics, territory and the map).
- A truce lasts its five days in every time zone.
- The map markers' hover text breaks onto its own lines.
- Switching from Mod App Creator's tile to the page's own tab while the page is open takes the PDA
  to the new tab; before, it reopened on the map under the page's caption.
- The Factions page: where the fighting is reads "Not counted yet" for the seconds before the
  first census after a load; "Relations restored" shows only when they were.
- A save holding a faction, loaded where the faction isn't declared (a broken install), keeps it
  aside instead of crashing.

### 0.4.0: territory

- **The Factions page, sectioned** like Seasons' and Arsenal's pages: a frame, a header with your
  side and its buttons (the PDA's Relations tab, and Back from Mod App Creator's tile), the
  standings on the left, the war log, the fighting and your members on the right between
  dividers, and a footer with politics' state and Reset relations.
- **Reset relations,** before "Restore relations", says what it does: it puts every relation back
  where it was before the fighting moved it and ends every war, truce and alliance. The first
  click shows what the second will do.
- **Your faction's patch.** Sidorovich has patches sewn for the faction you lead: ask him, and buy
  as many as you like at the item's cost (650 RU). Your members wear it and leave one behind when
  they fall, and it's your faction's emblem on the Factions page. The art is a placeholder (an
  oval patch with the mod's banner) that one file of your own replaces, and a second for Wearable
  Devices' bracer, which shows it on your arm. A save that holds a patch
  can't load without the mod, so MCM's "Remove your faction's patches" takes them all out of the
  game before you remove it.
- **The Factions page in words.** No numbers: the PDA's own Relations tab has them, and a
  button on the page goes there. A row for each faction whose relation with your side can change
  says how it stands with you (at war, hostile, in a truce, neutral, friendly, allied), what holds
  it and since when, and whether it's getting better or worse. The factions that never change
  share a line for each standing ("Permanent enemies: Monolith, Renegades, Sin and UNISG.").
- **Where the fighting is, on the Factions page.** A sentence a level from the last census:
  "Agroprom: Mercenaries winning, your Duty losing". It's about your side where it fights, else
  the level's strongest side, against every enemy it faces there; the verdict (in control,
  winning, ahead, evenly matched) is from its share of the fighters against its biggest enemy. A
  fight needs 10 fighters or more and 3 a side (a big force and a few stragglers isn't one). Your
  side's levels come first, then the biggest, four in all. The war log shows its last four
  events and your members list five.
- **The fighting on the PDA map.** A marker on each level with a fight, at a smart where its two
  main sides meet: red where it's your side's, amber elsewhere, with the two sides named under it
  ("Bandits vs Ecologists"). Hover it for the page's sentence and the factions there hostile to
  you. The markers are never saved, so removing the mod leaves nothing in a save, and MCM can
  turn them off.
- **News from the fronts.** When a side takes the upper hand on a front (two thirds of the
  fighters there), it says so in its own voice, with PDA news set to everything. Only a front that
  was there at the last census and has at least 10 fighters on it counts, and at most two such
  news a day, the biggest fronts first. Loading a save never sets it off.
- **Other mods' squads are left alone.** The steer only weighs squads the game routes itself, so
  squads AlifePlus or ZHOPA direct are never touched. Squads Homestead holds (its camps'
  garrisons, reinforcements and convoys), Capture the Zone's campaign squads (Queen Jadwiga's
  mod) and squads claimed in AlifePlus's owner registry are left alone too, and any mod can claim
  squads it holds with `fotz_territory.add_owner`.
- **Squads lean toward winning fronts.** When a squad picks where to go next, a smart held by a
  faction its own is at war with weighs more where its faction outnumbers the holder on that
  level, and less where it's outnumbered (from 0.6 to 1.5 times), on levels both sides are on.
  It's a bias in the game's own choice, not an order: no squad is sent anywhere, no squads are
  added, and story squads, squads on a scripted errand, your companions and Homestead's
  garrisons are left alone. "At war" is the game's own enmity, so pairs G.A.M.M.A. starts as
  enemies (Duty and the Mercenaries) count, and so do the wars politics declares. MCM can turn
  it off, and it's off in Warfare mode. Nothing goes into your save.

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
