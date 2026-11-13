"""waivers - weekly waiver-wire / free-agent check for every discovered ESPN football team.
RECOMMENDATIONS ONLY: never adds, drops, claims or bids. Read-only against ESPN.
For each team: compares top free agents / waiver players against the weakest droppable roster players using
(a) next week's best-lineup projection, (b) rest-of-season starting-lineup strength (ESPN ROS projection per game,
blended with actual), with byes and injuries counted. Writes data/reports/waivers_<date>.md/.json and sends a
summary through the optional notification hook.
Usage: python -m ff_companion.waivers [--no-push]"""
import json, sys, time
from datetime import datetime
from .config import CFG
from .espn_common import (LOGDIR, REPORTS, SEASON, SLOTNAME, BENCH, IR, NO_START, session, get, league, league_url,
                          load_leagues, team_roster, pro_schedule, week_started, eff_proj, ros_ppg, optimize, active_slots,
                          player_row, notify, now_str, log_to, ensure_dirs)

LOG = LOGDIR / f"waivers_{datetime.now():%Y%m%d}.log"
_W = CFG["waivers"]
N_FA, N_DROP, N_REC = int(_W["free_agents_considered"]), int(_W["drop_candidates"]), int(_W["max_recommendations"])
INJ_FACTOR = dict(_W["injury_ros_factor"])   # discount rest-of-season value for injured players

def log(m): log_to(LOG, m)

def games_left(pro, sched, w0, w1):
    g = sched.get(pro, {}).get("games", {})
    return sum(1 for w in range(w0, w1 + 1) if g.get(w))

