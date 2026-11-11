"""Cross-platform weekly runner (Windows/macOS/Linux), for cron, Task Scheduler or launchd.

Usage: python -m ff_companion.weekly [plan|waivers|lineups|sunday|sunday-plan|claims|claims-plan]
  plan         (default) read-only lineup preview: set_lineups plan. No ESPN writes, no notifications.
  waivers      read-only waiver/free-agent suggestions (never adds, drops or claims); sends the summary
               through the optional notification hook. Typical schedule: the day before waivers process.
  lineups      LIVE: set_lineups run -> verify -> notification summary. LINEUP MOVES ONLY (guarded).
               Typical schedule: Thursday morning before the first game.
  sunday       LIVE late-inactive recheck: set_lineups run -> verify for the current week, using fresh
               injury tags (OUT / IR / SUSPENSION / INACTIVE; DOUBTFUL still discounted). Locked players
               (game already started) are never moved. Notifies through the optional hook ONLY if a
               lineup changed or an error occurred; stays silent when nothing changed.
  sunday-plan  Preview of the Sunday path: set_lineups plan -> verify. No ESPN writes, no notifications.
  claims       READ-ONLY waiver claim results: notifies which of your claims succeeded / failed / are pending.
               Silent when there is nothing new. Run it after your league's waivers process.
  claims-plan  Same, but print only: no notification and no state written.
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
MODES = ("plan", "waivers", "lineups", "sunday", "sunday-plan", "claims", "claims-plan")


def _load_report(name):
    try:
        return json.loads((REPORTS / name).read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e), "teams": []}


def lineup_outcome(run_report, verify_report=None):
    """Return (summary, changed, errored) from lineup run/plan and verify report dicts.

    `changed` is True if any team has a non-empty moves list. `errored` is True if a team
    failed or verify reported a mismatch/fail. Used by the Sunday runner to decide whether
    to notify (notify when changed or errored; stay silent otherwise).
    """
    if not isinstance(run_report, dict) or run_report.get("_error") or "teams" not in run_report:
        err = (run_report or {}).get("_error", "no report")
        return f"(no report: {err})", False, True
    vs = {}
    if isinstance(verify_report, dict):
        vs = {t.get("league"): t.get("status") for t in verify_report.get("teams") or []}
    parts = []
    changed = False
    errored = False
    for t in run_report.get("teams") or []:
        if t.get("status") == "fail" and "err" in t:
            parts.append(f"{t.get('league', '?')}: ERROR {t['err'][:80]}")
            errored = True
            continue
        mv = t.get("moves") or []
        if mv:
            changed = True
        label = t.get("league") or t.get("team") or "?"
        s = f"{label} wk{t.get('week', '?')}: " + (
            f"{len(mv)} moves ({'; '.join(m.replace('->', ' to ') for m in mv[:6])})" if mv else "no changes needed"
        )
        if t.get("proj_after", t.get("proj_best")) is not None:
            s += f", proj {t.get('proj_after', t.get('proj_best'))}"
        if vs.get(t.get("league")) not in ("already", None):
            s += f" [verify: {vs.get(t['league'])}]"
            if vs.get(t.get("league")) in ("mismatch", "fail"):
                errored = True
        if t.get("status") == "fail":
            errored = True
        if t.get("warnings"):
            s += " | " + "; ".join(t["warnings"][:2])
        parts.append(s)
    for t in (verify_report or {}).get("teams") or []:
        if t.get("status") in ("mismatch", "fail"):
            errored = True
    return (" || ".join(parts) if parts else "see log"), changed, errored


def sunday_need_notify(run_report, verify_report=None, run_verify_text=""):
    """Return (summary, need_notify). Notify if any lineup moved or an error/mismatch occurred."""
    msg, changed, errored = lineup_outcome(run_report, verify_report)
    if run_verify_text and re.search(r"fail=[1-9]|mismatch=[1-9]", run_verify_text):
        errored = True
    return msg, (changed or errored)


def lineup_summary(report_name="lineup_run_latest.json"):
    run = _load_report(report_name)
    verify = _load_report("lineup_verify_latest.json")
    msg, _, _ = lineup_outcome(run, verify)
    return msg


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode not in MODES:
        sys.exit(__doc__)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    for old in LOGDIR.glob("*.log"):
        if time.time() - old.stat().st_mtime > 60 * 86400:
            old.unlink()
    log = LOGDIR / f"weekly_{datetime.now():%Y%m%d}.log"
    status_file = LOGDIR / "LAST_STATUS"
    ts = lambda: datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    notify_on_fault = mode not in ("plan", "sunday-plan", "claims-plan")

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
            status(f"FAIL AUTH ({label}): ESPN sign-in expired - refresh espn_s2/SWID (see README). Log: {log}", 2, push=notify_on_fault)
        if "GUARD REFUSED" in out:
            status(f"FAIL GUARD ({label}): lineup-only guard refused a payload; nothing was sent for it. Log: {log}", 3, push=notify_on_fault)
        if rc != 0:
            status(f"FAIL ({label}) exit={rc}. Log: {log}", 1, push=notify_on_fault)
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
    elif mode in ("claims", "claims-plan"):
        extra = ["--dry-run"] if mode == "claims-plan" else []
        step("claims", "ff_companion.claims", *extra)
        status(f"OK {mode}", 0)
    elif mode == "lineups":
        run_out = step("set_lineups run", "ff_companion.set_lineups", "run")
        ver_out = step("set_lineups verify", "ff_companion.set_lineups", "verify")
        msg = lineup_summary()
        write(f"notify: {notify('FF lineups set', msg[:900] or f'see log {log}')}")
        if re.search(r"fail=[1-9]|mismatch=[1-9]", run_out + ver_out):
            status(f"WARN lineups: {msg}", 1)
        status(f"OK lineups: {msg}", 0)
    else:
        # sunday / sunday-plan
        dry = mode == "sunday-plan"
        if dry:
            run_out = step("set_lineups plan", "ff_companion.set_lineups", "plan")
            report_name = "lineup_plan_latest.json"
        else:
            run_out = step("set_lineups run", "ff_companion.set_lineups", "run")
            report_name = "lineup_run_latest.json"
        ver_out = step("set_lineups verify", "ff_companion.set_lineups", "verify")
        combined = run_out + ver_out
        msg, should = sunday_need_notify(_load_report(report_name), _load_report("lineup_verify_latest.json"), combined)
        run_failed = bool(re.search(r"fail=[1-9]", run_out))
        verify_issue = bool(re.search(r"fail=[1-9]|mismatch=[1-9]", combined))
        if dry:
            write(f"sunday-plan preview: would_notify={int(should)} no writes, no notification; msg={msg}")
            # Verify mismatch is expected on a preview (moves were not applied). Fail only if plan itself failed.
            if run_failed:
                status(f"WARN sunday-plan (preview, no writes, no notification): {msg}", 1)
            status(f"OK sunday-plan (preview, no writes, no notification): {msg}", 0)
        if should or verify_issue:
            write(f"notify: {notify('FF late inactives', msg[:900] or f'see log {log}')}")
        else:
            write("sunday: no lineup changes, no notification")
        if verify_issue:
            status(f"WARN sunday: {msg}", 1)
        status(f"OK sunday: {msg}", 0)


if __name__ == "__main__":
    main()
