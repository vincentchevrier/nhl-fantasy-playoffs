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
- **Goalies:** Wins + Shutouts (shutout win = 2 pts total)

## Features

- User signup/login with forced password change on first login
- Interactive draft page with player hover cards (headshots, team logos, stats)
- Draft locks automatically when admin starts the playoffs
- Live standings with sortable skater and goalie tables
- Per-team roster view with fantasy points breakdown
- Playoff bracket visualization
- Interactive points-over-time chart on the dashboard (Plotly)
- Schedule-aware stat refresh: nightly job + live 5-minute polling during game windows
- Admin panel: manage users, toggle playoff state, force stat refresh

## Setup

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
| `MAIL_SERVER` | SMTP server (e.g. `smtp.gmail.com`) |
| `MAIL_PORT` | SMTP port (e.g. `587`) |
| `MAIL_USE_TLS` | `True` or `False` |
| `MAIL_USERNAME` | SMTP login username |
| `MAIL_PASSWORD` | SMTP login password |
| `MAIL_DEFAULT_SENDER` | From address for outgoing emails |
| `SIGNUP_NOTIFY_EMAIL` | Address that receives new signup notifications |

### Initialize the Database and Draft Pools

Run once before the playoffs start to pull stats and bin players into pools:

```
python setup_pools.py
```

This fetches current playoff rosters and regular season stats from the NHL API, then seeds the database. It is idempotent — safe to re-run.

### Run

```
python app.py
```

The app starts on port 8000. Log in with username `administrator` and the password set in `ADMIN_PASSWORD`.

### Admin workflow

1. Direct users to `/signup` — they submit their email and receive credentials via email
2. Alternatively, create users directly from the Admin panel
3. Users draft their 22 players before the playoffs begin
4. When ready, toggle **Playoffs Started** in the Admin panel — this locks all drafts
5. Stats refresh nightly at 2 AM ET; the scheduler also polls every 5 minutes during live game windows

## Project Structure

```
app.py              # App factory, blueprint registration, scheduler guard
models.py           # SQLAlchemy models
setup_pools.py      # One-time pool seeding script
scheduler.py        # Nightly + live-window stat refresh jobs
playoff_stats.py    # Standalone script to fetch and rank playoff rosters
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
