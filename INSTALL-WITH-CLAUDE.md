# Installing Factions of the Zone with Claude Code

For an AI coding agent (Claude Code or similar) that a player has asked to install, update or
remove Factions of the Zone in their S.T.A.L.K.E.R. G.A.M.M.A. Player: open Claude Code in your
GAMMA folder (where `ModOrganizer.exe` is) and paste:

> Install Factions of the Zone by following https://raw.githubusercontent.com/devinhorowitz/factionsofthezone/main/INSTALL-WITH-CLAUDE.md

Agent: follow these steps in order. Say what you are about to do before each change, and stop
and ask whenever something doesn't match what this guide describes.

## Rules

- Change only `mods\Factions of the Zone` and one line of the active profile's `modlist.txt`.
  Leave every other mod, setting and file alone.
- Never delete. Move anything you replace into a backup folder (below) and say where it went.
- Never press, start or suggest the GAMMA launcher's **Update** button; it can reset the
  player's mod list.
- MO2 and the game must be closed before you touch `modlist.txt`: MO2 writes that file when it
  exits and would undo your edit.
- Don't start the game yourself unless the player asks.

## 1. Check the folder and what's running

1. The working folder must hold `ModOrganizer.exe`, `ModOrganizer.ini`, `mods\` and
   `profiles\`. If not, ask the player where their GAMMA folder is.
2. Run `tasklist`. If `ModOrganizer.exe` or any `Anomaly*.exe` is listed, ask the player to
   close MO2 and the game, then check again.
3. In `ModOrganizer.ini`, `selected_profile=@ByteArray(<name>)` is the active profile (GAMMA's
   is `G.A.M.M.A`); its mod list is `profiles\<name>\modlist.txt`.

## 2. Is it installed already?

It is installed if a folder under `mods\` has `gamedata\scripts\fotz_census.script`. Its version
is the `VERSION = "x.y.z"` line in that script. Below, `<folder>` is that folder's name, or
`Factions of the Zone` for a new install. Installed and current: say so and stop.

## 3. Download and check the release

1. Read `https://api.github.com/repos/devinhorowitz/factionsofthezone/releases/latest`. If there
   is no release yet, tell the player and stop. Take the asset named
   `FactionsOfTheZone-<version>.zip`: its `browser_download_url` and its `digest` (`sha256:...`).
2. Download it into a new folder outside `mods\`, such as `downloads\fotz-<version>\`.
3. Compute its SHA-256 (`certutil -hashfile <zip> SHA256`). It must equal the digest. If it
   doesn't, tell the player and stop.
4. List the zip. It holds one folder, `Factions of the Zone`, with `gamedata\`, `README.md` and
   `LICENSE`. Anything else: stop and ask.

## 4. Install

1. For an update, move `mods\<folder>` to `mods_backup\<folder>-<old version>-<date>` in the
   GAMMA folder.
2. Extract what is inside the zip's `Factions of the Zone` folder to `mods\<folder>`, so that
   `mods\<folder>\gamedata\` exists.
3. For a new install, add the line `+Factions of the Zone` to the profile's `modlist.txt`, right
   after the first line (the `#` comment). Keep the file's CRLF line endings. Its position
   doesn't matter: it ships only files of its own.

## 5. Tell the player

- What was installed, and where any backup went.
- 0.1.0 only watches: once a game day it writes a census of the factions to
  `fotz_census.jsonl` in the game's appdata folder, and changes nothing in the game or the save.
  It can be switched off in MCM under Factions of the Zone.

## Removing it

Close MO2 and the game, change `+Factions of the Zone` to `-Factions of the Zone` in
`modlist.txt`, and move `mods\<folder>` to `mods_backup\`. Saves are unaffected.
