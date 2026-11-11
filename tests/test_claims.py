"""Offline test for the claim-result selection/description (no network, no cookies).
Run: python -m tests.test_claims"""
from ff_companion.claims import select_claims, describe
NOW = 2_000_000_000_000
def tx(st, items, t=NOW - 3600_000, team=1, typ="WAIVER"):
    return {"teamId": team, "type": typ, "status": st, "proposedDate": t, "processDate": t if st != "PENDING" else None,
            "items": [{"type": a, "playerId": p} for a, p in items]}
def main():
    a = tx("EXECUTED", [("ADD", 1), ("DROP", 2)]); b = tx("PENDING", [("ADD", 1), ("DROP", 2)])
    c = tx("FAILED_ROSTERLIMIT", [("ADD", 3)]); d = tx("EXECUTED", [("ADD", 4)], team=2)
    e = tx("EXECUTED", [("ADD", 5)], t=NOW - 40 * 3600_000); f = tx("EXECUTED", [("LINEUP", 9)], typ="ROSTER")
    got = select_claims([a, b, c, d, e, f], 1, NOW)
    assert got == [a, c], got
    assert describe(a, {1: "A", 2: "B"}) == "OK +A/-B"
    assert describe(c, {3: "C"}) == "FAILED +C (roster full)"
    assert describe(tx("PENDING", [("ADD", 3)]), {}) == "PENDING +3"
    print("CLAIMS TEST: ALL PASS")
    return True


def test_claims():  # pytest entry point
    assert main()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
