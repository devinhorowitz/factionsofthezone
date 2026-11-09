# Hooks for other mods

Factions of the Zone tells other mods what its factions do, and lets them weigh in. It was built
first for charlies' Zone Civil War, and it's for any mod that wants Factions' wars and territory.

A mod gets three things:

- **Callbacks:** ground changes hands, a front tips, a war, truce or alliance starts or ends, and
  each census is done.
- **Reads:** who holds a place, where the fronts are, where a pair of factions stands, and how
  strong a faction is.
- **Nudges:** a grievance between two factions, and places of interest that count for more.

## The rules

1. **One script is the contract:** `fotz_api.script`. Everything else in Factions can change
   between versions. `fotz_api.VERSION` is 1. Within version 1, names and fields are only ever
   added, never removed or given a new meaning. A field that's missing means "not known".
2. **Names, never object ids.** Factions are community names (`dolg`, `killer`; `fotz_own` is the
   player's faction). Places are smart names and levels are level names. For display, use
   `fotz_api.name(f)` and `fotz_api.place_name(smart)`, which give what the news shows.
3. **What Factions hands out is a copy.** Changing a payload or a read's result changes nothing in
   Factions. Every handler of one callback gets the same table, though.
4. **Callbacks run inside Factions' daily tick.** Each send is wrapped in its own `pcall`, so a
   handler's error is logged and the tick goes on. A failing handler does stop the handlers after
   it in that one send, so keep handlers short or guard them yourself.
5. **Nudges are paced like everything else.** They wait in the pair's pressure and move the
   relation within the daily budget and the caps. Nothing here sets a relation. To set one
   outright, such as a story ceasefire, set it with `relation_registry` as you would today.
   Factions treats that as another script's change and starts the pair over from the new value.
6. **Factions saves nothing it's given at run time.** A mod sets its places again after each load.
   Grievances waiting for the day's tick are kept in the save.
7. **Standing down.** Politics stands down while MCM turns it off, or while Warfare mode, the base
   game's dynamic relations, DFRC or Fluid Relations runs. Then no politics events fire and
   grievances are refused. The census, ground and front callbacks still fire.

## Callbacks

Factions declares them as it loads, and the game loads every script before it calls any
`on_game_start`, so a mod registers them from its own. Registering one without Factions installed
logs an error, so check first:

```lua
local function on_ground_taken(t)
    printf("%s took %s from %s", t.by, t.place, t["from"])
end

function on_game_start()
    if fotz_api and fotz_api.VERSION >= 1 then
        RegisterScriptCallback("fotz_on_ground_taken", on_ground_taken)
    end
end
```

`from` and `until` are Lua keywords: read them as `t["from"]` and `t["until"]`.

| Callback | When | The table it gets |
|---|---|---|
| `fotz_on_census(c)` | After each census (each new game day, and about 30 s after each load), once Factions has used it | `date` ("YYYY-MM-DD HH:MM"), `cause` ("load" or "day"), `smarts` (smart = faction), `contested` (a list of smarts), `factions` (faction = `squads`, `fighters`, `levels`, which is level = fighters) |
| `fotz_on_ground_taken(t)` | At the daily tick, once for each smart one faction took from another since the day before: every one, not only the three the news shows. A smart left empty isn't "taken". The last census's holders are saved, so a change across a save and load counts. | `smart`, `place` (its display name), `level` (when known), `by`, `from`, `date`, `counted` (whether politics counted it: only pairs it follows, while it runs), `weight` (its place-of-interest weight, 1 if none) |
| `fotz_on_front_shift(t)` | A side newly has the upper hand on a front (two thirds of the two sides' fighters on the level), on fronts of 10 fighters or more. Every one, not only the two a day the news shows; never from the first census after a load. | `level`, `by`, `from`, `by_fighters`, `from_fighters`, `date` |
| `fotz_on_politics(e)` | A war, truce or alliance starts or ends | `kind` ("war", "truce", "alliance", "war_over", "truce_over", "alliance_over"), `a`, `b` (in name order), `day`. A start: `voice` (the side whose news it is); a war's `cause` ("kills", "ground", "front", "settled", "incident") and `at` and `place` when it has one; a truce's `until`; an alliance's `enemy` when a common enemy made it. An end: `since`, and `why`: "truce" (a war ending in one), "expired" (a truce), "lapsed" (an alliance), "changed" (another script set the pair), "reset" (MCM's reset) or "disbanded" (the player's faction is gone) |

## Reads

All are functions of `fotz_api`.

| Function | Returns |
|---|---|
| `VERSION` | 1 (a number, not a function) |
| `active()` | true, or false and the reason politics stands down |
| `sides()` | the factions politics follows, yours included while you lead one |
| `name(f)` | the faction's name as the news gives it ("Mercenaries", or your faction's name) |
| `place_name(smart)` | the place as the news gives it ("Darkscape - Cliffside Camp") |
| `holder(smart)` | the faction holding it at the last census, or nil; before the first census after a load, the save's |
| `contested(smart)` | true if two hostile factions were both there at the last census |
| `held(f)` | the smarts `f` held at the last census, by name |
| `strength(f)` | `squads`, `fighters` and `levels` (level = fighters) at the last census, or nil |
| `fronts()` | the fronts, biggest first: `level`, `a`, `b`, `fa`, `fb`, `leader` (nil while it's close) |
| `pair(a, b)` | nil for a pair Factions never moves; else `relation` (live, a toward b), `start` (without Factions' drift), `drift`, `pending` (the pressure waiting; a grievance joins it at the next daily tick), `trend` (the day's move), and `event` (`kind`, `a`, `b`, `since`, `until`, `cause`, `at`, `voice`, `enemy`) or nil |
| `events()` | the wars, truces and alliances in force, the oldest first, as `pair`'s `event` |
| `history(n)` | the last `n` events (all of them without `n`), newest first: the page's War log |
| `census()` | the last census, as `fotz_on_census` gives it, or nil |
| `own()` | the player's faction (`id`, `name`, `mother`, `founded`, `members`, the living ones), or nil |
| `place_weight(smart)` | its weight as a place of interest, 1 if it's none |

`strength`, `contested`, `census` and `fronts` know nothing until the first census after a load.

## Nudges

**`fotz_api.grievance(a, b, amount, opts)`** returns true when Factions counts it.

- `amount` is in relation points: negative pushes toward war, positive toward peace, at most 1,500
  either way. It waits for the day's tick and joins the pair's pressure as kills do: halved during
  a truce, and moved by the daily budget within the caps.
- Factions refuses it (false) for a fixed pair or a faction that never changes, a pair it doesn't
  follow, a zero or a non-number, or while politics stands down.
- A negative one counts as the cause "incident". `opts.at` names a smart for the war news. If an
  incident is what tips the pair into war, `opts.news` gives that news a string id of the mod's
  own, with the fields `{b}` and `{place}`; else the news is Factions' own ("{b} crossed us at
  {place} once too often").

```lua
-- the Mercenaries raided the Loners' stash at Darkscape's Cliffside Camp
fotz_api.grievance("stalker", "killer", -300, { at = "ds2_lager_st", news = "st_mymod_raid_war" })
```

**Places of interest** count for more. A weight goes from 1 to 3.

- **By config:** Factions ships an empty `[places]` section in
  `configs/plugins/fotz_politics.ltx`. A mod extends it with a DLTX file of its own,
  `configs/plugins/mod_fotz_politics_<mod>.ltx`:

  ```ini
  ![places]
  esc_smart_terrain_2_12 = 3     ; Cordon - Rookie Village
  mar_smart_terrain_12_2 = 2     ; Great Swamp - Northern Village
  ```

- **At run time:** `fotz_api.set_place(smart, weight)`, and `fotz_api.clear_place(smart)` to drop
  it again (the config's weight stays). They aren't saved; set them again after each load.
- **What a weight does:**
  - Ground taken there counts `weight` times toward the pair's pressure, and so does fighting
    there. A front's war news names its heaviest place.
  - On a front, squads at war with the place's holder lean toward it a little more: the steer's
    multiplier there is raised by `1 + place_pull * (weight - 1)` (`place_pull` is 0.2) and stays
    within `lo` and `hi`.
  - Ground taken at a place of interest always makes the news, even past the three a day.

## Zone Civil War

**What its matrix does to Factions.** Zone Civil War starts every pair at -2000, below the war
line. Factions declares a war only when a pair crosses that line, so it never declares one there,
the same as for the 7 pairs G.A.M.M.A. starts at war. With no wars there are no truces, and no
alliances either, so `fotz_on_politics` stays quiet.

What still runs:

- kills and ground as pressure, which can only push pairs further down, to the caps;
- the territory steer and the fronts: with enmity everywhere, every level two factions share is a
  front;
- the ground and upper-hand news, the fronts on the map, and the player's faction.

Zone Civil War replaces the whole of `game_relations.ltx`. Factions declares its own faction by
DLTX, so the declaration survives that.

**What the hooks give it:**

- `fotz_on_ground_taken` and `fotz_on_front_shift` for its story beats;
- places of interest for "places factions fight over";
- grievances for its own incidents.

**A question for charlies:** should Factions treat a pair that starts at war as a war in force?
Then two quiet days could end it in a truce. That would turn "everyone at war" into wars that end,
which Zone Civil War likely doesn't want. Factions keeps its rule unless asked. If asked, it would
be a config option, off by default.

## Later

- **Events for the player's faction** (`fotz_on_faction`): founded, disbanded, and a member who
  joined, left or died.
- **A veto before a war or truce,** if a mod asks for one, like Homestead's
  `homestead_on_before_settler_leave` with its flags.
- **Places of interest** on the map and on the Factions page.