def free_agents(s, lid, week, slot_ids):
    base = {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "filterSlotIds": {"value": slot_ids}, "limit": 75,
            "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [f"00{SEASON}", f"10{SEASON}", f"11{SEASON}{week}"]}}
    out = {}
    for sort in ({"sortPercOwned": {"sortPriority": 1, "sortAsc": False}},
                 {"sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 1, "value": f"11{SEASON}{week}"}},
                 {"sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 1, "value": f"10{SEASON}"}}):
        j = get(s, league_url(lid), params=[("view", "kona_player_info"), ("scoringPeriodId", str(week))],
                filt={"players": {**base, **sort}})
        for pe in j.get("players", []):
            r = player_row(pe, BENCH); r["status"] = pe.get("status"); r["waiverDate"] = pe.get("waiverProcessDate")
            out[r["id"]] = r
        time.sleep(0.5)
    return list(out.values())

def lineup_val(players, slots, weights):
    return optimize([{**p, "slot": BENCH} for p in players], slots, weights)[1]

IR_FLAGS = ("INJURY_RESERVE", "OUT", "DOUBTFUL")   # injury tags worth an IR suggestion, most severe first

def ir_suggestions(roster, ir_open, starters=None):
    """Bench players who could move to an open IR slot (suggestion only; nothing is ever sent to ESPN).
    Needs: on the bench, an IR-flag injury tag, and ESPN lists IR (slot 21) as eligible for him. A DOUBTFUL player
    is only suggested when he is not in the projected best lineup. Most severe first, at most ir_open entries."""
    if ir_open <= 0: return []
    starters = starters or {}
    c = [p for p in roster if p.get("slot") == BENCH and p["inj"] in IR_FLAGS and IR in (p.get("elig") or [])
         and not (p["inj"] == "DOUBTFUL" and starters.get(p["id"]) not in (None, BENCH))]
    c.sort(key=lambda p: (IR_FLAGS.index(p["inj"]), p["ros"]))
    return c[:ir_open]

def bye_headsup(roster, act, starters_next, week, sched):
    """Info only. Players currently in a starting slot whose team is on bye in `week`, plus starting spots that the
    projected best lineup cannot fill with a player who has a game. Never changes anything."""
    byes = [{"name": p["name"], "pos": p["pos"]} for p in roster
            if p.get("slot") in act and not sched.get(p["pro"], {}).get("games", {}).get(week)
            and sched.get(p["pro"], {}).get("bye") == week]
    open_spots = []
    for sl, c in sorted(act.items()):
        n = sum(1 for p in roster if starters_next.get(p["id"]) == sl and p["next"] > 0)
        if n < c: open_spots.append(f"{c - n} {SLOTNAME.get(sl, sl)}")
    return {"byes": byes, "open": open_spots}

def bye_text(b, week):
    """One-line text for the report/notification, or '' when there is nothing to flag."""
    if not b or not (b["byes"] or b["open"]): return ""
    parts = []
    if b["byes"]: parts.append("byes among starters: " + ", ".join(f"{x['name']} ({x['pos']})" for x in b["byes"]))
    if b["open"]: parts.append("open starting spots: " + ", ".join(b["open"]))
    return f"wk{week} " + "; ".join(parts)

def analyse(s, L, week, final, sched):
    j, ros = team_roster(s, L["leagueId"], L["teamId"], week)
    slots = j["settings"]["rosterSettings"]["lineupSlotCounts"]
    team = next(t for t in j["teams"] if t["id"] == L["teamId"])
    acq = j["settings"]["acquisitionSettings"]
    act = active_slots(slots)
    nweeks = max(1, final - week + 1)
    def enrich(p):
        p["next"] = eff_proj(p, week, sched)
        gl = games_left(p["pro"], sched, week, final)
        ppg = ros_ppg(p["raw"]) * INJ_FACTOR.get(p["inj"], 1.0)
        p["ppg"] = round(ppg, 2); p["ros"] = round(ppg * gl, 1)
        p["bye"] = sched.get(p["pro"], {}).get("bye")
        return p
    roster = [enrich(p) for p in ros if p["slot"] != IR]
    ir_slot = [p for p in ros if p["slot"] == IR]
    fas = [enrich(p) for p in free_agents(s, L["leagueId"], week, sorted(act))]
    fas = [p for p in fas if p["inj"] not in NO_START]          # never recommend adding an OUT/IR/suspended player
    fas.sort(key=lambda p: -(p["ros"] + 2 * p["next"]))
    fas = fas[:N_FA]
    drops = sorted(roster, key=lambda p: p["ros"] + 2 * p["next"])[:N_DROP]
    wn = lambda ps: {p["id"]: p["next"] for p in ps}
    wr = lambda ps: {p["id"]: p["ppg"] for p in ps}
    base_next = lineup_val(roster, slots, wn(roster)); base_ros = lineup_val(roster, slots, wr(roster))
    cands = []
    for a in fas:
        for d in drops:
            new = [p for p in roster if p["id"] != d["id"]] + [a]
            dn = round(lineup_val(new, slots, wn(new)) - base_next, 2)
            dr = round(lineup_val(new, slots, wr(new)) - base_ros, 2)
            depth = round(a["ros"] - d["ros"], 1)
            good = (dr >= 0.5 and dn >= -1.0) or (dn >= 2.0 and dr >= -0.5) or (depth >= 15 and a["posId"] == d["posId"] and dn >= 0 and dr >= 0)
            if good:
                cands.append({"add": a, "drop": d, "dn": dn, "dr": dr, "depth": depth,
                              "score": round(dr * nweeks * 0.6 + dn + 0.1 * depth, 2)})
    cands.sort(key=lambda c: -c["score"])
    recs, used_a, used_d = [], set(), set()
    for c in cands:
        if c["add"]["id"] in used_a or c["drop"]["id"] in used_d: continue
        recs.append(c); used_a.add(c["add"]["id"]); used_d.add(c["drop"]["id"])
        if len(recs) >= N_REC: break
    notes = []
    ir_cap = slots.get(str(IR), 0) - len(ir_slot)
    starters_next = optimize([{**p, "slot": BENCH} for p in roster], slots, wn(roster))[0]
    ir_moves = [{"name": p["name"], "pos": p["pos"], "inj": p["inj"]} for p in ir_suggestions(roster, ir_cap, starters_next)]
    for p in ir_slot:
        if p["inj"] in ("ACTIVE", "QUESTIONABLE"):
            notes.append(f"{p['name']} is in IR but now {p['inj']} - ESPN may block moves until he leaves IR")
    for sl, c in act.items():
        n = sum(1 for p in roster if starters_next.get(p["id"]) == sl and p["next"] > 0)
        if n < c: notes.append(f"week {week}: only {n}/{c} {SLOTNAME.get(sl, sl)} slot(s) can be filled with a player who has a game")
    bye = bye_headsup(roster, act, starters_next, week, sched)
    return {"league": L["league"], "team": L["team"], "week": week, "bye": bye, "waiverRank": team.get("waiverRank"),
            "acq": acq.get("acquisitionType"), "faab": acq.get("isUsingAcquisitionBudget"),
            "budget_left": (acq.get("acquisitionBudget") or 0) - ((team.get("transactionCounter") or {}).get("acquisitionBudgetSpent") or 0),
            "waiverDays": acq.get("waiverProcessDays"), "waiverHour": acq.get("waiverProcessHour"),
            "base_next": base_next, "recs": recs, "notes": notes, "ir_open": ir_cap, "ir_moves": ir_moves}

def fmt_player(p):
    tag = "W" if p.get("status") == "WAIVERS" else ("FA" if p.get("status") == "FREEAGENT" else "")
    inj = "" if p["inj"] == "ACTIVE" else f", {p['inj'].replace('INJURY_RESERVE','IR').lower()}"
    return f"{p['name']} ({p['pos']}{', '+tag if tag else ''}{inj})"

def strip(o):
    if isinstance(o, dict): return {k: strip(v) for k, v in o.items() if k not in ("raw", "elig")}
    if isinstance(o, list): return [strip(x) for x in o]
    return o

def main():
    push = "--no-push" not in sys.argv
    ensure_dirs()
    s = session(); cfg = load_leagues(); sched = pro_schedule(s)
    out = []
    for L in cfg["leagues"]:
        try:
            st = league(s, L["leagueId"], ["mStatus"])["status"]
            latest, final = st["latestScoringPeriod"], st["finalScoringPeriod"]
            week = latest + 1 if week_started(sched, latest) and latest < final else latest
            r = analyse(s, L, week, final, sched)
        except SystemExit:
            raise
        except Exception as e:
            r = {"league": L["league"], "team": L["team"], "error": str(e)}
        out.append(r)
    md = [f"# Fantasy football waiver check - {now_str()}", "", "Recommendations only; nothing was added, dropped or claimed.", ""]
    pushes = []
    for r in out:
        md.append(f"## {r['league']} - {r['team']}")
        if "error" in r:
            md.append(f"ERROR: {r['error']}"); pushes.append((r["league"], f"Waiver check failed: {r['error'][:120]}")); continue
        wd = ", ".join(d[:3].title() for d in (r["waiverDays"] or []))
        md.append(f"Week {r['week']} | waiver priority #{r['waiverRank']} | {r['acq']}{' FAAB $'+str(r['budget_left']) if r['faab'] else ''}"
                  f" | waivers process {wd} ~{r['waiverHour']}:00 | best lineup proj {r['base_next']}")
        lines = []
        for c in r["recs"]:
            a, d = c["add"], c["drop"]
            md.append(f"- ADD {fmt_player(a)} proj {a['next']:.1f} wk{r['week']}, ROS {a['ros']} | DROP {fmt_player(d)} proj {d['next']:.1f}, ROS {d['ros']}"
                      f" | lineup +{c['dn']} next wk, {c['dr']:+} pts/wk ROS")
            if d["inj"] in ("OUT", "INJURY_RESERVE") and r.get("ir_open", 0) > 0:
                md[-1] += " | or move him to an open IR slot instead of dropping"
            lines.append(f"+{a['name']} ({a['pos']}{', waivers' if a.get('status')=='WAIVERS' else ''}) for -{d['name']}: {c['dn']:+.1f} wk{r['week']}, {c['dr']:+.1f}/wk ROS")
        if not r["recs"]: md.append("- No add/drop clearly improves this team this week."); lines.append("No clear upgrades on the wire.")
        irl = [f"{m['name']} ({m['pos']}, {m['inj'].replace('INJURY_RESERVE','IR').lower()})" for m in r.get("ir_moves", [])]
        for m in irl: md.append(f"- IR SUGGESTION: move {m} from the bench to an open IR slot ({r['ir_open']} open) - frees a roster spot; do it in ESPN yourself")
        byet = bye_text(r.get("bye"), r["week"])
        if byet: md.append(f"- BYE HEADS-UP: {byet} (info only; set your lineup in ESPN)")
        for n in r["notes"]: md.append(f"- note: {n}")
        pushes.append((r["league"], f"{r['team']} wk{r['week']} (waiver #{r['waiverRank']}): " + "; ".join(lines)
                       + (f" | IR: move {', '.join(irl)} to open IR slot" if irl else "")
                       + (f" | Bye: {byet}" if byet else "")
                       + (f" | {r['notes'][0]}" if r["notes"] else "")))
        md.append("")
    path = REPORTS / f"waivers_{datetime.now():%Y%m%d}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    (REPORTS / "waivers_latest.json").write_text(json.dumps(strip(out), indent=1, default=str), encoding="utf-8")
    for line in md: log(line)
    if push:
        for lg, msg in pushes: log(f"push {lg}: {notify('FF waivers: ' + lg, msg[:900])}")
    log(f"DONE waivers teams={len(out)} report={path}")

if __name__ == "__main__":
    main()
