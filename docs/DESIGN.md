# Design

Factions of the Zone makes the Zone's factions living powers. They hold ground, grow or bleed,
make war and truces, and talk about it on the PDA. The player can stand with one, broker between
them, or stay out of it. It is built for G.A.M.M.A. (Anomaly 1.5.3 with Modded Exes, LuaJIT
2.0.4), next to Seasons of the Zone and Arsenal.

**Why.** Today the player is a loner tied to one faction and bound to whatever alliances that
faction has. Factions of the Zone fills that gap: make a faction of your own, with a Homestead
settlement as its base; recruit settlers who may, as their loyalty grows, join it; build your own
alliances; and face rival factions that compete with the Zone's own. That also gives warfare
mods, Warfare mode or Capture the Zone, a reason to fight.

**Where it started.** On the G.A.M.M.A. Discord on 2026-10-26, Pikapika asked how close G.A.M.M.A.
was to a mod that lets you start your own faction: in Fallout 4 he ran a mercenary company,
recruiting everyone he could, giving them jobs, helping one faction and hurting another, and
"homestead is like first step of making your own faction". The idea went to Homestead's author the
same hour, and this mod is its faction half.

This is a plan, not a manual. What exists today is the census (0.1.0), the politics engine
(0.2.0) and the first part of your own faction (0.3.0).

## Decisions (2026-10-31)

- **1.0 covers politics and territory.** Relations, dated wars and truces, news, and a light
  steer of squads toward the ground a faction is winning.
- **Saves: its own keys, rebuilt on load.** Faction-to-faction relations come from a short history
  the mod saves under its own key and reapplies on every load. Uninstalled, the factions return to
  the configured relations at the next load. The player's goodwill, which the engine saves itself,
  changes only through the player's deeds, and those changes stay.
- **Homestead is an optional partner.** Everything works without it. With it, Factions reads its
  outposts and settlers, and changes Homestead only through public hooks.
- **Faithful caps.** The base game's fixed factions and lore pairs stay fixed, every other pair
  has caps, and MCM can loosen them.
- **The player's own faction comes next,** ahead of the territory steer: it's why the mod exists.
  It is one faction among many, of the player's making, competing for members (see "Later" for
  the full idea). Whether it is a declared engine community or a script-only allegiance is being
  settled by a prototype.

## Engine facts it rests on

Seen on this install, or read in source and marked so.

- **The relation matrix isn't saved.** `set_community_relation` changes a cached table that every
  level load resets from the configs (source: Anomaly Development Reference, FAC-02). The base
  game's dynamic relations reapply theirs from pstor in `on_game_load`. So relations that follow
  from history must be reapplied after every load and level change.
- **Goodwill is saved.** Each character's goodwill toward a community is in the engine's own
  save (FAC-02).
- **A community must be declared.** `set_character_community` with a community the configs don't
  list reaches assertions (source: FAC-03), and the setter changes neither goodwill, the matrix,
  squad membership nor smart assignment. Communities are the matrix in
  `configs/creatures/game_relations.ltx`, which G.A.M.M.A. Economy ships as a whole file here.
- **A new faction can be declared by DLTX, and it works** (seen 2026-10-31, a prototype):
  - append the faction and its `actor_` twin to `[game_relations] communities`, and give each a
    row in `[communities_relations]` and `[communities_sympathy]`. Every community needs a row,
    but a short row is padded with 0 (neutral), so no other mod's rows need touching and two
    faction mods can coexist;
  - an NPC moved into it stays a member through a save and load, and the player can join it as
    its `actor_` twin;
  - team numbers must stay under 64 (the engine's `max_team_count`, checked only in debug
    builds). Stalker factions use 0-31 and mutants 39-68, so 32-38 are free; another faction mod
    already uses 32 and 33.
- **Removing a declared faction bricks saves that hold members.** Loading such a save without the
  declaration is a fatal error ("item by index not found in section game_relations"; seen
  2026-10-31).
- **But membership can be kept out of every save** (seen 2026-10-31). `save_state` runs before the
  engine writes objects, and a server object's saved faction is 4 bytes in its state packet: after
  the 2-byte header come money (u32), specific character (stringZ), trader flags (s32) and profile
  (stringZ), then the community index (s32). Editing only those bytes, for online, offline and dead
  members alike, puts every member back in their old faction in the save without touching the
  live NPC. A save made that way loads with the declaration removed.
