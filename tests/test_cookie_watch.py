"""Offline test for cookie expiry / auth-failure notification decisions (no network, no cookies).
Run: python -m tests.test_cookie_watch"""
from ff_companion.cookie_watch import decide_expiry, decide_authfail

D = 86400
NOW = 2_000_000_000.0


def main():
    assert decide_expiry(None, {}, NOW) is None
    assert decide_expiry(0, {}, NOW) is None
    assert decide_expiry(NOW + 40 * D, {}, NOW) is None
    assert "20 days" in decide_expiry(NOW + 20.5 * D, {}, NOW)
    assert decide_expiry(NOW + 20 * D, {"last_expiry_warn": NOW - 2 * D}, NOW) is None
    assert decide_expiry(NOW + 13 * D, {"last_expiry_warn": NOW - 8 * D}, NOW)
    assert "expired" in decide_expiry(NOW - D, {}, NOW)
    assert decide_authfail({}) and not decide_authfail({"auth_failing": True})
    print("COOKIE_WATCH TEST: ALL PASS")
    return True


def test_cookie_watch():  # pytest entry point
    assert main()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
