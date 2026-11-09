"""Shared ESPN fantasy football API helpers (requests + espn_s2/SWID cookies).

Auth uses the two cookies ESPN sets for a logged-in browser session: `espn_s2` and `SWID`.
They are read from environment variables (ESPN_S2 / ESPN_SWID) or from a git-ignored JSON file.
Values are never printed or logged.

Every ESPN write goes through post_lineup(), whose guard refuses anything that is not a pure
lineup-slot move (no adds/drops/waiver claims/trades/IR moves, no locked players, own team only).
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime

import requests

from .config import CFG
from .notify import notify  # noqa: F401  (re-exported for the CLI modules)

DATA = CFG["data_dir"]
LOGDIR = DATA / "logs"
REPORTS = DATA / "reports"
LEAGUES_PATH = DATA / "leagues.json"     # written by discover.py when config.json lists no leagues
SEASON = int(CFG["season"])
GAME = "ffl"
READS = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/{GAME}/seasons/{SEASON}"
WRITES = "https://lm-api-writes.fantasy.espn.com/apis/v3/games/{g}/seasons/{s}/segments/0/leagues/{l}/transactions/"
EXPIRED_MSG = ("ESPN returned {code}: cookies expired or invalid. Re-copy espn_s2 and SWID from a logged-in "
               "browser (see README.md, 'Authentication').")

SLOTNAME = {0: "QB", 1: "TQB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE", 7: "OP", 8: "DT", 9: "DE",
            10: "LB", 11: "DL", 12: "CB", 13: "S", 14: "DB", 15: "DP", 16: "D/ST", 17: "K", 18: "P", 19: "HC",
            20: "BE", 21: "IR", 23: "FLEX", 24: "ER", 25: "Rookie"}
POSNAME = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST", 7: "P", 9: "DT", 10: "DE", 11: "LB", 12: "CB", 13: "S", 14: "HC"}
BENCH, IR = 20, 21
NO_START = {"OUT", "INJURY_RESERVE", "SUSPENSION"}
BIG = 10**9

class CookiesExpired(SystemExit):
    pass

def log_to(path, msg):
    print(msg, flush=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def cookies():
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if s2 and swid:
        return {"espn_s2": s2, "SWID": swid, "espn_s2_expires": None}
    p = CFG["cookies_file"]
    if not p.exists():
        sys.exit(f"No ESPN cookies: set ESPN_S2/ESPN_SWID or create {p.name} (see README.md)")
    return json.loads(p.read_text(encoding="utf-8"))

def session():
    c = cookies()
    s = requests.Session()
    s.cookies.set("espn_s2", c["espn_s2"], domain=".espn.com")
    s.cookies.set("SWID", c["SWID"], domain=".espn.com")
    s.headers.update({"User-Agent": "Mozilla/5.0 fantasy-football-companion", "Accept": "application/json"})
    exp = c.get("espn_s2_expires")
    if exp and exp > 0 and exp - time.time() < 7 * 86400:
        print(f"WARNING: espn_s2 expires {time.strftime('%Y-%m-%d', time.localtime(exp))}; refresh soon.", file=sys.stderr)
    return s

def get(s, url, params=None, filt=None):
    h = {"x-fantasy-filter": json.dumps(filt)} if filt else {}
    for attempt in range(3):
        try:
            r = s.get(url, params=params, headers=h, timeout=60)
        except requests.RequestException:
            if attempt == 2: raise
            time.sleep(5 * (attempt + 1)); continue
        if r.status_code in (401, 403):
            print(EXPIRED_MSG.format(code=r.status_code), file=sys.stderr)
            raise CookiesExpired(2)
        if r.status_code >= 500 and attempt < 2:
            time.sleep(5 * (attempt + 1)); continue
        r.raise_for_status()
        return r.json()

def league_url(lid): return f"{READS}/segments/0/leagues/{lid}"

def league(s, lid, views, **params):
    return get(s, league_url(lid), params=[("view", v) for v in views] + list(params.items()))

def load_leagues():
    """Teams to manage: config.json "leagues" (or FF_LEAGUE_ID/FF_TEAM_ID) if set, else data/leagues.json from discover.
    Returns {"leagues": [{"leagueId", "teamId", "league", "team"}, ...]}."""
    if CFG.get("leagues"):
        out = []
        for i, L in enumerate(CFG["leagues"], 1):
            lid, tid = int(L.get("league_id") or 0), int(L.get("team_id") or 0)
            if not lid or not tid:
                sys.exit("Each entry in config.json \"leagues\" needs league_id and team_id. See README.md.")
            label = L.get("name") or f"League {i}"
            out.append({"leagueId": lid, "teamId": tid, "league": label, "team": L.get("team_name") or "my team"})
        return {"leagues": out}
    if not LEAGUES_PATH.exists():
        sys.exit("No leagues configured: add them to config.json, set FF_LEAGUE_ID/FF_TEAM_ID, "
                 "or run: python -m ff_companion.discover")
    return json.loads(LEAGUES_PATH.read_text(encoding="utf-8"))

def ensure_dirs():
    LOGDIR.mkdir(parents=True, exist_ok=True); REPORTS.mkdir(parents=True, exist_ok=True)

def pro_schedule(s):
    j = get(s, READS, params={"view": "proTeamSchedules_wl"})
    out = {}
    for t in j["settings"]["proTeams"]:
        out[t["id"]] = {"abbrev": t["abbrev"], "bye": t.get("byeWeek"),
                        "games": {int(w): [g["date"] for g in gs] for w, gs in (t.get("proGamesByScoringPeriod") or {}).items()}}
    return out

def week_started(sched, week, now_ms=None):
    now_ms = now_ms or time.time() * 1000
    return any(d <= now_ms for t in sched.values() for d in t["games"].get(week, []))

def proj_week(p, week):
    """ESPN weekly projection (statSource 1, split 1) in league scoring, or None."""
    for st in p.get("stats") or []:
        if st.get("statSourceId") == 1 and st.get("statSplitTypeId") == 1 and st.get("scoringPeriodId") == week and st.get("seasonId") == SEASON:
            return st.get("appliedTotal") or 0.0
    return None

def actual_season(p):
    for st in p.get("stats") or []:
        if st.get("statSourceId") == 0 and st.get("statSplitTypeId") == 0 and st.get("seasonId") == SEASON:
            return st.get("appliedTotal") or 0.0, st.get("appliedAverage") or 0.0
    return 0.0, 0.0

def ros_ppg(p):
    """Rest-of-season projected points per game (ESPN id 10{season}), blended with actual per-game."""
    proj = None
    for st in p.get("stats") or []:
        if st.get("statSourceId") == 1 and st.get("statSplitTypeId") == 0 and st.get("seasonId") == SEASON:
            proj = st.get("appliedAverage")
    _, act = actual_season(p)
    if proj is None: return act or 0.0
    return 0.75 * proj + 0.25 * act if act else proj

def player_row(entry_or_pe, slot=None):
    pe = entry_or_pe.get("playerPoolEntry", entry_or_pe)
    p = pe["player"]
    return {"id": p["id"], "name": p["fullName"], "pos": POSNAME.get(p.get("defaultPositionId"), str(p.get("defaultPositionId"))),
            "posId": p.get("defaultPositionId"), "elig": p.get("eligibleSlots") or [], "pro": p.get("proTeamId"),
            "inj": p.get("injuryStatus") or "ACTIVE", "injured": bool(p.get("injured")), "slot": slot,
            "lineupLocked": bool(pe.get("lineupLocked")), "status": entry_or_pe.get("status") or pe.get("status"),
            "waiverDate": pe.get("waiverProcessDate"), "own": (p.get("ownership") or {}).get("percentOwned"), "raw": p}

def team_roster(s, lid, tid, week):
    j = league(s, lid, ["mRoster", "mTeam", "mStatus", "mSettings"], scoringPeriodId=week, forTeamId=tid, _=int(time.time() * 1000))
    t = next(x for x in j["teams"] if x["id"] == tid)
    return j, [player_row(e, e["lineupSlotId"]) for e in t["roster"]["entries"]]

def eff_proj(p, week, sched):
    """Projection used for lineup decisions: 0 on bye / no game / OUT-IR-SUSP; DOUBTFUL scaled by doubtful_factor."""
    if not sched.get(p["pro"], {}).get("games", {}).get(week): return 0.0
    if p["inj"] in NO_START: return 0.0
    v = proj_week(p["raw"], week) or 0.0
    if p["inj"] == "DOUBTFUL": v *= float(CFG.get("doubtful_factor", 0.5))
    return max(v, 0.0)

def is_locked(p, week, sched, now_ms=None):
    now_ms = now_ms or time.time() * 1000
    if p.get("lineupLocked"): return True
    return any(d <= now_ms + 60000 for d in sched.get(p["pro"], {}).get("games", {}).get(week, []))

def hungarian(a):
    n, m = len(a), len(a[0])
    u=[0]*(n+1); v=[0]*(m+1); p=[0]*(m+1); way=[0]*(m+1)
    for i in range(1, n+1):
        p[0]=i; j0=0; minv=[float('inf')]*(m+1); used=[False]*(m+1)
        while True:
            used[j0]=True; i0=p[j0]; delta=float('inf'); j1=0
            for j in range(1, m+1):
                if not used[j]:
                    cur=a[i0-1][j-1]-u[i0]-v[j]
                    if cur<minv[j]: minv[j]=cur; way[j]=j0
                    if minv[j]<delta: delta=minv[j]; j1=j
            for j in range(m+1):
                if used[j]: u[p[j]]+=delta; v[j]-=delta
                else: minv[j]-=delta
            j0=j1
            if p[j0]==0: break
        while True:
            j1=way[j0]; p[j0]=p[j1]; j0=j1
            if j0==0: break
    ans=[None]*n
    for j in range(1, m+1):
        if p[j]: ans[p[j]-1]=j-1
    return ans

def active_slots(slot_counts):
    return {int(k): v for k, v in slot_counts.items() if v and int(k) not in (BENCH, IR)}

def optimize(players, slot_counts, weights, locked=frozenset()):
    """Best lineup: maximise sum of weights in active slots. players exclude IR-slot players.
    locked player ids keep their current slot. Returns ({pid: slot}, projected_total)."""
    act = active_slots(slot_counts)
    inst = [sl for sl, c in sorted(act.items()) for _ in range(c)] + [BENCH] * max(1, len(players))
    rows = []
    for p in players:
        w = weights.get(p["id"], 0.0); row = []
        for sl in inst:
            stay = 1 if p["slot"] == sl else 0
            if p["id"] in locked and p["slot"] != sl: row.append(BIG); continue
            if sl == BENCH: row.append(-stay); continue
            if sl not in p["elig"]: row.append(BIG); continue
            row.append(-(w * 1000) - stay)
        rows.append(row)
    if not rows: return {}, 0.0
    asg = hungarian(rows); desired = {}; total = 0.0
    for i, p in enumerate(players):
        if rows[i][asg[i]] >= BIG: raise RuntimeError(f"infeasible lineup for {p['name']}")
        desired[p["id"]] = inst[asg[i]]
        if inst[asg[i]] != BENCH: total += weights.get(p["id"], 0.0)
    return desired, round(total, 2)

# ---- LINEUP-ONLY GUARD ------------------------------------------------------------------------
ALLOWED_TX_TYPES = {"ROSTER"}            # current-week lineup change only
ALLOWED_PAYLOAD_KEYS = {"isLeagueManager", "teamId", "type", "scoringPeriodId", "executionType", "items"}
ALLOWED_ITEM_KEYS = {"playerId", "type", "fromLineupSlotId", "toLineupSlotId"}

class GuardRefused(Exception):
    pass

def guard_lineup_payload(payload, team_id, roster, slot_counts, locked):
    """Raise GuardRefused unless payload is a lineup-only move for team_id. roster = list of freshly read
    player rows for that team/week; slot_counts = league lineupSlotCounts; locked = set of locked player ids."""
    def no(why): raise GuardRefused(f"GUARD REFUSED: {why}")
    if not isinstance(payload, dict): no("payload not a dict")
    extra = set(payload) - ALLOWED_PAYLOAD_KEYS
    if extra: no(f"unexpected payload keys {sorted(extra)}")
    if payload.get("type") not in ALLOWED_TX_TYPES: no(f"transaction type {payload.get('type')!r} is not a lineup move")
    if payload.get("teamId") != team_id: no(f"teamId {payload.get('teamId')!r} != own team")
    if payload.get("isLeagueManager") not in (False, None): no("isLeagueManager must be False")
    if payload.get("executionType") != "EXECUTE": no("executionType must be EXECUTE")
    if not isinstance(payload.get("scoringPeriodId"), int): no("scoringPeriodId missing")
    if not roster: no("no current roster supplied")
    allowed = set(active_slots(slot_counts)) | {BENCH}
    cur = {p["id"]: p for p in roster}
    items = payload.get("items")
    if not isinstance(items, list) or not items: no("no items")
    for it in items:
        if not isinstance(it, dict): no("item not a dict")
        extra = set(it) - ALLOWED_ITEM_KEYS
        if extra: no(f"unexpected item keys {sorted(extra)}")
        if it.get("type") != "LINEUP": no(f"item type {it.get('type')!r} is not LINEUP")
        pid, fr, to = it.get("playerId"), it.get("fromLineupSlotId"), it.get("toLineupSlotId")
        if pid not in cur: no(f"player {pid} is not on the current roster")
        if fr not in allowed or to not in allowed: no(f"player {pid} slot {fr}->{to} touches IR/invalid slot")
        if cur[pid]["slot"] != fr: no(f"player {pid} fromLineupSlotId {fr} != current slot {cur[pid]['slot']}")
        if to != BENCH and to not in cur[pid]["elig"]: no(f"player {pid} not eligible for slot {to}")
        if pid in locked: no(f"player {pid} is locked (game started)")
        if fr == to: no(f"player {pid} no-op move")
    return True

def post_lineup(s, lid, payload, team_id, roster, slot_counts, locked, dry=False):
    guard_lineup_payload(payload, team_id, roster, slot_counts, locked)   # raises -> nothing sent
    if dry: return {"status": "dry", "body": "guard OK, not sent"}
    r = s.post(WRITES.format(g=GAME, s=SEASON, l=lid), json=payload, timeout=60, headers={"content-type": "application/json"})
    if r.status_code in (401, 403):
        print(EXPIRED_MSG.format(code=r.status_code), file=sys.stderr)
    return {"status": r.status_code, "body": r.text[:600]}

def now_str(): return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