- **Never set a dead NPC's faction.** `set_character_community` on a corpse corrupted the heap; pass
  an NPC's own `squad()` and `group()`, not 0 and 0.
- **No script changes an offline NPC's faction**: the server object only has a getter. The state
  packet edit is the only way.
- **Squads leave without dying.** Homestead, ZCP and others remove squads with `alife_release`, so
  no death callback fires. Strength is counted by census, not by deaths.
- **A smart's `faction` field is set only while it is online.** Offline, who holds a smart has to
  come from the squads there.
- **A squad's `current_action` isn't saved.** After a load it is nil until the squad's next
  update, and offline squads update rarely, so "has it arrived" comes from the smart's arrival
  test (game vertex or distance), not from the squad's action. Seen on the first in-game census:
  read by `current_action`, 6 smarts were held 30 s after a load.
- **Squads can't target squads.** Steer by a smart's name.
- **ZCP owns the squad scripts.** In G.A.M.M.A., `sim_board`, `sim_squad_scripted`,
  `smart_terrain` and `faction_expansions` come from G.A.M.M.A. ZCP 1.4 Balanced Spawns. Factions
  wraps functions there; it never ships those files.
- **The base game's dynamic relations are off** here and by default
  (`alife/general/dynamic_relations`).

## 1. The census (0.1.0)

Once a game day, and once after each load, it counts what the alife holds and writes one JSON
line to `fotz_census.jsonl` in the game's appdata folder. It only reads.

- Each faction's squads and fighters, by tier (the squad section's novice/advanced/veteran), by
  rank and by level, and its story squads.
- Who holds each smart: the faction with the most fighters in squads assigned to the smart that
  have arrived, by the smart's own arrival test (`am_i_reached`). A smart is contested while two
  hostile factions are there at once. Mutants hold nothing.
- The full relation matrix of the 12 player factions, their goodwill toward the player, and their
  relation to the player's community.
- How long it took.

`_tools/census_report.py` prints the latest census and each day's changes: squads and fighters
gained or lost, smarts that changed hands, relations that moved. The point is to learn what
G.A.M.M.A.'s world does on its own before anything changes it. The census is also the politics
engine's input: strength and territory are its counts.

## Your faction (0.3.0, first part)

`fotz_faction.script`, declared in `configs/mod_system_fotz_faction.ltx` (`fotz_own`, team 36, and
its player twin `actor_fotz_own`, team 37).

- **Founding** (MCM, per save): it starts with every relation of the faction you came from (both
  directions, for the faction and its player twin), and it and its twin are friends (2000). You
  join it yourself, unless "You join it" is off; then you lead it from your old faction, keeping its
  traders and tasks. While you're disguised in another faction's suit, you're left alone.
- **Members:** your companions join, with their own squad and group, and leave when they stop
  being companions. A member who comes online is given the faction on the next update, never
  inside net spawn, and only if their id still names them (their profile is checked; ids are
  reused after release).
- **No save holds it.** Before each save every member, online, offline or dead, is set back to
  their old faction in their state packet, and you to yours; the dead are then dropped from the
  roster. You and the online members are back in it on the next update. Removing the mod needs no
  step: tested by founding, saving and loading with Factions disabled.
- **Others in it.** Other mods can spread the faction: Homestead caches each settler's faction
  when it recruits them and gives its camp traders the camp's dominant one, so a companion who
  joined and was then recruited would put `fotz_own` in Homestead's save and onto its traders,
  and Homestead would set it again after Factions is gone (a crash: the faction is undeclared). So
  anyone in the faction who isn't a member is saved in your old faction too (their live faction is
  left alone), and the tables other mods save (`PARTNERS`: Homestead's camps, rival camps,
  expeditions, convoys and retaliation timers) get the old faction in place of ours: a settler's
  own faction where it's known, on each update, at the save and at load. Only a game that has had
  a faction pays for this; the save's sweep reads every object once.
- **Disbanding** (MCM) returns everyone at once: the living and online live, the rest in their
  state packet.
