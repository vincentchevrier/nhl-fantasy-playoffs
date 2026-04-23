# NHL Playoff Stats Project

## Context

This repository is a clone of [nhl-api-py](https://github.com/coreyjs/nhl-api-py), a Python wrapper around the NHL API. The library provides an `NHLClient` with modules for teams, standings, schedules, game center, stats, EDGE tracking, and more.

## What Was Built

`playoff_stats.py` — a standalone script that:

1. Fetches all 16 teams in the 2025-2026 NHL playoffs via `client.schedule.playoff_carousel()`
2. Retrieves full rosters for each team via `client.teams.team_roster()`
3. Fetches league-wide regular season skater stats via `client.stats.skater_stats_summary()` (paginated, game_type_id=2)
4. Fetches league-wide regular season goalie stats via `client.stats.goalie_stats_summary()` (paginated)
5. Filters both datasets to only players on playoff rosters
6. Outputs two ranked tables and writes them to JSON

## Output Files

- `playoff_skaters.json` — 394 skaters ranked by regular season points (desc), tiebroken by goals
- `playoff_goalies.json` — 40 goalies ranked by regular season SV% (desc)

### Skater columns
`rank`, `name`, `team`, `position`, `gp`, `goals`, `assists`, `points`

### Goalie columns
`rank`, `name`, `team`, `gp`, `gaa`, `sv_pct`, `shutouts`

## Media Assets

### Player Images
Available via `client.stats.player_career_stats(player_id)`:
- `headshot` — portrait PNG: `https://assets.nhle.com/mugs/nhl/20252026/MTL/8480018.png`
- `heroImage` — action shot JPG (1296×729): `https://assets.nhle.com/mugs/actionshots/1296x729/8480018.jpg`

### Team Logos
- Light SVG via `client.teams.teams()` → `logo` field: `https://assets.nhle.com/logos/nhl/svg/COL_light.svg`
- Both light and dark SVGs via `client.schedule.playoff_carousel()` → `logo` / `darkLogo` fields: `https://assets.nhle.com/logos/nhl/svg/COL_dark.svg`

## Key API Notes

- `skater_stats_summary()` parameter is `game_type_id` (not `game_type`)
- `goalie_stats_summary()` uses `savePct` (not `savePctg`) in its response
- Both endpoints default to `limit=25` — pagination is required to get all players
- `playoff_carousel()` returns series with `topSeed`/`bottomSeed` — both must be extracted to get all 16 teams

## Running

```bash
python3 playoff_stats.py
```
