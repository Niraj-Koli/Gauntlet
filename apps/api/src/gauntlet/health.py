"""Is the trading floor's loop alive? For container probes, so it imports only settings:

    python -m gauntlet.health

Exits 1 unless the scheduler touched HEARTBEAT_FILE within HEARTBEAT_MAX_AGE_SECONDS.
"""

import sys
import time

from .settings import get_settings


def main() -> None:
    settings = get_settings()
    path = settings.heartbeat_file
    if path is None:
        sys.exit("HEARTBEAT_FILE isn't set, so there is nothing to check")
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        sys.exit(f"No heartbeat yet at {path}")
    if age > settings.heartbeat_max_age_seconds:
        sys.exit(f"Last heartbeat {age:.0f}s ago (limit {settings.heartbeat_max_age_seconds:.0f}s)")
    print(f"ok: last heartbeat {age:.0f}s ago")


if __name__ == "__main__":
    main()
