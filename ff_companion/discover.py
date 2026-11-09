"""discover - find every ESPN fantasy football league/team on your ESPN account for the configured season.
Writes data/leagues.json (league ids, team ids, names, settings summary), which the other tools use when
config.json lists no leagues. Read-only. Cookie values are never printed.
Usage: python -m ff_companion.discover"""
import json
from .espn_common import SEASON, GAME, LEAGUES_PATH, cookies, session, get, league, SLOTNAME, ensure_dirs

def main():
    s = session(); swid = cookies()["SWID"]
    fan = get(s, f"https://fan.api.espn.com/apis/v2/fans/{swid}",
              params={"displayEvents": "false", "displayNow": "false", "displayRecs": "false", "context": "fantasy",
                      "source": "espncom-fantasy-lm", "lang": "en", "section": "espn", "region": "us"})
    out, other = [], []
    for pref in fan.get("preferences", []):
        e = (pref.get("metaData") or {}).get("entry") or {}
        if not e: continue
        g = (e.get("groups") or [{}])[0]
        if e.get("abbrev") != GAME.upper() or e.get("seasonId") != SEASON:
            other.append(f"{e.get('abbrev')} {e.get('seasonId')} {g.get('groupName')}"); continue
        lid, tid = int(g["groupId"]), int(e["entryId"])
        j = league(s, lid, ["mSettings", "mStatus", "mTeam"])
        st = j["settings"]; acq = st["acquisitionSettings"]; rs = st["rosterSettings"]
        t = next(x for x in j["teams"] if x["id"] == tid)
        out.append({"leagueId": lid, "teamId": tid, "league": st["name"],
                    "team": t.get("name") or f"{t.get('location','')} {t.get('nickname','')}".strip(),
                    "size": st.get("size"), "slots": {k: v for k, v in rs["lineupSlotCounts"].items() if v},
                    "acquisitionType": acq.get("acquisitionType"), "faab": acq.get("isUsingAcquisitionBudget"),
                    "budget": acq.get("acquisitionBudget"), "waiverProcessDays": acq.get("waiverProcessDays"),
                    "waiverProcessHour": acq.get("waiverProcessHour"),
                    "scoring": st["scoringSettings"].get("scoringType")})
    ensure_dirs()
    LEAGUES_PATH.write_text(json.dumps({"season": SEASON, "leagues": out, "other_espn_entries": other}, indent=1), encoding="utf-8")
    try:
        LEAGUES_PATH.chmod(0o600)
    except OSError:
        pass
    print(f"{len(out)} ESPN football team(s) for {SEASON}:")
    for L in out:
        sl = ", ".join(f"{SLOTNAME.get(int(k), k)}x{v}" for k, v in L["slots"].items() if int(k) not in (20,))
        print(f"  {L['league']} -> {L['team']} ({L['size']} teams; {sl}; {L['acquisitionType']}, FAAB={L['faab']})")
    if other: print("Other ESPN entries (not football/this season): " + "; ".join(other))
    print(f"Saved to {LEAGUES_PATH} (git-ignored).")

if __name__ == "__main__":
    main()
