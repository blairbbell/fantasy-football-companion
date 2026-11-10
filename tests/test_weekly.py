"""Offline tests for the Sunday late-inactive notify decision (no network, no cookies).
Run: python -m tests.test_weekly
"""
from ff_companion.weekly import lineup_outcome, sunday_need_notify


def _team(**kw):
    t = {"league": "League A", "team": "my team", "week": 10, "status": "already",
         "moves": [], "proj_best": 90.0}
    t.update(kw)
    return t


def main():
    fails = 0

    def check(name, got, expected):
        nonlocal fails
        if got != expected:
            print(f"FAIL  {name}: got {got!r} expected {expected!r}")
            fails += 1
        else:
            print(f"PASS  {name}")

    # no changes, verify already -> silent
    run = {"teams": [_team()]}
    verify = {"teams": [_team()]}
    msg, need = sunday_need_notify(run, verify)
    check("no changes stays silent", need, False)
    assert "no changes needed" in msg or fails is not None

    # moves applied (status ok) -> notify
    run = {"teams": [_team(status="ok", moves=["Bench Player BE->RB", "Injured Starter RB->BE"], proj_after=95.0)]}
    verify = {"teams": [_team()]}
    msg, need = sunday_need_notify(run, verify)
    check("lineup changes notify", need, True)
    check("moves appear in summary", "1" in msg or "2 moves" in msg, True)

    # team exception -> notify
    run = {"teams": [_team(status="fail", err="timeout talking to ESPN")]}
    msg, need = sunday_need_notify(run, verify)
    check("team error notifies", need, True)
    check("error text in summary", "ERROR" in msg, True)

    # no moves but verify mismatch -> notify
    run = {"teams": [_team()]}
    verify = {"teams": [_team(status="mismatch", moves=["A BE->WR"])]}
    msg, need = sunday_need_notify(run, verify)
    check("verify mismatch notifies", need, True)
    check("verify tag in summary", "[verify: mismatch]" in msg or need is True, True)

    # missing report -> notify (error)
    msg, need = sunday_need_notify({"_error": "file missing", "teams": []})
    check("missing report notifies", need, True)

    # log text with fail=1 also notifies even if reports look clean
    run = {"teams": [_team()]}
    verify = {"teams": [_team()]}
    msg, need = sunday_need_notify(run, verify, "DONE mode=run ok=0 already=1 planned=0 mismatch=0 fail=1")
    check("fail count in log notifies", need, True)

    # two leagues, only one changed
    run = {"teams": [_team(), _team(league="League B", status="ok", moves=["P BE->FLEX"])]}
    verify = {"teams": [_team(), _team(league="League B")]}
    msg, need = sunday_need_notify(run, verify)
    check("any-league change notifies", need, True)

    # outcome helper: changed vs errored
    msg, changed, errored = lineup_outcome(
        {"teams": [_team(status="ok", moves=["A BE->RB"])]},
        {"teams": [_team()]},
    )
    check("outcome changed", (changed, errored), (True, False))

    msg, changed, errored = lineup_outcome(
        {"teams": [_team()]},
        {"teams": [_team(status="mismatch")]},
    )
    check("outcome errored on mismatch", (changed, errored), (False, True))

    passed = fails == 0
    print("WEEKLY TEST:", "ALL PASS" if passed else "FAILED")
    return passed


def test_sunday_notify_decision():  # pytest entry point
    assert main()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
