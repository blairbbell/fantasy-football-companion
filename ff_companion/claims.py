"""claims.py - report which of your waiver claims succeeded or failed. READ-ONLY (GET only; never adds/drops/claims).
Looks at each team's recent WAIVER transactions (ESPN mTransactions2), keeps ones processed/proposed in the last
WINDOW_H hours, de-duplicates, skips ones already reported (reports/claims_seen.json) and pushes one summary.
Silent when there is nothing new. Usage: python -m ff_companion.claims [--dry-run]   (dry-run: print only, no push, no state write)"""
import json, sys, time
from datetime import datetime
from .config import CFG
from .espn_common import (LOGDIR, REPORTS, session, get, league, league_url, load_leagues, notify, log_to,
                          ensure_dirs)

SEEN = REPORTS / "claims_seen.json"
LOG = LOGDIR / f"claims_{datetime.now():%Y%m%d}.log"
WINDOW_H = float((CFG.get("claims") or {}).get("window_hours", 30))   # how far back to look
REASONS = {"FAILED_INVALIDPLAYERSOURCE": "player no longer available", "FAILED_ROSTERLIMIT": "roster full",
           "FAILED_PLAYERALREADYDROPPED": "drop player already gone", "FAILED_INVALIDACTION": "invalid move",
           "FAILED_PLAYERNOTDROPPABLE": "drop player not droppable", "FAILED_BUDGET": "not enough budget",
           "CANCELED": "canceled"}

def log(m): log_to(LOG, m)

def claim_key(t):
    return "%s|%s|%s" % (t.get("teamId"), t.get("proposedDate"), ",".join("%s:%s" % (i["type"], i["playerId"]) for i in t.get("items", [])))

def select_claims(txs, team_id, now_ms, window_h=None):
    window_h = WINDOW_H if window_h is None else window_h
    """My WAIVER claims touched in the window. A PENDING entry duplicating a resolved claim (same items) is dropped."""
    cut = now_ms - window_h * 3600 * 1000
    mine = [t for t in txs if t.get("teamId") == team_id and t.get("type") == "WAIVER"
            and max(t.get("processDate") or 0, t.get("proposedDate") or 0) >= cut]
    sig = lambda t: tuple(sorted((i["type"], i["playerId"]) for i in t.get("items", [])))
    resolved = {sig(t) for t in mine if t.get("status") != "PENDING"}
    return [t for t in mine if t.get("status") != "PENDING" or sig(t) not in resolved]

def describe(t, names):
    adds = [names.get(i["playerId"], str(i["playerId"])) for i in t["items"] if i["type"] == "ADD"]
    drops = [names.get(i["playerId"], str(i["playerId"])) for i in t["items"] if i["type"] == "DROP"]
    what = "+" + ", ".join(adds) + ("/-" + ", ".join(drops) if drops else "")
    st = t.get("status", "?")
    if st == "EXECUTED": return "OK " + what
    if st == "PENDING": return "PENDING " + what
    return "FAILED %s (%s)" % (what, REASONS.get(st, st.replace("FAILED_", "").lower()))

def main():
    dry = "--dry-run" in sys.argv
    ensure_dirs()
    s = session(); now_ms = int(time.time() * 1000)
    try: seen = set(json.loads(SEEN.read_text()))
    except Exception: seen = set()
    parts, new_keys, errs = [], [], 0
    for L in load_leagues()["leagues"]:
        try:
            j = league(s, L["leagueId"], ["mTransactions2"])
            claims = [t for t in select_claims(j.get("transactions", []), L["teamId"], now_ms) if claim_key(t) not in seen]
            if not claims:
                log(f"{L['league']}: no new claims"); continue
            ids = sorted({i["playerId"] for t in claims for i in t["items"]})
            pj = get(s, league_url(L["leagueId"]), params=[("view", "kona_playercard")], filt={"players": {"filterIds": {"value": ids}}})
            names = {pe["id"]: pe["player"]["fullName"] for pe in pj.get("players", [])}
            lines = [describe(t, names) for t in claims]
            parts.append("%s: %s" % (L.get("team") or L["league"], "; ".join(lines)))
            new_keys += [claim_key(t) for t in claims if t.get("status") != "PENDING"]
            time.sleep(0.5)
        except SystemExit: raise
        except Exception as e:
            errs += 1; log(f"ERROR: {L.get('league')}: {str(e)[:120]}")
    msg = " || ".join(parts)
    if not msg:
        log("DONE no new claims, no push" + (" (dry-run)" if dry else "")); return 1 if errs else 0
    if dry:
        log(f"DRY-RUN would push: {msg}"); return 1 if errs else 0
    log(f"notify: {notify('FF waiver claims', msg[:900])}")
    SEEN.write_text(json.dumps(sorted(seen | set(new_keys))[-200:]))
    return 1 if errs else 0

if __name__ == "__main__":
    sys.exit(main())
