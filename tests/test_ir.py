"""Offline tests for the bench-IR suggestion logic (no network, no cookies).
Run: python -m tests.test_ir
"""
from ff_companion.waivers import ir_suggestions
from ff_companion.espn_common import BENCH, IR


def P(i, slot, inj, elig=(0, 20, 21), ros=10.0):
    return {"id": i, "name": f"P{i}", "pos": "RB", "slot": slot, "inj": inj, "elig": list(elig), "ros": ros}


def main():
    fails = 0

    def check(name, got, expected):
        nonlocal fails
        ok = got == expected
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f": got {got!r} expected {expected!r}"))
        fails += 0 if ok else 1

    ids = lambda xs: [p["id"] for p in xs]
    check("no open IR slot -> nothing", ids(ir_suggestions([P(1, BENCH, "OUT")], 0)), [])
    check("bench OUT is suggested", ids(ir_suggestions([P(1, BENCH, "OUT")], 1)), [1])
    check("starter OUT is not a bench IR move", ids(ir_suggestions([P(1, 2, "OUT")], 1)), [])
    check("already on IR is ignored", ids(ir_suggestions([P(1, IR, "OUT")], 1)), [])
    check("not IR-eligible per ESPN", ids(ir_suggestions([P(1, BENCH, "OUT", elig=(0, 20))], 1)), [])
    check("healthy / questionable ignored", ids(ir_suggestions([P(1, BENCH, "ACTIVE"), P(2, BENCH, "QUESTIONABLE")], 2)), [])
    check("capped by open slots, IR tag first", ids(ir_suggestions([P(1, BENCH, "OUT"), P(2, BENCH, "INJURY_RESERVE"), P(3, BENCH, "OUT")], 2)), [2, 1])
    check("doubtful bench suggested", ids(ir_suggestions([P(1, BENCH, "DOUBTFUL")], 1, {1: BENCH})), [1])
    check("doubtful in best lineup not suggested", ids(ir_suggestions([P(1, BENCH, "DOUBTFUL")], 1, {1: 2})), [])
    print("ALL PASS" if not fails else f"{fails} FAILED")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
