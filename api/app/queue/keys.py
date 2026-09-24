"""Redis keys used by the job queue (SPEC §12.2)."""

PREFIX = "bz:"
JOBS = f"{PREFIX}jobs"  # stream; consumer group GROUP
DELAYED = f"{PREFIX}delayed"  # sorted set; score = run-at epoch ms, member = envelope JSON
DEAD = f"{PREFIX}dead"  # stream of dead-lettered jobs
STATS = f"{PREFIX}stats"  # hash of "<type>:<outcome>" counters
GROUP = "workers"

DONE_TTL_S = 7 * 24 * 3600
CRON_LOCK_TTL_S = 2 * 24 * 3600
STREAM_MAXLEN = 100_000  # approximate cap; acked entries are history only


def done_key(idempotency_key: str) -> str:
    return f"{PREFIX}done:{idempotency_key}"


def cron_key(name: str, scope: str, day: str) -> str:
    return f"{PREFIX}cron:{name}:{scope}:{day}"
