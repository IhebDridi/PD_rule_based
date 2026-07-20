# Clever Cloud — oTree scaling (TG / Prolific)

Use this layout for Prolific and for `_with_bots` stress tests. oTree sessions
share one Postgres `Session` row; scaling out web instances usually makes
contention worse, not better.

## Recommended topology

| Piece | Recommendation |
|-------|----------------|
| App instances | **1** (scale vertically, not horizontally) |
| Redis | Required addon; link to the **Python app** (not Postgres) |
| Postgres | Existing `DATABASE_URL` / `POSTGRESQL_ADDON_URI` |
| Workers | Let `otree prodserver` use several processes on the **same** instance |

### Why one instance

Browser bots and wait-page polls serialize on the session row. Two Clever
instances double the lock fighters without doubling useful throughput for a
single session.

Prefer something like: **1 instance, 8 CPU, 16 GB** over **2 × smaller**.

### Redis

1. Create a Redis addon (S plan is enough; name e.g. `otree-channels-redis`).
2. **Link it to the Python oTree app** — Clever injects `REDIS_URL`.
3. Redeploy. oTree uses Redis for channels / wait-page wakeups across workers.
4. On BatchWait, Clever logs once per session whether Redis is linked (see
   `pages_classes/BatchWaitForGroup.py`).

Without Redis, multi-worker wait wakeups are less reliable; experiment data
still lives in Postgres either way.

### `run.sh`

```bash
export DATABASE_URL=${POSTGRESQL_ADDON_URI}
otree prodserver 9000
```

Optional bot pacing:

```bash
export OTREE_BOT_SUBMIT_DELAY_MS=1500
export OTREE_BOT_SUBMIT_JITTER_MS=1000
```

### Checklist

1. Scale to **1** Clever instance.
2. Confirm `REDIS_URL` on the Python app after linking Redis.
3. `OTREE_PRODUCTION=1` and admin password set.
4. Bot stress: start with 3–6 bots, not 20.
