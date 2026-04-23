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
- **Goalies:** Win × 2 + Shutouts × 2 (win = 2pts, shutout win = 4pts total)

## Features

- User signup/login with forced password change on first login
- Interactive draft page with player hover cards (headshots, team logos, stats)
- Draft locks automatically when admin starts the playoffs
- Live standings with sortable skater and goalie tables
- Per-team roster view with fantasy points breakdown
- Playoff bracket visualization
- Interactive points-over-time chart on the dashboard (Plotly)
- Schedule-aware stat refresh: nightly job + live 5-minute polling during game windows
- Admin panel: manage users, seed pools, toggle playoff state, force stat refresh

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
python app.py
```

The app starts on port 8000. Log in with username `administrator` and the password set in `ADMIN_PASSWORD`.

## Deployment

The app runs on a DigitalOcean droplet behind Nginx with a Let's Encrypt TLS certificate. Gunicorn serves the Flask app as a systemd service.

### Deploying changes

```
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
2. Click **Seed Pools from NHL API** — fetches current playoff rosters and bins players into pools (can also be run via `python setup_pools.py`)
3. Direct users to `/signup` to request access, or create accounts directly from the Admin panel
4. Users draft their 22 players before the playoffs begin
5. Toggle **Start Playoffs & Lock Draft** — this locks all submitted teams
6. Stats refresh nightly at 2 AM ET; the scheduler also polls every 5 minutes during live game windows

## Project Structure

```
app.py              # App factory, blueprint registration, scheduler guard
models.py           # SQLAlchemy models
setup_pools.py      # Pool seeding (CLI or called from admin panel)
scheduler.py        # Nightly + live-window stat refresh jobs
playoff_stats.py    # Fetches and ranks playoff rosters from NHL API
routes/
  auth.py           # signup, login, logout, change-password
  draft.py          # Draft page and pick submission
  teams.py          # Team list and team detail
  standings.py      # Dashboard, standings, bracket, about
  admin.py          # Admin panel and actions
templates/          # Jinja2 HTML templates (Bootstrap 5)
static/
  css/style.css
  js/draft.js       # Draft pick state, hover cards, AJAX submit
  js/sortable.js    # Generic click-to-sort table handler
```

## Built With

Designed and developed using [Claude Code](https://claude.ai/claude-code).
