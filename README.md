# Collin's Fantasy Playoffs

A web-based NHL fantasy hockey playoff pool tracker — the digital evolution of Collin's legendary Excel spreadsheet.

Built with Flask + SQLite + Bootstrap 5, powered by the [nhl-api-py](https://github.com/coreyjs/nhl-api-py) NHL Stats API wrapper.

## How It Works

All 16 playoff teams' rosters are pulled at the start of the playoffs. Players are ranked by regular season stats and divided into draft pools so every participant has access to players of similar calibre.

| Pool group | Players per pool | Ranking metric |
|---|---|---|
| F1 – F12 (forwards) | 8 | Regular season points (goals as tiebreaker) |
| D1 – D6 (defensemen) | 7 | Regular season points |
| G1 – G4 (goalies) | 7 | Regular season wins + shutouts |

Each participant drafts **22 players** — one from each pool. Fantasy points are accumulated from playoff stats only:

- **Skaters:** Goals × 2 + Assists
- **Goalies:** Win × 2 + Shutout win × 2 (win = 2 pts, shutout win = 4 pts total)

## Features

- User signup/login with admin approval flow; forced password change on first login
- Interactive draft page with player hover cards (headshots, team logos, regular season stats)
- Draft locks automatically when admin starts the playoffs
- Live standings with sortable skater and goalie tables
- Per-team roster view with fantasy points breakdown
- **Who Took Who** page — grid of all participants × all 22 pools, highlights shared picks
- Playoff bracket visualization (responsive NHL-style layout)
- Interactive points-over-time chart on the dashboard (Plotly)
- Page-load driven stat refresh: schedule checked every 24h, stats pulled every 5 min during live game windows and every 24h otherwise — no background scheduler required
- Player hover cards on draft, standings, and roster pages
- Admin panel: manage users (create, enable/disable, rename, delete), seed pools, toggle playoff state, force stat refresh

## Local Development

### Requirements

```
pip install -r requirements.txt
```

### Environment

Copy `.env.example` to `.env` and fill in values:

```
cp .env.example .env
```

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask secret key (use a long random string in production) |
| `ADMIN_PASSWORD` | Password for the `administrator` account |
| `POOL_OWNER` | Name prefix for the site title (e.g. `Collin's`) |

### Run

```
python3 app.py          # port 8000 by default
PORT=8001 python3 app.py  # override port
```

Log in with username `administrator` and the password set in `ADMIN_PASSWORD`.

## Deployment

The app runs on a DigitalOcean droplet behind Nginx with a Let's Encrypt TLS certificate. Gunicorn serves the Flask app as a systemd service.

### Deploying changes

```bash
# 1. Make and test changes locally
git commit -m "..."
git push

# 2. On the server
cd /opt/nhl-fantasy-playoffs
sudo -u fantasy git pull
systemctl restart fantasy-playoffs
```

### Server layout

| Path | Purpose |
|---|---|
| `/opt/nhl-fantasy-playoffs` | App root |
| `/opt/nhl-fantasy-playoffs/.env` | Environment config (not in repo) |
| `/opt/nhl-fantasy-playoffs/venv` | Python virtualenv |
| `/var/log/fantasy-playoffs/` | Gunicorn access + error logs |
| `/etc/systemd/system/fantasy-playoffs.service` | Systemd unit |
| `/etc/nginx/sites-available/fantasy-playoffs` | Nginx config |

## Admin Workflow

1. Log in as `administrator`
2. Click **Seed Pools from NHL API** — fetches current playoff rosters and bins players into pools
3. Direct users to `/signup` to request access, or create accounts directly from the Admin panel
4. New accounts start disabled — enable them from the user table
5. Users draft their 22 players before the playoffs begin
6. Toggle **Start Playoffs & Lock Draft** — locks all submitted teams
7. Stats update automatically on page load: every 5 min during live games, every 24h otherwise

## Project Structure

```
app.py              # App factory, blueprint registration, after_request refresh hook
models.py           # SQLAlchemy models
refresh.py          # Page-load driven stat refresh logic (schedule check + stats pull)
setup_pools.py      # Pool seeding (called from admin panel)
playoff_stats.py    # Fetches and ranks playoff rosters from NHL API
routes/
  auth.py           # signup, login, logout, change-password
  draft.py          # Draft page and pick submission
  teams.py          # Team list and team detail
  standings.py      # Dashboard, standings, bracket, about, who-took-who
  admin.py          # Admin panel and actions
templates/          # Jinja2 HTML templates (Bootstrap 5)
static/
  css/style.css
  js/draft.js       # Draft pick state, AJAX submit
  js/hovercard.js   # Shared player hover card (draft, standings, roster pages)
  js/sortable.js    # Generic click-to-sort table handler
```

## Built With

Designed and developed using [Claude Code](https://claude.ai/claude-code).
