"""Guard test: uses a fake session that records any POST attempt; nothing reaches ESPN.
Run: python -m tests.test_guard   (no network, no cookies, no config needed)"""
from ff_companion import espn_common as fc

class FakeSession:
    def __init__(self): self.calls = 0
    def post(self, *a, **k): self.calls += 1; raise AssertionError("POST WOULD HAVE BEEN SENT")
slots = {"0": 1, "2": 2, "4": 2, "6": 1, "16": 1, "20": 4, "21": 2, "23": 1}
R = [{"id": 1, "slot": 0, "elig": [0, 7, 20, 21]}, {"id": 2, "slot": 20, "elig": [2, 3, 23, 7, 20, 21]},
     {"id": 3, "slot": 2, "elig": [2, 3, 23, 7, 20, 21]}, {"id": 4, "slot": 21, "elig": [4, 23, 20, 21]}, {"id": 5, "slot": 20, "elig": [0, 7, 20, 21]}]
T = 42; base = {"isLeagueManager": False, "teamId": T, "scoringPeriodId": 10, "executionType": "EXECUTE"}
L = lambda pid, f, t: {"playerId": pid, "type": "LINEUP", "fromLineupSlotId": f, "toLineupSlotId": t}
cases = {
 "FREEAGENT add/drop": ({**base, "type": "FREEAGENT", "items": [{"playerId": 99, "type": "ADD", "toTeamId": T}, {"playerId": 2, "type": "DROP", "fromTeamId": T}]}, set()),
 "WAIVER claim": ({**base, "type": "WAIVER", "items": [{"playerId": 99, "type": "ADD", "toTeamId": T, "bidAmount": 5}]}, set()),
 "TRADE": ({**base, "type": "TRADE_PROPOSAL", "items": [L(2, 20, 2)]}, set()),
 "FUTURE_ROSTER": ({**base, "type": "FUTURE_ROSTER", "items": [L(2, 20, 2)]}, set()),
 "ROSTER with DROP item": ({**base, "type": "ROSTER", "items": [{"playerId": 2, "type": "DROP", "fromLineupSlotId": 20, "toLineupSlotId": 20}]}, set()),
 "into IR": ({**base, "type": "ROSTER", "items": [L(2, 20, 21)]}, set()),
 "out of IR": ({**base, "type": "ROSTER", "items": [L(4, 21, 20)]}, set()),
 "non-roster player": ({**base, "type": "ROSTER", "items": [L(99, 20, 2)]}, set()),
 "other team": ({**base, "teamId": 43, "type": "ROSTER", "items": [L(2, 20, 2)]}, set()),
 "league manager": ({**base, "isLeagueManager": True, "type": "ROSTER", "items": [L(2, 20, 2)]}, set()),
 "ineligible slot (RB to QB)": ({**base, "type": "ROSTER", "items": [L(2, 20, 0)]}, set()),
 "unused slot (K)": ({**base, "type": "ROSTER", "items": [L(2, 20, 17)]}, set()),
 "locked player": ({**base, "type": "ROSTER", "items": [L(3, 2, 20), L(2, 20, 2)]}, {3}),
 "wrong from-slot": ({**base, "type": "ROSTER", "items": [L(2, 4, 2)]}, set()),
 "extra payload key": ({**base, "type": "ROSTER", "memberId": "x", "items": [L(2, 20, 2)]}, set()),
}
def main():
    fs = FakeSession(); fails = 0
    for name, (pl, locked) in cases.items():
        try:
            fc.post_lineup(fs, 1, pl, T, R, slots, locked); print(f"FAIL  {name}: not refused"); fails += 1
        except fc.GuardRefused as e: print(f"PASS  {name}: {e}")
    ok = {**base, "type": "ROSTER", "items": [L(3, 2, 20), L(2, 20, 2)]}
    print("PASS  valid RB swap accepted (dry):", fc.post_lineup(fs, 1, ok, T, R, slots, set(), dry=True)["body"])
    print(f"POST attempts: {fs.calls}")
    passed = fails == 0 and fs.calls == 0
    print("GUARD TEST:", "ALL PASS" if passed else "FAILED")
    return passed


def test_guard():  # pytest entry point
    assert main()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
