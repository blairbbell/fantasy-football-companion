"""ESPN cookie expiry warning and auth-failure alert. Reads only the expiry timestamp (`espn_s2_expires`, epoch
seconds) from the cookies file; cookie values are never read into output or logs. Notifies through the optional hook.

  python -m ff_companion.cookie_watch check    [--dry-run]  warn when <= warn_days remain; at most once per repeat_days
  python -m ff_companion.cookie_watch authfail [--dry-run]  ESPN answered 401/403: notify once per failure streak
  python -m ff_companion.cookie_watch ok       [--dry-run]  a run succeeded: end the failure streak

Settings (config "cookie_watch"): warn_days (default 21), repeat_days (default 7).
State: <data_dir>/reports/cookie_watch_state.json. --dry-run prints only (no notification, no state write).
`weekly claims` calls ok + check, and the weekly runner calls authfail on an auth error."""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import CFG
from .notify import notify

STATE = CFG["data_dir"] / "reports" / "cookie_watch_state.json"
_C = CFG.get("cookie_watch") or {}
WARN_DAYS = float(_C.get("warn_days", 21))
REPEAT_DAYS = float(_C.get("repeat_days", 7))
AUTH_MSG = "ESPN sign-in expired - refresh the espn_s2 and SWID cookies (see README)."


def read_expiry(path: Path | None = None):
    """Epoch seconds from the cookies file's `espn_s2_expires` key, or None if absent/zero/unreadable."""
    try:
        v = json.loads(Path(path or CFG["cookies_file"]).read_text(encoding="utf-8")).get("espn_s2_expires")
        return float(v) if v else None
    except Exception:
        return None


def decide_expiry(expires, state, now, warn_days=WARN_DAYS, repeat_days=REPEAT_DAYS):
    """Message to send, or None. Pure function."""
    if not expires:
        return None
    days = (expires - now) / 86400.0
    if days > warn_days:
        return None
    if now - (state.get("last_expiry_warn") or 0) < repeat_days * 86400:
        return None
    when = datetime.fromtimestamp(expires).strftime("%Y-%m-%d")
    if days <= 0:
        return f"ESPN cookies expired on {when}. Refresh espn_s2 and SWID (see README)."
    return f"ESPN cookies expire in {int(days)} days ({when}). Refresh espn_s2 and SWID soon (see README)."


def decide_authfail(state) -> bool:
    """True when this failure starts a new streak (notify once). Pure function."""
    return not state.get("auth_failing")


def _load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st), encoding="utf-8")


def check(dry=False, title="Fantasy football"):
    st, now = _load(), time.time()
    msg = decide_expiry(read_expiry(), st, now)
    if not msg:
        print("cookie_watch: nothing to warn about")
        return None
    print("cookie_watch:", msg)
    if not dry:
        print("notify:", notify(title, msg))
        st["last_expiry_warn"] = now
        _save(st)
    return msg


def authfail(dry=False, title="Fantasy football"):
    st = _load()
    if not decide_authfail(st):
        print("cookie_watch: auth failure already reported this streak")
        return None
    print("cookie_watch:", AUTH_MSG)
    if not dry:
        print("notify:", notify(title, AUTH_MSG))
        st["auth_failing"] = True
        st["auth_failed_at"] = time.time()
        _save(st)
    return AUTH_MSG


def ok(dry=False):
    st = _load()
    if st.get("auth_failing") and not dry:
        st["auth_failing"] = False
        _save(st)


def main(argv):
    mode = argv[0] if argv else "check"
    dry = "--dry-run" in argv
    if mode == "check":
        check(dry)
    elif mode == "authfail":
        authfail(dry)
    elif mode == "ok":
        ok(dry)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
