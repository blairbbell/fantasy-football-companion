"""Offline tests for the bye-week heads-up logic (no network, no cookies).
Run: python -m tests.test_bye"""
from ff_companion.waivers import bye_headsup, bye_text
from ff_companion.espn_common import BENCH
BENCH_ = BENCH

def P(i, slot, pro, nxt=10.0, pos="RB"):
    return {"id": i, "name": f"P{i}", "pos": pos, "slot": slot, "pro": pro, "next": nxt}

SCHED = {1: {"bye": 9, "games": {10: [1]}}, 2: {"bye": 10, "games": {9: [1]}}}

def main():
    fails = 0
    def check(name, got, expected):
        nonlocal fails
        ok = got == expected
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f": got {got!r} expected {expected!r}"))
        fails += 0 if ok else 1
    act = {2: 1, 4: 1}
    roster = [P(1, 2, 1), P(2, 4, 2, 0.0, "WR"), P(3, BENCH_, 2, 0.0)]
    b = bye_headsup(roster, act, {1: 2, 2: BENCH_, 3: BENCH_}, 10, SCHED)
    check("starter on bye listed", [x["name"] for x in b["byes"]], ["P2"])
    check("bench player on bye ignored", len(b["byes"]), 1)
    check("open spot counted", len(b["open"]), 1)
    b0 = bye_headsup([P(1, 2, 1), P(4, 4, 1, 8.0)], act, {1: 2, 4: 4}, 10, SCHED)
    check("nothing to flag", (b0["byes"], b0["open"]), ([], []))
    check("empty text when clean", bye_text(b0, 10), "")
    check("text names bye and open", bye_text(b, 10).startswith("wk10 byes among starters: P2 (WR); open starting spots: 1 "), True)
    print("ALL PASS" if not fails else f"{fails} FAILED")
    raise SystemExit(1 if fails else 0)

if __name__ == "__main__":
    main()
