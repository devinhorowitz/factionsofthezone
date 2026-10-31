# Design

Factions of the Zone makes the Zone's factions living powers. They hold ground, grow or bleed,
make war and truces, and talk about it on the PDA. The player can stand with one, broker between
them, or stay out of it. It is built for G.A.M.M.A. (Anomaly 1.5.3 with Modded Exes, LuaJIT
2.0.4), next to Seasons of the Zone and Arsenal.

This is a plan, not a manual. What exists today is the census (0.1.0).

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
- **The player's own faction comes after 1.0.** It is one faction among many, of the player's
  making, competing for members (see "Later"). Whether it is a declared engine community or a
  script-only allegiance is still open.

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

## 2. The politics engine

- **State per faction:** strength and territory (from the census), supply (a few abstract
  stocks), mood, and an attitude toward every other faction.
- **A daily tick** turns what happened into change: losses and gains by census, ground won or
  lost, kills between factions, emissions, the season (Seasons' `sotz_api` when present), and the
  player's deeds.
- **Wars, truces and alliances are events**, each with a date, a cause, a duration and terms
  ("Duty and Freedom at war since 14 May over the Army Warehouses"). The relation between two
  factions is the configured value plus the effects of the events in force, inside the pair's
  caps. Only events are saved; relations are rebuilt from them.
- **The event deck** (after Zone Frontline): a truce after heavy losses on both sides, a coalition
  against the strongest, incidents, trade, betrayal, ultimatums, prisoner exchanges, escalation.
  A ceasefire waits for the fighting to stop (after DFRC): it is refused while the pair is in
  combat, and alliances can lapse.
- **Paced, not per death** (after Warfare Alife Overhaul 1.6): what happens adds to a pending
  total per pair, applied a few times a game day within a daily budget, with a pull back toward
  the configured value. Relations stay inside ±4750, since `change_faction_relations` resets a
  pair at the limit to 0 half the time. The matrix's columns come from an explicit list:
  `game_relations.factions_table_all` doesn't follow the order of `[communities_relations]`.
- **Lore guardrails:**
  - Monolith, Sin, ISG, Renegades, traders, mutants and Zombified never change, as in the base
    game's dynamic relations.
  - The base game's 12 fixed lore pairs stay fixed, among them Duty–Freedom, Army–Loners and
    Bandits–Duty.
  - Every other pair has caps in a config that DLTX can edit, in the spirit of Fluid Relations.
  - Story characters and quest factions are left alone.
- **One system changes relations.** If the player turns on the base game's dynamic relations,
  or runs Fluid Relations (which replaces `game_relations.script`), Dynamic Faction Relations
  Customizer, or Warfare mode (with Warfare Alife Overhaul's relation pacing), Factions only
  watches and reports. Each of them saves and reapplies relations itself, so reapplying ours on
  load would overwrite theirs. Killing Friends Reduces Goodwill changes the player's goodwill,
  not the matrix, and can run beside it.
- **`game_relations` functions are looked up at call time.** DFRC, Show All Faction Relations and
  Faction Story Safeguard replace or wrap several of them.

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
- **News in the factions' own voices,** signed with portraits, on the PDA only; the player plays
  nearly HUD-less. MCM sets how much.
- English and Russian.

## 5. Partners

- **Homestead** (optional): rival outposts drawn from real strength and territory instead of
  fixed level lists, couriers and turf wars feeding the politics engine, and raids that follow
  the war. What a moving world breaks there (campmates forced friendly every 10 s, cached settler
  factions, turrets that follow the player's relations) is fixed through hooks we ask Homestead's
  author for, not by wrapping its file-local tables.
- **Seasons of the Zone:** winter shortages and quiet fronts, spring offensives, autumn supply
  runs, truces through emissions, ceasefires on the marked days (Apr 26, Dec 14). Its scheduler
  can switch Factions' options by date.
- **Arsenal:** a faction's supply could thin its traders' stock and its squads' gear.
- **Immersive Identification:** identifications could log "last seen" squads for the tab.

## 6. Capture the Zone

Queen-Jadwiga's Capture the Zone (CtZ) is a strategic campaign for Anomaly. Its repository is no
longer public (404 on 2026-10-31), and a search that day found no fork, mirror, archive snapshot
or ModDB page, and no player reports. What is known comes from the Anomaly Development Reference,
which studied Alpha 0.0.5j (commit `eba6660`, a Rostok/Army Warehouses prototype scenario). We
don't plan around it.

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

- **0.1.0 writes nothing to the save.** The census file is outside it.
- **From 0.2.0:** one key, `m_data.fotz`, with a version, the events in force, a short history of
  past ones, and per-faction stocks. Keys are faction and smart names, never object ids.
- **Uninstalling:** the key is ignored, relations return to the configs at the next load, and
  goodwill the player earned stays. Squads the steer moved stay where they went; nothing else in
  the alife is changed.
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
- **PDA:** Show All Faction Relations patches the Relations tab; DFRC and DNM Fixes (on in
  G.A.M.M.A.) patch `dynamic_news_manager`, PDA Message Core reorders news, and AlifePlus holds
  lines. News goes through the helpers, rate-limited.
- **Other:** disguise, faction tasks (dominance tasks target a faction's squads), Faction Story
  Safeguard and Immersive Faction Swap.
- These come from a survey of 23 Anomaly mods on 2026-10-31, as the ones to stay compatible
  with.
- **Performance:** daily work only, nothing per frame. The census reports its own cost.

## Milestones

1. **0.1.0, the census.** Read-only; learn the world.
2. **0.2.0, the politics engine.** Events, relations rebuilt on load, news.
3. **0.3.0, the Factions tab.** Relations, territory, the war log, the player's standing.
4. **0.4.0, territory.** The light steer, fronts in the news and on the map.
5. **0.5.0, partners.** Seasons and Homestead.
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