- **Next:** residents of a Homestead settlement who may join as their loyalty grows, and members
  who may leave; the Factions tab with your roster; your faction's relations moved by the politics
  engine like any other's.

## 2. The politics engine (0.2.0)

`fotz_politics.script`, tuned by `configs/plugins/fotz_politics.ltx`.

- **Pressure per pair.** Kills between two factions (online through `npc_on_death_callback`,
  offline by listening in on `game_relations.offline_npc_on_death`), weighted by the victim's rank;
  the player's kills count half, for the player's own faction. From each day's census: smarts one
  faction took from the other since the day before, and fronts, the smarts both are fighting
  over. And a third faction both are at war with pushes two factions together.
- **Paced, not per death** (after Warfare Alife Overhaul 1.6): pressure waits per pair and moves
  the relation once a game day, within a daily budget, and what has built up fades back toward the
  start by a tenth a day, except in a war, which only a truce ends. Changed relations stay inside
  ±4750, since the base game's `change_faction_relations` resets a pair at ±5000 to 0 half the
  time.
- **Events.** A war when a pair crosses -1000, an alliance at 1000; each is dated, with a cause
  (the biggest of recent kills, ground and fronts, and where) and a voice (the side that bled
  most). A war ends in a truce once the pair has two quiet days, or after two weeks; the truce
  holds the line above -1000 for five days and halves new grievances (after DFRC's ceasefires that
  wait for the fighting to stop). An alliance lapses when nothing holds it up.
- **What's saved:** `m_data.fotz`, keyed by faction and smart names: each pair's drift from where
  the game started it, the pressure waiting, the events in force, recent grievances and a history
  of the last 50 events. Relations are rebuilt from the drift on every load (see the save, below).
- **Pairs that start at war stay at war.** In G.A.M.M.A., 7 of the 16 changeable pairs start at
  -2000 (among them Duty–Mercenaries and Clear Sky–Military); they can be pushed further but a
  peace between them is later work. Wars can be declared among the other 9, which start neutral.
