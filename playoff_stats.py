"""
playoff_stats.py

Fetches all players from the 2025-2026 NHL playoffs and ranks them
by regular season points. Outputs two JSON files:
  - playoff_skaters.json  — skaters ranked by points (desc)
  - playoff_goalies.json  — goalies ranked by SV% (desc)

Library: nhl-api-py (installed from ./nhl-api-py/)
"""

import json
from nhlpy import NHLClient

client = NHLClient()


def get_playoff_teams(season="20252026"):
    result = client.schedule.playoff_carousel(season=season)
    teams = set()
    for series in result["rounds"][0]["series"]:
        teams.add(series["topSeed"]["abbrev"])
        teams.add(series["bottomSeed"]["abbrev"])
    return teams


def get_rosters(teams, season="20252026"):
    skater_ids = set()
    goalie_ids = set()
    player_team = {}

    for team in teams:
        roster = client.teams.team_roster(team_abbr=team, season=season)
        for group in ["forwards", "defensemen"]:
            for p in roster[group]:
                skater_ids.add(p["id"])
                player_team[p["id"]] = team
        for p in roster["goalies"]:
            goalie_ids.add(p["id"])
            player_team[p["id"]] = team

    return skater_ids, goalie_ids, player_team


def fetch_all_skater_stats(season="20252026"):
    results = []
    start = 0
    while True:
        batch = client.stats.skater_stats_summary(
            start_season=season, end_season=season,
            game_type_id=2, start=start, limit=100
        )
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 100:
            break
        start += 100
    return results


def fetch_all_goalie_stats(season="20252026"):
    results = []
    start = 0
    while True:
        batch = client.stats.goalie_stats_summary(
            start_season=season, end_season=season,
            game_type_id=2, start=start, limit=100
        )
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 100:
            break
        start += 100
    return results


def build_skater_rows(all_skaters, skater_ids, player_team):
    rows = []
    for s in all_skaters:
        if s["playerId"] not in skater_ids:
            continue
        rows.append({
            "rank": None,
            "player_id": s["playerId"],
            "name": s["skaterFullName"],
            "team": player_team[s["playerId"]],
            "position": s["positionCode"],
            "gp": s["gamesPlayed"],
            "goals": s["goals"],
            "assists": s["assists"],
            "points": s["points"],
        })
    rows.sort(key=lambda x: (x["points"], x["goals"]), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def build_goalie_rows(all_goalies, goalie_ids, player_team):
    rows = []
    for g in all_goalies:
        if g["playerId"] not in goalie_ids:
            continue
        rows.append({
            "rank": None,
            "player_id": g["playerId"],
            "name": g["goalieFullName"],
            "team": player_team[g["playerId"]],
            "gp": g["gamesPlayed"],
            "gaa": round(g["goalsAgainstAverage"], 3),
            "sv_pct": round(g["savePct"], 4),
            "shutouts": g["shutouts"],
            "wins": g["wins"],
        })
    rows.sort(key=lambda x: (x["wins"] + x["shutouts"], x["wins"]), reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def print_skater_table(rows):
    print(f"\n{'PLAYOFF SKATERS — Ranked by Regular Season Points':^70}")
    print(f"{'Rank':<6} {'Name':<25} {'Team':<6} {'Pos':<5} {'GP':<5} {'G':<5} {'A':<5} {'PTS':<5}")
    print("-" * 62)
    for r in rows:
        print(f"{r['rank']:<6} {r['name']:<25} {r['team']:<6} {r['position']:<5} "
              f"{r['gp']:<5} {r['goals']:<5} {r['assists']:<5} {r['points']:<5}")


def print_goalie_table(rows):
    print(f"\n{'PLAYOFF GOALIES — Ranked by Wins + Shutouts':^65}")
    print(f"{'Rank':<6} {'Name':<25} {'Team':<6} {'GP':<5} {'W':<5} {'GAA':<7} {'SV%':<8} {'SO':<5}")
    print("-" * 63)
    for r in rows:
        print(f"{r['rank']:<6} {r['name']:<25} {r['team']:<6} {r['gp']:<5} "
              f"{r['wins']:<5} {r['gaa']:<7.3f} {r['sv_pct']:<8.3f} {r['shutouts']:<5}")


def main():
    print("Fetching 2026 playoff teams...")
    teams = get_playoff_teams()
    print(f"  {len(teams)} teams: {sorted(teams)}")

    print("Fetching rosters...")
    skater_ids, goalie_ids, player_team = get_rosters(teams)
    print(f"  {len(skater_ids)} skaters, {len(goalie_ids)} goalies")

    print("Fetching skater stats...")
    all_skaters = fetch_all_skater_stats()
    print(f"  {len(all_skaters)} total skaters in league")

    print("Fetching goalie stats...")
    all_goalies = fetch_all_goalie_stats()
    print(f"  {len(all_goalies)} total goalies in league")

    skater_rows = build_skater_rows(all_skaters, skater_ids, player_team)
    goalie_rows = build_goalie_rows(all_goalies, goalie_ids, player_team)

    print_skater_table(skater_rows)
    print_goalie_table(goalie_rows)

    with open("playoff_skaters.json", "w") as f:
        json.dump(skater_rows, f, indent=2)
    print("\nWrote playoff_skaters.json")

    with open("playoff_goalies.json", "w") as f:
        json.dump(goalie_rows, f, indent=2)
    print("Wrote playoff_goalies.json")


if __name__ == "__main__":
    main()
