"""Optional, pluggable notifications.

Nothing is sent unless you configure one of:
  * notify_command / FF_NOTIFY_CMD : a command run as  <command> "<title>" "<message>"
    (e.g. a script that calls your phone-push service, Pushover, a chat webhook, ...)
  * notify_url / FF_NOTIFY_URL     : a URL that accepts a plain-text POST body (e.g. an ntfy topic URL).
Without either, messages are only printed (and logged by the caller).
Quiet hours, batching, etc. are up to your hook.
"""
from __future__ import annotations
import shlex
import subprocess
import sys

from .config import CFG


def notify(title: str, msg: str) -> str:
    cmd, url = (CFG.get("notify_command") or "").strip(), (CFG.get("notify_url") or "").strip()
    if not cmd and not url:
        print(f"[notify disabled] {title}: {msg}")
        return "disabled"
    result = []
    if cmd:
        try:
            argv = shlex.split(cmd, posix=(sys.platform != "win32")) + [title, msg]
            p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
            result.append(f"command rc={p.returncode}")
        except Exception as e:  # never let a notification failure break a run
            print(f"notify command failed: {e}", file=sys.stderr)
            result.append("command failed")
    if url:
        try:
            import requests
            r = requests.post(url, data=msg.encode("utf-8"), headers={"Title": title}, timeout=30)
            result.append(f"url http={r.status_code}")
        except Exception as e:
            print(f"notify url failed: {e}", file=sys.stderr)
            result.append("url failed")
    return ", ".join(result)


if __name__ == "__main__":  # quick manual test: python -m ff_companion.notify "Title" "Message"
    a = sys.argv[1:] + ["Fantasy Football Companion", "test notification"][len(sys.argv[1:]):]
    print(notify(a[0], a[1]))