- **Lore guardrails:**
  - Monolith, Sin, ISG, Renegades, traders, mutants and Zombified never change, as in the base
    game's dynamic relations.
  - The base game's 12 fixed lore pairs stay fixed, among them Duty–Freedom, Army–Loners and
    Bandits–Duty.
  - Every other pair moves at most -3000 to +2500 from its start; a pair can have its own caps.
  - Story characters and quest factions are left alone: nothing here touches a character.
  - **Open: hubs.** A war with a hub's faction (the Loners at the Skadovsk, Duty at the Bar) brings
    fights there: vanilla targeting lets enemies go for a base between 3 and 6 am, and AlifePlus
    once sent hostile squads to the Skadovsk to trade and heal (its #17). Watch hub smarts in the
    census before deciding whether a declared war should spare them.
- **One system changes relations.** While the base game's dynamic relations, Fluid Relations
  (which replaces `game_relations.script`), Dynamic Faction Relations Customizer, or Warfare mode
  (with Warfare Alife Overhaul's relation pacing) run, Factions writes the game's relations back
  and stops counting. Each of them saves and reapplies relations itself. Killing Friends Reduces
  Goodwill changes the player's goodwill, not the matrix, and can run beside it.
- **Someone else's change wins.** If another script sets a cell Factions manages, that value
  becomes the cell's new start, and Factions' drift goes on top of it.
- **Later:** strength and supply per faction, emissions, the season, the player's deeds beyond
  kills, and the rest of the event deck (after Zone Frontline): a coalition against the strongest,
  incidents, trade, betrayal, ultimatums, prisoner exchanges.

## 3. Territory

- **Control per level** comes from the census: smarts held per faction, contested smarts, and
  fighters on the level.
- **A light steer, a bias and not a command:** squads of a faction at war lean toward contested
  and enemy smarts on fronts it is winning, and away from fronts it is losing. The hook is the
  smart's score in the target choice (`evaluate_prior`, which `simulation_board:get_squad_target`
  ranks), with a bounded multiplier (ZHOPA clamps its own to 0.35-1.5). Factions never sets a
  squad's `scripted_target`; AlifePlus, ZHOPA, P.O.L.I.C.Y and Pathfinder all do, and two
  commanders fight. It never touches story squads, squads with a script target, squads another
  mod owns (AlifePlus's `ap_api.get_owner`, ZHOPA's managed flag, CtZ's mark), or Homestead's
  garrisons.
- **No spawn rows.** AlifePlus writes `respawn_params` and `last_respawn_update` on smarts,
  AlifeBalance and ZCP gate on the latter; Factions leaves them alone.
- **Uninstall-safe wrappers** (after ZHOPA): one switch unwinds every callback and wrapper, and
  a wrapper is put back only if it is still ours.
- **Fronts** show up as news, on the Factions tab and, with mmmint's PDA Map Location Labels, on
  the map.
- **Spawns** follow later and carefully: ZCP and Squad Filler own them in G.A.M.M.A.

## 4. PDA and news

- **A tab of its own** through `pda_dynamic_tabs.register`, plus an MCM key that opens it flat
  (the 3D PDA softens PDA pages). It shows relations with trend arrows, territory, the war log,
  leaders, and the player's standing. The vanilla Relations tab stays.
  - The model is Clear Sky's faction-war page: each side's members, strength and leader.
  - Register it from an actor callback, never during a load (a registration during a load
    crashed in testing).
  - The war log keeps strategic events only (wars, truces, alliances, ground lost and taken), not
    every message.
  - A "restore relations" button: clearing the drift puts every pair back where the game started
    it, mid-save. Six players asked for a way back without a new game.
- **Art by reference only.** The tab points at textures the game already has: the faction icon
  atlas (`ui_mm_faction_<faction>`, 64 px, with inactive variants), leader portraits and the news
  icons. HD packs that replace them (HD Faction Patches, BBFI) show through, and Factions ships no
  art: almost no art addon on ModDB grants reuse.
- **News in the factions' own voices,** signed with portraits, on the PDA only; the player plays
  nearly HUD-less. MCM sets how much. Never an internal id ("dolg", "killer") in a message.
- English and Russian.

## 5. Partners

- **Homestead** (optional): rival outposts drawn from real strength and territory instead of
  fixed level lists, couriers and turf wars feeding the politics engine, and raids that follow
  the war. What a moving world breaks there (campmates forced friendly every 10 s, cached settler
  factions, turrets that follow the player's relations) is fixed through hooks we ask Homestead's
  author for, not by wrapping its file-local tables. Issue #378's follow-up asks for three:
  callbacks for settler events, a supported way to change a settler's community, and the
  prosperity data on the settler record. Since 501f2fe its outposts change hands on their own
  (with a 6-hour cooldown), and wiping a hostile garrison brings a retaliation camp 2 to 4 hours
  later; the census sees both as ground taken.
- **Homestead's custom factions.** Its author has said a coming update brings custom factions with
  an emblem-making GUI (Discord, 2026-10-28), starting from your current relations: the same idea
  as this mod's, from the same conversation. They should be one faction, not two (two declared
  player factions would fight over team ids, the player's faction and save safety): Factions
  keeps the declaration, the relations, the members and the save safety; Homestead keeps the
  flag, the emblem and the settlement, and reads the faction through a hook. Until then its
  Settlement Flag shows a Loner flag for a Factions leader (no
  `homestead_settlement_flag_fotz_own` section; it falls back).
- **Seasons of the Zone:** winter shortages and quiet fronts, spring offensives, autumn supply
  runs, truces through emissions, ceasefires on the marked days (Apr 26, Dec 14). Its scheduler
  can switch Factions' options by date.
- **Arsenal:** a faction's supply could thin its traders' stock and its squads' gear.
- **Immersive Identification:** identifications could log "last seen" squads for the tab.
- **Candidates to ask:** PDA Map Location Labels and Faction Icons (mmmint) for a hook to show
  holders and fronts on the map; KUD Tactical Net (NPCs radio sightings, with an API) for front
  reports; Word of Mouth (NPCs say what they and the area are up to) for gossip about the war.

## 6. Capture the Zone

Queen-Jadwiga's Capture the Zone (CtZ) is a strategic campaign for Anomaly. Its repository is no
longer public (404 on 2026-10-31), and a search that day found no fork, mirror, archive snapshot
or ModDB page, and no player reports. What is known comes from the Anomaly Development Reference,
which studied Alpha 0.0.5j (commit `eba6660`, a Rostok/Army Warehouses prototype scenario). Its
author has since shared a newer build with us privately; how the two could work together is
noted outside this repo until it's public. The points below are about 0.0.5j.

- **What it does:** faction-owned forts at named smarts, campaign squads ("detachments") it marks
  with its own fields and pins to forts or sends on assaults, field and fort battles, a rouble
  economy per faction, and a War PDA with a War Ledger. Its state is one table,
  `m_data.ctz_state`.
- **What we take:**
  - Strength by snapshot, not by death callbacks. CtZ tells a squad that is gone (MISSING) from
    one with no one left (LOST), and waits a while before calling a missing squad lost.
  - Its own ownership model, kept apart from Warfare's.
  - Forts as named anchors, the war ledger, and per-faction stocks, for the politics engine and
    the tab.
- **What we avoid:**
  - Saved state keyed by object ids. CtZ rebinds detachments by numeric id with no check that the
    id still names the same squad, and ids are reused after release. Factions keys its state by
    faction and smart names.
  - World changes on load. CtZ's reconciliation absorbs ambient squads and suppresses others when
    a save loads. Factions' load only reapplies relations.
  - A schema nobody checks. CtZ stamps a save version but never reads it. Factions' key carries a
    version that the load migrates or refuses.
- **Living with it:** if CtZ comes back, Factions leaves squads with its `ctz_campaign_owned`
  mark alone, and its forts could feed the territory score.

Homestead, CtZ and Factions would all move squads; only one should steer a given squad, and a
squad another mod pinned is never steered.

## The save

- **The census writes nothing to the save.** Its file is outside it.
- **0.2.0 adds one key, `m_data.fotz`,** with a version (a save of another version is set aside
  and the engine starts over), each pair's drift, the pressure waiting, the events in force,
  recent grievances, the last census's holders, and a history of past events. Keys are faction and
  smart names, never object ids.
- **Every load** reads each managed cell of the matrix as the game has it after the base game's
  own reapply (at the first update), and sets it to that start plus the pair's drift: the faction
  rows and the player's `actor_` rows, as the base game's dynamic relations do. Turned off in MCM,
  or standing down, it sets the starts back.
- **0.3.0 adds `m_data.fotz_faction`:** your faction's name, the faction you came from, its
  founding relations, and its members (id, old faction, name, profile). No object in the save is
  ever in your faction (see "Your faction").
- **Uninstalling:** the keys are ignored, relations return to the configs at the next load, every
  member and you are in your old factions, and goodwill the player earned stays. Squads the steer
  moved (from 0.4.0) stay where they went; nothing else in the alife is changed.
- The base game's `drx_df_*` pstor keys belong to its dynamic relations; Factions never writes
  them.

## Compatibility to watch

- **Relations:** the base dynamic relations, Fluid Relations, Dynamic Faction Relations
  Customizer, Warfare Alife Overhaul's pacing, Zone Frontline, Killing Friends Reduces Goodwill,
  Sin and Mutants are Allies, GhenTuong's Rostok peace zone, and ZCP's civil war option (it sets
  Monolith's relation to itself; off here).
- **Squads and spawns:** ZCP (owns the squad scripts), Squad Filler, AlifePlus and Xlib (in
  G.A.M.M.A., off in this profile), AlifeBalance, ZHOPA, P.O.L.I.C.Y, Pathfinder, Warfare mode
  (unstable in G.A.M.M.A.), Homestead's garrisons (re-pinned every 10 s).
- **Mods that assume relations stand still.** When Warfare flipped relations, AlifePlus sent ISG
  squads to restock at a now-hostile Clear Sky base (its #7, reported by Warfare Alife Overhaul's
  author; fixed in 357d5e3 along with three more causes). Factions' wars do the same, so test them
  with AlifePlus on before 1.0.
- **PDA:** Show All Faction Relations patches the Relations tab; DFRC and DNM Fixes (on in
  G.A.M.M.A.) patch `dynamic_news_manager`, PDA Message Core reorders news, and AlifePlus holds
  lines. News goes through the helpers, rate-limited.
- **Other:** disguise, faction tasks (dominance tasks target a faction's squads), Faction Story
  Safeguard and Immersive Faction Swap.
- These come from a survey of 23 Anomaly mods on 2026-10-31, as the ones to stay compatible
  with.
- **Your faction, as G.A.M.M.A. sees it** (an audit of every enabled script that reads a faction,
  2026-10-31, about 180 sites in 70 files). When you join it, you're in a faction nothing else
  knows:
  - **Disguise** (Banjaji's, as G.A.M.M.A. patches it) takes any faction other than your home one
    for a disguise. On every load and every armor change it "undisguises" you (a message, NPCs
    forgetting you) and rewrites your faction's relation with your old one from its own saved
    value. Factions puts you back a second later.
  - **Faction-bound content goes quiet:** dialogs gated on your faction, the Mysteries of the Zone
    task, credit for clearing a smart, faction fast travel, PDA v2's squads of your faction, and
    the Chain artefact's bonus.
  - **Latent:** G.A.M.M.A. UI's faction prices script would ask the engine about a faction named
    "fotz" on every trade (a fatal error), but it doesn't load today (its `faction_stocks` is
    missing).
  - Leading from your old faction ("You join it" off) avoids all of these. A story change of your
    faction (`set_actor_true_community`) leaves the faction's record of where you came from stale.
- **Your members, as G.A.M.M.A. sees them:** their bodies get no faction loot, patch or PDA, and
  the news names them with this mod's own strings. Mods that save a member's faction get the old
  one in its place (`PARTNERS`): Homestead's camps, and Fair Autocomplete's kill records (it
  checks a death's faction against relations, a fatal error once ours is undeclared).
  Nothing else in G.A.M.M.A. copies the player's faction onto an NPC, and nothing writes the
  disguise system's `default_faction` from the player's current faction.
- **Performance:** daily work only, nothing per frame. The census reports its own cost.

## What players ask for

From the newest comments on 27 faction addons and 12 forum threads on ModDB (2026-10-31), counted
by how many different people raised each. They shape the plan:

- **A war that keeps moving (about 15).** The top complaint about every faction mod is a Zone where
  nothing happens: factions take ground and stop, relations barely move in two weeks. The census
  should count days with no change on each front, and a front stalled for days gets a nudge.
- **Lore first (about 13).** Players argue pair by pair, and peace mid-firefight or Duty friendly
  with the Military breaks the game for them. This backs the fixed pairs and caps; per-pair caps
  might belong in MCM.
- **No runaway winner (about 9).** Monolith or the Ecologists ending up with the whole map. The
  census should track each faction's share of held smarts; expansion should cost something.
  These two pull against the first, so pacing, caps and fading stay central.
- **A faction or base of one's own (about 9)** and **ground you can see change hands, bases
  included (about 8):** the player's faction (later) and the territory steer (0.4.0).
- **Neutral hubs and peace zones (about 8):** the Bar, the Skadovsk, Yanov. This leans the open
  question about hubs toward sparing them.
- **Deeds, not only kills, move politics (about 8):** tasks done for a faction, rescues. DFRC's
  rule that unseen kills don't count was praised.
- **A way back mid-save (about 6):** the tab's "restore relations" button.
- **News the player controls (about 5),** with no internal names: already the MCM news level.

From the Homestead thread on Discord (June to October 2026), asks that land on Factions:

- **A base for your faction:** base pieces built over days with money, resources and manpower; the
  Palace of Culture taken from Monolith; forward bases.
- **Factions with their own style:** camp types, bonuses and broadcasts by faction.
- **Fixed points to fight over:** places factions claim and build their own structures on, raided
  at night.
- **Camps that make sense:** settlers of hostile factions fought each other until Homestead
  checked residents' relations at recruiting. Those checks don't rerun when a war turns two
  residents' factions hostile; Homestead's periodic "campmates friendly" refresh is what holds a
  camp together, and the territory table it checks (`TERRITORY_RULING_FACTIONS`) is fixed, a place
  for the territory steer to feed through a hook.
- **Show each settler's faction** in the UI: the Factions tab's roster.

**What failed in other faction mods, and Factions' answer:**

- Spawn bloat (hundreds of squads stacked on one smart): Factions spawns nothing.
- Saves bricked during play or after removal: one versioned key, relations rebuilt on load, and
  an uninstall leaves only the key behind.
- Chaos (peace mid-firefight, mutant kills souring relations, everything at war): kills count only
  between two human factions, changes are paced, and the lore pairs never move.
- Story breakage (leaders and traders gone, quest targets killed): Factions never removes or kills
  anyone.
- A whole-file `pda.script` stripping looted PDAs, and Relations-tab patches breaking each other:
  Factions keeps its own tab and ships none of those files.
- Constant polling (a map-labels mod checks every location): daily work only.

## Milestones

1. **0.1.0, the census.** Read-only; learn the world.
2. **0.2.0, the politics engine.** Events, relations rebuilt on load, news. (Built.)
3. **0.3.0, your faction** (founding, companions, disbanding and save safety built). Found it (a name and an emblem), with a Homestead settlement as its
   base; residents who may join as their loyalty grows, and members who may leave; your faction's
   relations moved by the politics engine like any other. The Factions tab comes with it: your
   faction's roster, every faction's relations, the war log, your standing.
4. **0.4.0, territory.** The light steer, fronts in the news and on the map.
5. **0.5.0, partners.** Seasons, Homestead's hooks, Capture the Zone.
6. **1.0.0.**

## Later

- **The player's faction (allegiance and defection).** A settlement recruits residents, but a
  faction keeps members. Residents who prosper drift back to their mother faction unless the
  player brings them into a faction of their own. Members' loyalty rises with prosperity, service
  and victories and falls with losses, hunger and the player's absence; a rival faction's pull
  grows with rank and war. Members defect from a faction that is losing ground. It needs either a
  declared community slot the player names, or a script-only allegiance kept by per-NPC goodwill.
  The Trashman faction mod shows the declared route through DLTX: append the community and its
  `actor_` twin to `communities`, a column to every row of `[communities_relations]`, the two new
  rows and `[communities_sympathy]`, then register it in `squad_community_by_behaviour`, the news
  channels and the Relations tab. Community indices collide between such mods (Trashman takes 32
  and 33), so the slot needs a check at load. NPCs join with `set_character_community` (Convert
  Surrendering Enemies re-registers them in place afterward); the player's own faction change
  goes through `set_actor_true_community`, which Faction Story Safeguard owns, and
  `xr_effects.drx_sl_change_factions`, which Immersive Faction Swap wraps.
- **Diplomacy work** that moves relations: carry terms, broker a ceasefire, escort a convoy,
  sabotage a depot.
- **Standing beyond goodwill:** trust tiers that unlock services, favors, debts, bounties.
- Leaders with temperaments, faction economies that move prices, prisoners and exchanges.
- **Factions with a state of mind** that moves with history: expansion, consolidation, recovery,
  desperation. A defeat makes one faction dig in and another lash out. Holding ground takes
  surviving strength, a faction may raid instead of occupy, and expansion costs exposed fronts, so
  no one snowballs.
- **Not every faction expands** (an idea from CoC Warfare's author): Ecologists go after anomalies
  and data, traders after trade.
- **A Monolith threat from the north** that pushes south now and then (four players asked).
- **Ideas from Clear Sky's Faction War mods:** a squad in trouble radios for help and its faction
  pays you in cash and standing; a front-line informant who sells who holds what; a front that
  falls back a phase when a camp is lost.
- **A base's stock changes hands** when the base does (CoC's Faction Stash Raid).
- **Shared factions ("invasions").** Players share the factions they make, and others let them
  into their own single-player games as rivals, a little like invasions in Dark Souls: turn it on,
  and a faction someone real built competes in your Zone.
  - The game can't go online from Lua. A launcher tool would fetch shared factions before the game
    starts, the way Seasons of the Zone's `play.bat` fetches the weather, and the mod reads them.
  - A shared faction is data only (name, emblem, members, temperament, strength), never code,
    checked on import, names filtered.
  - Each one needs a declared community slot, so the mod would ship a few spare slots beside the
    player's own.
  - Open: the file format, where they're hosted, and how strong an imported faction may start.
- Players have asked AlifePlus for some of the same: NPCs who rise in rank and switch factions
  (#24), leaders, mechanics, medics and traders replaced when killed, with the old bodies cleared
  (#25), a squad member who betrays the rest for loot and turns renegade (#31), and payback for
  wiping squads (#15).
