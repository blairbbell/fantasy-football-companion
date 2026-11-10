# Fantasy Football Companion

A small, local, browserless companion for **ESPN Fantasy Football** managers. It runs on any machine with
Python 3 (a Raspberry Pi works well), handles one or several leagues at once, and:

- **Discovers** every football team on your ESPN account (or uses the leagues you list in `config.json`).
- **Suggests waiver / free-agent pickups** each week by comparing the best available players with your weakest
  droppable players, using next week's best-lineup projection and rest-of-season strength (byes and injuries
  counted). **Suggestions only:** it never adds, drops, claims or bids.
- **Optimizes your weekly lineup** (Hungarian assignment over your league's lineup slots, including FLEX / OP /
  D/ST / K) from ESPN's weekly projections. Players on bye, without a game, or tagged OUT / IR / SUSPENSION / INACTIVE never
  start; DOUBTFUL players are discounted; players whose game has started are never moved.
- **Writes lineup moves only.** Every write goes through a guard that refuses anything other than a lineup-slot
  move between players already on your own roster: no adds, drops, waiver claims, trades or IR moves.
- Includes a **cross-platform weekly runner** (defaults to a read-only preview) with logs, a one-line status file,
  and an **optional, pluggable notification hook** (any command or a plain-text POST URL such as ntfy).

> **Unofficial tool.** This project is not affiliated with, endorsed by, or supported by ESPN or The Walt Disney Company.
> It uses undocumented ESPN fantasy API endpoints that can change or break at any time. You are responsible for
> complying with ESPN's Terms of Use and your league's rules. Use it only for teams you manage, and at your own risk.

## Quick start

Full per-OS instructions (Windows, macOS, Linux), scheduling and troubleshooting: **[docs/SETUP.md](docs/SETUP.md)**.

```bash
git clone https://github.com/blairbbell/fantasy-football-companion.git
cd fantasy-football-companion
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp config.example.json config.json                     # Windows: Copy-Item config.example.json config.json
cp .env.example .env                                   # then add your ESPN cookies (and league ids)
python -m tests.test_guard                             # offline self-test of the write guard
python -m tests.test_weekly                            # offline self-test of the Sunday notify decision
python -m ff_companion.discover                        # optional: auto-detect your football teams
python -m ff_companion.set_lineups                     # preview lineup moves (no writes)
python -m ff_companion.waivers --no-push               # pickup suggestions (read-only)
```

This is a command-line tool: there is no web UI, URL or port. Results are written to `data/`.

## Requirements

- Python 3.9+
- `requests` (`pip install -r requirements.txt`)
- Optional: `flock` (standard on Linux) for the lock in `scripts/weekly.sh`; `python -m ff_companion.weekly` works on every OS

## Configuration

`config.json`, `.env`, cookie files and everything under `data/` are git-ignored.

| Key | Meaning |
| --- | --- |
| `season` | ESPN `seasonId`; for football it is the year the season **starts** (2026 season = `2026`) |
| `leagues` | List of `{"league_id", "team_id", "name"}`. `name` is just a local label. Leave the list empty to use `data/leagues.json` written by `discover` |
| `doubtful_factor` | Multiplier on a DOUBTFUL player's weekly projection (default `0.5`) |
| `waivers` | Tuning for suggestions: how many free agents / drop candidates to compare, max suggestions per team, and the rest-of-season discount for injured players |
| `notify_command` / `notify_url` | Optional notification hook (see below) |
| `data_dir` / `cookies_file` | Where reports/logs and the cookie file live (relative to the repo root) |

Lineup slots, roster size, bench and IR counts, scoring and waiver settings are read from ESPN at run time, so
you do not need to copy them into the config.

Environment overrides: `FF_SEASON`, `FF_LEAGUE_ID` + `FF_TEAM_ID` (+ `FF_LEAGUE_NAME`) for a single league,
`FF_DATA_DIR`, `FF_CONFIG`, `ESPN_COOKIES_FILE`, `ESPN_S2`, `ESPN_SWID`, `FF_NOTIFY_CMD`, `FF_NOTIFY_URL`.

