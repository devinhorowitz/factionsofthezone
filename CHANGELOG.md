# Changelog

## Unreleased

### 0.1.0: the census

- Once a game day and after each load, a census counts each faction's squads and fighters by
  tier, rank and level, who holds each smart terrain and which are contested, and the relations
  between factions and toward the player. It writes one JSON line to `fotz_census.jsonl` in the
  game's appdata folder and a summary line to the game's log. It changes nothing in the game and
  nothing in the save.
- MCM page with a switch for the census. English and Russian.
- `_tools/census_report.py` prints the latest census and each day's changes.
