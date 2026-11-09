# Setup guide (Windows, macOS, Linux)

Fantasy Football Companion is a set of **command-line tools**. It has **no web UI, opens no network port, and
runs no local server**. It only makes outbound HTTPS requests to ESPN's (undocumented, unofficial) fantasy API and,
if you configure one, to your notification hook. The parts are:

- **Read-only:** `discover` (find your teams), `waivers` (pickup suggestions; never adds/drops/claims),
  `set_lineups plan` / `verify`.
- **Lineup writes:** `set_lineups run` and `weekly lineups`, which apply lineup-slot moves only, through a safety guard.

All commands below are run from the repository root folder.

---

## 1. Prerequisites

You need **Python 3.9 or newer** and **Git**.

### Windows 10/11

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
```

Or download Python from https://www.python.org/downloads/windows/ (tick **"Add python.exe to PATH"**) and Git
from https://git-scm.com/download/win. Close and reopen PowerShell, then check:

```powershell
py --version      # or: python --version
git --version
```

### macOS

Install Homebrew from https://brew.sh, then:

```bash
brew install python git
python3 --version
```

(Python is also available from https://www.python.org/downloads/macos/.)

### Linux

Debian / Ubuntu / Raspberry Pi OS:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

Fedora / RHEL:

```bash
sudo dnf install -y python3 python3-pip git
```

Check with `python3 --version`.

---

## 2. Get the code

```bash
git clone https://github.com/blairbbell/fantasy-football-companion.git
cd fantasy-football-companion
```

## 3. Create a virtual environment and install dependencies

Linux / macOS (bash/zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Linux / macOS (fish): `source .venv/bin/activate.fish`

Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Windows (Command Prompt): `.venv\Scripts\activate.bat`

After activation, use `python` for the commands below. You can also skip activation and call the venv's Python
directly: `.venv/bin/python` (Linux/macOS) or `.\.venv\Scripts\python.exe` (Windows).

Quick check (no network, no cookies needed): `python -m tests.test_guard` should end with `GUARD TEST: ALL PASS`.

## 4. Configure

Copy the examples:

| | Linux / macOS | Windows (PowerShell) |
| --- | --- | --- |
| Config | `cp config.example.json config.json` | `Copy-Item config.example.json config.json` |
| Environment (optional) | `cp .env.example .env` | `Copy-Item .env.example .env` |
| Cookie file (option B) | `cp espn_cookies.example.json espn_cookies.json` | `Copy-Item espn_cookies.example.json espn_cookies.json` |

`config.json`, `.env`, `espn_cookies.json` and `data/` are in `.gitignore`. Never commit them.

**Values you fill in yourself:**

| Value | Where to find it | Put it in |
| --- | --- | --- |
| `season` | Year the NFL season starts (2026 season = `2026`) | `config.json` or `FF_SEASON` |
| `leagues[].league_id` | Your ESPN league URL: `...?leagueId=123456` | `config.json` (or `FF_LEAGUE_ID` for one league) |
| `leagues[].team_id` | Your team page URL: `...&teamId=1` | `config.json` (or `FF_TEAM_ID`) |
| `leagues[].name` | Any label you like (only used in reports) | `config.json` |
| `espn_s2`, `SWID` cookies | See below | `.env` (`ESPN_S2`, `ESPN_SWID`) **or** `espn_cookies.json` |

Don't know your ids? Set `"leagues": []` in `config.json`, add your cookies, and run
`python -m ff_companion.discover`. It finds every football team on your ESPN account for the season, prints them,
and saves `data/leagues.json`, which the other tools use automatically while `leagues` is empty.

Lineup slots, bench/IR counts, scoring and waiver rules are read from ESPN, so you don't need to enter them.
Optional tuning: `doubtful_factor`, the `waivers` block, and the notification hook (`notify_command` /
`notify_url`, see the README).

**Getting the ESPN cookies:** log in at https://fantasy.espn.com in a desktop browser, open DevTools
(F12 / Cmd+Opt+I) → **Application** (Chrome/Edge) or **Storage** (Firefox) → **Cookies** → `https://www.espn.com`,
and copy the values of `espn_s2` and `SWID` (keep SWID's curly braces). These cookies are as powerful as your
password: keep them only in `.env` or `espn_cookies.json`, and on Linux/macOS run `chmod 600 .env espn_cookies.json`.

## 5. Run

| Task | Command |
| --- | --- |
| Test the write guard (no network, no cookies) | `python -m tests.test_guard` |
| Find your football teams (read-only) | `python -m ff_companion.discover` |
| Pickup suggestions (read-only) | `python -m ff_companion.waivers --no-push` |
| Preview lineup moves (no writes) | `python -m ff_companion.set_lineups plan` |
| Preview a future week | `python -m ff_companion.set_lineups plan 12` |
| Apply lineup moves on ESPN (current week) | `python -m ff_companion.set_lineups run` |
| Check lineups after a run | `python -m ff_companion.set_lineups verify` |
| Weekly runner, preview (default) | `python -m ff_companion.weekly` |
| Weekly runner, suggestions + notification | `python -m ff_companion.weekly waivers` |
| Weekly runner, live lineups + verify + notification | `python -m ff_companion.weekly lineups` |
| Test your notification hook | `python -m ff_companion.notify "Test" "Hello"` |

Output goes to `data/`: `data/reports/waivers_YYYYMMDD.md`, `data/reports/*_latest.json`,
`data/logs/*.log` and `data/logs/LAST_STATUS`.

Start with `plan` for a week or two and read the output before scheduling `lineups`.

## 6. Schedule it (optional)

Pick times in your local time zone. Waivers usually process overnight on Wednesday in ESPN's default settings,
so Tuesday morning is a good time for suggestions; set lineups Thursday morning before the first game, and
optionally again Sunday morning for late inactives.

**Linux / macOS (cron):** `crontab -e`, then add:

```
0 8 * * 2  cd /path/to/fantasy-football-companion && .venv/bin/python -m ff_companion.weekly waivers
0 8 * * 4  cd /path/to/fantasy-football-companion && .venv/bin/python -m ff_companion.weekly lineups
# optional Sunday re-check for late inactives:
0 11 * * 0 cd /path/to/fantasy-football-companion && .venv/bin/python -m ff_companion.weekly lineups
```

On Linux you can use `scripts/weekly.sh waivers|lineups` instead; it adds a run lock via `flock` when available.

**macOS:** cron is simplest. If cron cannot read the folder, give `cron` Full Disk Access in System Settings →
Privacy & Security, or keep the project outside Documents/Desktop. launchd also works.

**Windows (Task Scheduler, PowerShell):**

```powershell
$dir = "C:\path\to\fantasy-football-companion"
$py  = "$dir\.venv\Scripts\python.exe"
$a1 = New-ScheduledTaskAction -Execute $py -Argument "-m ff_companion.weekly waivers" -WorkingDirectory $dir
$t1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 8am
Register-ScheduledTask -TaskName "FantasyFootballWaivers" -Action $a1 -Trigger $t1
$a2 = New-ScheduledTaskAction -Execute $py -Argument "-m ff_companion.weekly lineups" -WorkingDirectory $dir
$t2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Thursday -At 8am
Register-ScheduledTask -TaskName "FantasyFootballLineups" -Action $a2 -Trigger $t2
```

The computer must be on (and not asleep) at those times.

---

## Troubleshooting

**PowerShell: "running scripts is disabled on this system" when activating the venv**
Allow local scripts for your user only, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Or skip activation and call the venv Python directly: `.\.venv\Scripts\python.exe -m ff_companion.set_lineups`.

**`python` opens the Microsoft Store or is not found (Windows)**
Use `py` instead, or turn off the `python.exe` alias in Settings → Apps → Advanced app settings → App execution aliases.

**`error: externally-managed-environment` (Linux/macOS pip)**
You are installing outside a venv. Create and activate `.venv` (step 3) first.

**`No module named venv` / `ensurepip is not available` (Debian/Ubuntu)**
`sudo apt install python3-venv`.

**`No module named ff_companion`**
Run commands from the repository root (the folder containing `ff_companion/`), and use `python -m ...`, not
`python ff_companion/xyz.py`.

**"No ESPN cookies"**
Set `ESPN_S2` and `ESPN_SWID` in `.env`, or create `espn_cookies.json` (step 4).

**"cookies expired or invalid" / HTTP 401 or 403 / `FAIL AUTH` in LAST_STATUS**
Re-copy `espn_s2` and `SWID` from a logged-in browser. They stop working if you log out of ESPN or change your
password. Make sure SWID still has its `{...}` braces.

**"No leagues configured"**
Add your league(s) to `config.json`, set `FF_LEAGUE_ID` / `FF_TEAM_ID`, or run `python -m ff_companion.discover`.

**`discover` finds 0 teams**
Check `season` (football uses the year the season starts) and that the cookies belong to the ESPN account that
owns the team.

**`GUARD REFUSED` in the log**
The safety guard blocked a non-lineup write; nothing was sent. This is expected protection, not an ESPN error.

**A player wasn't moved**
Players whose game has started are locked and never moved; players in IR slots are never touched. Lineups can only
be written for the current scoring week (`plan <week>` is a preview only).

**Notification didn't arrive**
Run `python -m ff_companion.notify "Test" "Hello"` and check the printed result (`command rc=...` or `url http=...`).

**Firewall / proxy**
The tools only make outbound HTTPS requests and listen on no port. If a proxy blocks `lm-api-reads.fantasy.espn.com`,
`lm-api-writes.fantasy.espn.com` or `fan.api.espn.com`, set `HTTPS_PROXY` or run from another network.

**`SKIP: lock held` in the log (shell wrapper)**
A previous run is still going or crashed; delete `data/logs/.weekly.lock` if no run is active.

**Times or "game locked" look wrong**
The tools use your computer's local time zone. Check the system clock and time zone.