### Authentication

ESPN leagues need the two cookies from a logged-in browser session, `espn_s2` and `SWID`.

1. Log in at fantasy.espn.com in your browser.
2. Open DevTools → Application/Storage → Cookies → `espn.com`, and copy `espn_s2` and `SWID` (keep the braces on SWID).
3. Either put them in `.env` as `ESPN_S2` / `ESPN_SWID`, or copy `espn_cookies.example.json` to `espn_cookies.json`
   and fill it in (`chmod 600 espn_cookies.json`). `espn_s2_expires` (epoch seconds) is optional and enables an
   expiry warning.

These cookies give full access to your ESPN account. Never commit, paste or share them. They stop working when
you log out or change your password; the tools report "cookies expired" on HTTP 401/403.

### Notifications (optional)

Nothing is sent anywhere unless you configure a hook:

- `notify_command` / `FF_NOTIFY_CMD`: run as `<command> "<title>" "<message>"`. Point it at your own script for
  Pushover, Telegram, a chat webhook, email, etc. Quiet hours are up to your script.
- `notify_url` / `FF_NOTIFY_URL`: the message is POSTed as plain text with a `Title` header (works with ntfy).

Test it with `python -m ff_companion.notify "Test" "Hello"`. Without a hook, messages are printed and logged.

## Usage

```bash
python -m ff_companion.discover            # read-only: find your football teams -> data/leagues.json
python -m ff_companion.waivers             # read-only pickup suggestions -> data/reports/waivers_YYYYMMDD.md (+ notification)
python -m ff_companion.waivers --no-push   # same, without the notification
python -m ff_companion.set_lineups         # plan (read-only; builds the payload and checks it with the guard, sends nothing)
python -m ff_companion.set_lineups plan 12 # preview a future week
python -m ff_companion.set_lineups run     # WRITES lineup changes to ESPN for the current week
python -m ff_companion.set_lineups verify  # re-reads lineups and reports anything not optimal
python -m tests.test_guard                 # proves the write guard blocks non-lineup payloads (no network)
python -m tests.test_weekly                # proves the Sunday path notifies only on a change or error (no network)
```

Weekly automation (any OS):

```bash
python -m ff_companion.weekly                # plan: read-only lineup preview (default)
python -m ff_companion.weekly waivers        # suggestions + notification
python -m ff_companion.weekly lineups        # LIVE: set lineups, verify, notification
python -m ff_companion.weekly sunday         # LIVE late-inactive recheck; notifies only if a lineup changed or an error occurred
python -m ff_companion.weekly sunday-plan    # preview of the Sunday path (no writes, no notification)
scripts/weekly.sh [plan|waivers|lineups|sunday|sunday-plan]   # Linux/macOS wrapper with a run lock
```

A typical schedule: `waivers` the morning before your league's waivers process, `lineups` on Thursday morning
before the first game, and `sunday` around 11:00 AM local time to swap out starters who are now OUT, IR or
inactive (players whose games have already started, such as early London/9:30 AM games, are never moved).
The Sunday run uses the same lineup-only guard and notifies only if a lineup actually changed or an error
occurred; it stays silent when nothing changed. `sunday-plan` is a dry-run of that path.
Logs go to `data/logs/weekly_YYYYMMDD.log` (60 days kept); `data/logs/LAST_STATUS` holds a one-line status:
`OK`, `WARN`, `FAIL AUTH`, `FAIL GUARD` or `FAIL`.

## How it values players

- **Lineups:** ESPN's weekly projection in your league's scoring. Zero for byes, no game, OUT / IR / SUSPENSION / INACTIVE;
  DOUBTFUL scaled by `doubtful_factor`. Players already in an IR slot are never touched.
- **Waivers:** rest-of-season points per game (ESPN projection blended with actual), times remaining games,
  discounted for injuries, plus the change in next week's best lineup. A swap is suggested only if it clearly
  improves the lineup now or for the rest of the season. Notes flag OUT players that could use an open IR slot
  and slots you cannot fill with a player who has a game.

## License

MIT, see [LICENSE](LICENSE).
