# ── Multi-worker uvicorn (#9) ─────────────────────────────────────────────────
# TRADEOFFS DOCUMENTED:
#  SQLite:  WAL journal_mode + busy_timeout=5000ms is already set on every
#           connection (sqlite_store.py). Two workers hit the same SQLite file;
#           WAL allows many readers + one concurrent writer. The 5 s busy_timeout
#           retries automatically on write contention. For Jay's single-user,
#           low write-rate workload this is safe. Activate SqliteWriteQueue
#           (async_writer.py stub) only if "database is locked" errors appear.
#
#  Finance cache: each worker keeps its own in-memory TTL cache. A cache miss
#           in one worker triggers a fresh Yahoo Finance fetch — no correctness
#           issue, just minor extra load. Acceptable for 2 workers.
#
#  WebSockets: each client TCP connection is handled by the OS and pinned to one
#           worker process (OS-level affinity). No sticky-session config needed
#           for Railway's direct-port model. NOTE: if a load balancer (nginx or
#           Railway HTTP proxy) is added, configure sticky sessions on it.
web: uvicorn jarvis.main:app --host 0.0.0.0 --port $PORT --workers ${WORKER_COUNT:-2}
