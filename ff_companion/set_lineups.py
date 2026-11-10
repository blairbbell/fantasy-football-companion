"""set_lineups - best weekly lineup for every discovered ESPN football team (LINEUP MOVES ONLY).
Modes:  plan [week]   read-only (default). Builds the exact payload and runs it through the guard without sending.
        run           writes lineup changes for the CURRENT scoring week only.
        verify        re-reads lineups; reports mismatch vs. optimal (unlocked players only).
Rules: weekly ESPN projections in league scoring; bye / no game / OUT / IR / SUSPENSION / INACTIVE players never start;
DOUBTFUL scaled by doubtful_factor (default 50%); locked players (game started) are never moved; IR slot never touched;
no adds/drops. Usage: python -m ff_companion.set_lineups [plan [week]|run|verify]"""
import json, sys, time
from datetime import datetime
from .espn_common import (LOGDIR, REPORTS, SLOTNAME, BENCH, IR, NO_START, session, league, load_leagues, team_roster, pro_schedule,
                          eff_proj, is_locked, optimize, post_lineup, now_str, log_to, ensure_dirs)

LOG = LOGDIR / f"lineups_{datetime.now():%Y%m%d}.log"

def log(m): log_to(LOG, m)

def plan_team(s, L, week, sched):
    j, ros = team_roster(s, L["leagueId"], L["teamId"], week)
    slots = j["settings"]["rosterSettings"]["lineupSlotCounts"] if "settings" in j else None
    if slots is None:
        slots = league(s, L["leagueId"], ["mSettings"])["settings"]["rosterSettings"]["lineupSlotCounts"]
    now_ms = time.time() * 1000
    movable = [p for p in ros if p["slot"] != IR]
    w = {p["id"]: eff_proj(p, week, sched) for p in movable}
    locked = {p["id"] for p in movable if is_locked(p, week, sched, now_ms)}
    desired, total = optimize(movable, slots, w, locked)
    cur_total = round(sum(w[p["id"]] for p in movable if p["slot"] != BENCH), 2)
    diff = [p for p in movable if desired[p["id"]] != p["slot"] and p["id"] not in locked]
    warn = []
    for p in movable:
        if desired[p["id"]] != BENCH and w[p["id"]] == 0:
            warn.append(f"{p['name']} starts with 0 proj (no better option)")
        if p["id"] in locked and p["slot"] != BENCH and w[p["id"]] == 0 and p["inj"] in NO_START:
            warn.append(f"{p['name']} locked in lineup but {p['inj']}")
    return {"j": j, "ros": movable, "slots": slots, "w": w, "locked": locked, "desired": desired,
            "total": total, "cur_total": cur_total, "diff": diff, "warn": warn}

def lineup_text(P):
    order = sorted(P["ros"], key=lambda p: (P["desired"][p["id"]] == BENCH, P["desired"][p["id"]], -P["w"][p["id"]]))
    return [f"    {SLOTNAME.get(P['desired'][p['id']], P['desired'][p['id']]):5s} {p['name']:24s} {p['pos']:4s} proj={P['w'][p['id']]:.1f}"
            f"{' LOCKED' if p['id'] in P['locked'] else ''}{'' if p['inj']=='ACTIVE' else ' '+p['inj']}" for p in order]

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if mode not in ("plan", "run", "verify"): sys.exit(__doc__)
    ensure_dirs()
    s = session(); cfg = load_leagues(); sched = pro_schedule(s)
    report = {"mode": mode, "time": now_str(), "teams": []}; counts = {"ok": 0, "already": 0, "planned": 0, "mismatch": 0, "fail": 0}
    for L in cfg["leagues"]:
        try:
            current = league(s, L["leagueId"], ["mStatus"])["status"]["latestScoringPeriod"]
            week = int(sys.argv[2]) if (mode == "plan" and len(sys.argv) > 2) else current
            P = plan_team(s, L, week, sched)
            log(f"== {now_str()} {mode} | {L['league']} / {L['team']} | week {week} (current {current}) | "
                f"proj now {P['cur_total']} -> best {P['total']} | locked {len(P['locked'])}")
            moves = [f"{p['name']} {SLOTNAME[p['slot']]}->{SLOTNAME[P['desired'][p['id']]]}" for p in P["diff"]]
            entry = {"league": L["league"], "team": L["team"], "week": week, "proj_before": P["cur_total"], "proj_best": P["total"],
                     "moves": moves, "warnings": P["warn"], "lineup": lineup_text(P)}
            status = "already"
            if P["diff"]:
                items = sorted([{"playerId": p["id"], "type": "LINEUP", "fromLineupSlotId": p["slot"], "toLineupSlotId": P["desired"][p["id"]]}
                                for p in P["diff"]], key=lambda it: 0 if it["toLineupSlotId"] == BENCH else 1)
                payload = {"isLeagueManager": False, "teamId": L["teamId"], "type": "ROSTER", "scoringPeriodId": week,
                           "executionType": "EXECUTE", "items": items}
                if mode == "plan":
                    if week == current:
                        r = post_lineup(s, L["leagueId"], payload, L["teamId"], P["ros"], P["slots"], P["locked"], dry=True)
                        log(f"  payload guard check: {r['body']} ({len(items)} items)")
                    else:
                        log("  (future-week preview; lineup can only be written in its own week)")
                    status = "planned"
                elif mode == "verify":
                    status = "mismatch"
                else:
                    r = post_lineup(s, L["leagueId"], payload, L["teamId"], P["ros"], P["slots"], P["locked"])
                    log(f"  POST {r['status']} ({len(items)} items)")
                    if r["status"] not in (200, 201): log(f"  body: {r['body'][:300]}")
                    time.sleep(1)
                    P2 = plan_team(s, L, week, sched)
                    status = "ok" if not P2["diff"] else "fail"
                    if P2["diff"]: entry["remaining"] = [f"{p['name']} {SLOTNAME[p['slot']]}->{SLOTNAME[P2['desired'][p['id']]]}" for p in P2["diff"]]
                    entry["proj_after"] = P2["cur_total"]
            for m in moves: log(f"  move: {m}")
            for w in P["warn"]: log(f"  warn: {w}")
            for line in entry["lineup"]: log(line)
            entry["status"] = status; counts[status] += 1
            log(f"  -> {status}")
        except SystemExit:
            raise
        except Exception as e:
            log(f"== {L['league']}: EXCEPTION {e}")
            entry = {"league": L["league"], "team": L["team"], "status": "fail", "err": str(e)}; counts["fail"] += 1
        report["teams"].append(entry)
    (REPORTS / f"lineup_{mode}_latest.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    log("DONE mode=" + mode + " " + " ".join(f"{k}={v}" for k, v in counts.items()))

if __name__ == "__main__":
    main()
