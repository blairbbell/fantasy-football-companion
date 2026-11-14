"""Configuration loading.

Settings come from (later wins):
  1. built-in defaults below
  2. a JSON config file (FF_CONFIG, default ./config.json)
  3. environment variables (FF_SEASON, FF_LEAGUE_ID, FF_TEAM_ID, FF_DATA_DIR, ...)

Nothing personal is hard-coded here. Copy config.example.json -> config.json and .env.example -> .env.
"""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "season": 2026,             # ESPN seasonId for football = the year the season starts
    # Teams to manage. Leave empty and run `python -m ff_companion.discover` to auto-detect every
    # football team on your ESPN account (saved to data/leagues.json). "name" is an optional local label.
    "leagues": [],              # e.g. [{"league_id": 123456, "team_id": 1, "name": "Work league"}]
    "data_dir": "data",         # reports and logs go here (git-ignored)
    "cookies_file": "espn_cookies.json",  # git-ignored; see README
    # Lineup rules
    "doubtful_factor": 0.5,     # weekly projection multiplier for DOUBTFUL players
    # Waiver / free-agent suggestion tuning (waivers.py is suggestions only)
    "waivers": {
        "free_agents_considered": 40,
        "drop_candidates": 7,
        "max_recommendations": 3,
        "injury_ros_factor": {"OUT": 0.7, "INJURY_RESERVE": 0.4, "SUSPENSION": 0.4, "INACTIVE": 0.4, "DOUBTFUL": 0.9},
    },
    "cookie_watch": {"warn_days": 21, "repeat_days": 7},  # cookie expiry warning window / re-warn interval
    # Optional notifications (see README "Notifications"). Leave empty to just print/log.
    "notify_command": "",       # command run as: <command> "<title>" "<message>"
    "notify_url": "",           # URL that accepts a plain-text POST (e.g. a self-hosted ntfy topic)
}

ENV_MAP = {
    "FF_SEASON": ("season", int),
    "FF_DATA_DIR": ("data_dir", str),
    "ESPN_COOKIES_FILE": ("cookies_file", str),
    "FF_NOTIFY_CMD": ("notify_command", str),
    "FF_NOTIFY_URL": ("notify_url", str),
}


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines); does not override real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load() -> dict:
    _load_dotenv(ROOT / ".env")
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg_path = Path(os.environ.get("FF_CONFIG", ROOT / "config.json"))
    if cfg_path.exists():
        _merge(cfg, json.loads(cfg_path.read_text(encoding="utf-8")))
    for env, (key, typ) in ENV_MAP.items():
        if os.environ.get(env):
            cfg[key] = typ(os.environ[env])
    # A single league can also be given purely through the environment.
    if os.environ.get("FF_LEAGUE_ID") and os.environ.get("FF_TEAM_ID"):
        cfg["leagues"] = [{"league_id": int(os.environ["FF_LEAGUE_ID"]), "team_id": int(os.environ["FF_TEAM_ID"]),
                           "name": os.environ.get("FF_LEAGUE_NAME", "")}]
    for key in ("data_dir", "cookies_file"):
        p = Path(cfg[key]).expanduser()
        cfg[key] = p if p.is_absolute() else ROOT / p
    return cfg


CFG = load()
