"""Cross-platform weekly runner (Windows/macOS/Linux), for cron, Task Scheduler or launchd.

Usage: python -m ff_companion.weekly [plan|waivers|lineups]
  plan     (default) read-only lineup preview: set_lineups plan. No ESPN writes, no notifications.
  waivers  read-only waiver/free-agent suggestions (never adds, drops or claims); sends the summary
           through the optional notification hook. Typical schedule: the day before waivers process.
  lineups  LIVE: set_lineups run -> verify -> notification summary. LINEUP MOVES ONLY (guarded).
           Typical schedule: Thursday morning before the first game (optionally re-run Sunday morning).
Writes data/logs/weekly_YYYYMMDD.log and a one-line data/logs/LAST_STATUS.
Exit 0 OK, 1 FAIL/WARN, 2 AUTH (cookies expired), 3 GUARD refused a payload."""
import json
import re
import subprocess
import sys
import time
from datetime import datetime

from .config import CFG, ROOT
from .notify import notify

LOGDIR = CFG["data_dir"] / "logs"
REPORTS = CFG["data_dir"] / "reports"
TITLE = "Fantasy football"


def lineup_summary() -> str:
    try:
        r = json.loads((REPORTS / "lineup_run_latest.json").read_text(encoding="utf-8"))
        v = json.loads((REPORTS / "lineup_verify_latest.json").read_text(encoding="utf-8"))
    except Exception as e:
        return f"(no report: {e})"
    vs = {t["league"]: t.get("status") for t in v["teams"]}
    parts = []
    for t in r["teams"]:
        if t.get("status") == "fail" and "err" in t:
            parts.append(f"{t['league']}: ERROR {t['err'][:80]}"); continue
        mv = t.get("moves") or []
        s = f"{t['league']} wk{t['week']}: " + (f"{len(mv)} moves ({'; '.join(m.replace('->', ' to ') for m in mv[:6])})" if mv else "no changes needed")
        s += f", proj {t.get('proj_after', t.get('proj_best'))}"
        if vs.get(t["league"]) not in ("already", None): s += f" [verify: {vs.get(t['league'])}]"
        if t.get("warnings"): s += " | " + "; ".join(t["warnings"][:2])
        parts.append(s)
    return " || ".join(parts)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode not in ("plan", "waivers", "lineups"):
        sys.exit(__doc__)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    for old in LOGDIR.glob("*.log"):
        if time.time() - old.stat().st_mtime > 60 * 86400:
            old.unlink()
    log = LOGDIR / f"weekly_{datetime.now():%Y%m%d}.log"
    status_file = LOGDIR / "LAST_STATUS"
    ts = lambda: datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def write(msg):
        with log.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def status(msg, code, push=False):
        status_file.write_text(f"{ts()} {msg}\n", encoding="utf-8")
        write(f"{ts()} STATUS: {msg}")
        print(msg)
        if push:
            write(f"notify: {notify(TITLE, msg[:900])}")
        sys.exit(code)

    def step(label, *args):
        write(f"--- {ts()} {label}: {' '.join(args)}")
        try:
            p = subprocess.run([sys.executable, "-m", *args], cwd=ROOT, capture_output=True, text=True, timeout=1200)
            out, rc = p.stdout + p.stderr, p.returncode
        except subprocess.TimeoutExpired:
            out, rc = "timeout", 124
        write(out.rstrip())
        write(f"--- {ts()} {label} exit={rc}")
        if re.search(r"cookies expired|POST 40[13]", out, re.I):
            status(f"FAIL AUTH ({label}): ESPN sign-in expired - refresh espn_s2/SWID (see README). Log: {log}", 2, push=mode != "plan")
        if "GUARD REFUSED" in out:
            status(f"FAIL GUARD ({label}): lineup-only guard refused a payload; nothing was sent for it. Log: {log}", 3, push=mode != "plan")
        if rc != 0:
            status(f"FAIL ({label}) exit={rc}. Log: {log}", 1, push=mode != "plan")
        return out

    write(f"===== {ts()} ff_companion.weekly mode={mode} =====")
    if mode == "plan":
        out = step("set_lineups plan", "ff_companion.set_lineups", "plan")
        done = [l for l in out.splitlines() if l.startswith("DONE mode=")]
        summary = done[-1][5:] if done else "no DONE summary line"
        if not done or re.search(r"fail=[1-9]", summary):
            status(f"WARN plan | {summary}. Log: {log}", 1)
        status(f"OK plan | {summary}", 0)
    elif mode == "waivers":
        out = step("waivers", "ff_companion.waivers")
        errors = sum(1 for l in out.splitlines() if l.startswith("ERROR:"))
        if errors:
            status(f"WARN waivers: {errors} league(s) failed. Log: {log}", 1)
        status("OK waivers", 0)
    else:
        run_out = step("set_lineups run", "ff_companion.set_lineups", "run")
        ver_out = step("set_lineups verify", "ff_companion.set_lineups", "verify")
        msg = lineup_summary()
        write(f"notify: {notify('FF lineups set', msg[:900] or f'see log {log}')}")
        if re.search(r"fail=[1-9]|mismatch=[1-9]", run_out + ver_out):
            status(f"WARN lineups: {msg}", 1)
        status(f"OK lineups: {msg}", 0)


if __name__ == "__main__":
    main()
