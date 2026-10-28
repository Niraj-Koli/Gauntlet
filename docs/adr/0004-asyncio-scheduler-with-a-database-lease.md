# 0004: A plain asyncio scheduler with a leader lease and command queue in the database

**Status:** accepted

## Context

The original scheduler was a sleep loop. It kept state in memory (whether the next run trades or rebalances), swallowed errors, had no run timeouts, and drifted, because it slept after each cycle finished. The rebuild added more needs:
- run now, pause and resume from the dashboard;
- at most one active scheduler, even during a rolling deploy;
- clean recovery from crashes.

APScheduler, and a task queue such as Celery or Arq with Redis, were the obvious options.

## Decision

`trading_floor.py` is a small asyncio loop:

- **Fixed slots:** it runs cycles on a schedule that long cycles don't push later.
- **Leader lease:** schedulers take a lease on a `floor_state` row in the database, and only the holder acts.
- **Commands:** the dashboard queues them in a `commands` table, and the leader applies them within seconds.
- **State lives in the database:** whether the next run trades or rebalances is read from the run history.
- **Every run is accounted for:** each run has a timeout. Retries happen only before it has traded. Each run's status, error, tokens and cost are recorded.
- **Clean shutdown:** on SIGTERM, in-flight runs are recorded as interrupted and the lease is released. A new leader marks runs a crashed process left behind as failed.

## Consequences

- **No broker:** no Redis and nothing else to run. The database the app already needs is the only coordination point, and it's transactional.
- **Easy to read and test:** the scheduling is one short module, and the tests drive it directly.
- **No distributed queue:** runs of one cycle execute concurrently in one process. That fits a handful of traders whose time is spent waiting on LLMs, but hundreds of traders would want a work queue spread across processes.
- **Commands have a delay:** they're polled every `COMMAND_POLL_SECONDS`, not pushed.
