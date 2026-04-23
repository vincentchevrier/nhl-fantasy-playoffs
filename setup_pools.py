"""
setup_pools.py

One-time setup: bins players into draft pools and seeds the database.
Idempotent — safe to re-run.

Pool bins:
  Forwards (C/L/R): top 96 by points → F1=1-8, F2=9-16, ..., F12=89-96
  Defensemen (D):   top 42 by points → D1=1-7, D2=8-14, ..., D6=36-42
  Goalies:          top 28 by sv_pct → G1=1-7, G2=8-14, G3=15-21, G4=22-28
"""

import json
import os
import sys
from app import create_app
from models import db, Player, Goalie, AppSetting

SKATERS_JSON = os.path.join(os.path.dirname(__file__), "playoff_skaters.json")
GOALIES_JSON = os.path.join(os.path.dirname(__file__), "playoff_goalies.json")


def ensure_json_files():
    if not os.path.exists(SKATERS_JSON) or not os.path.exists(GOALIES_JSON):
        print("JSON files not found — running playoff_stats.py...")
        import subprocess
        result = subprocess.run([sys.executable, "playoff_stats.py"], cwd=os.path.dirname(__file__))
        if result.returncode != 0:
            print("ERROR: playoff_stats.py failed.")
            sys.exit(1)


def assign_pool(rank, group_size, prefix):
    """Return pool label like F3 or D2, or None if outside cutoff."""
    pool_num = ((rank - 1) // group_size) + 1
    return f"{prefix}{pool_num}"


def seed_players(skaters):
    forwards = [s for s in skaters if s["position"] in ("C", "L", "R")]
    defensemen = [s for s in skaters if s["position"] == "D"]

    # Sort already by points desc (they come sorted from playoff_stats.py)
    inserted = 0
    for i, p in enumerate(forwards, 1):
        pool = assign_pool(i, 8, "F") if i <= 96 else None
        player = Player(
            id=p["player_id"],
            name=p["name"],
            team=p["team"],
            position=p["position"],
            pool=pool,
            gp=p["gp"],
            goals=p["goals"],
            assists=p["assists"],
            points=p["points"],
        )
        db.session.merge(player)
        inserted += 1

    for i, p in enumerate(defensemen, 1):
        pool = assign_pool(i, 7, "D") if i <= 42 else None
        player = Player(
            id=p["player_id"],
            name=p["name"],
            team=p["team"],
            position=p["position"],
            pool=pool,
            gp=p["gp"],
            goals=p["goals"],
            assists=p["assists"],
            points=p["points"],
        )
        db.session.merge(player)
        inserted += 1

    return inserted


def seed_goalies(goalies):
    inserted = 0
    for i, g in enumerate(goalies, 1):
        pool = assign_pool(i, 7, "G") if i <= 28 else None
        goalie = Goalie(
            id=g["player_id"],
            name=g["name"],
            team=g["team"],
            pool=pool,
            gp=g["gp"],
            wins=g.get("wins", 0),
            gaa=g["gaa"],
            sv_pct=g["sv_pct"],
            shutouts=g["shutouts"],
        )
        db.session.merge(goalie)
        inserted += 1
    return inserted


def main():
    ensure_json_files()

    with open(SKATERS_JSON) as f:
        skaters = json.load(f)
    with open(GOALIES_JSON) as f:
        goalies = json.load(f)

    app = create_app()
    with app.app_context():
        n_players = seed_players(skaters)
        n_goalies = seed_goalies(goalies)
        db.session.commit()

    # Print summary
    forwards = [s for s in skaters if s["position"] in ("C", "L", "R")]
    defensemen = [s for s in skaters if s["position"] == "D"]

    print(f"Seeded {n_players} skaters ({len(forwards)} forwards, {len(defensemen)} defensemen)")
    print(f"Seeded {n_goalies} goalies")
    print()

    # Verify pool counts
    f_pooled = [s for s in forwards if s["rank"] is not None][:96]
    d_pooled = [s for s in defensemen if s["rank"] is not None][:42]
    g_pooled = goalies[:28]

    print("Pool verification:")
    for pool_num in range(1, 13):
        label = f"F{pool_num}"
        start = (pool_num - 1) * 8 + 1
        end = pool_num * 8
        count = len([s for s in forwards[start-1:end]])
        print(f"  {label}: {count} players (ranks {start}–{end})")

    print()
    for pool_num in range(1, 7):
        label = f"D{pool_num}"
        start = (pool_num - 1) * 7 + 1
        end = pool_num * 7
        count = len(defensemen[start-1:end])
        print(f"  {label}: {count} players (ranks {start}–{end})")

    print()
    for pool_num in range(1, 5):
        label = f"G{pool_num}"
        start = (pool_num - 1) * 7 + 1
        end = pool_num * 7
        count = len(goalies[start-1:end])
        print(f"  {label}: {count} goalies (ranks {start}–{end})")

    print("\nDone. Database seeded.")


if __name__ == "__main__":
    main()
