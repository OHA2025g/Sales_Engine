"""Process health for the worker and the scheduler.

The API image healthcheck must not be reused for either process.
Worker health is the worker heartbeat file. Beat health is a recent
scheduler heartbeat in the database.
"""

from __future__ import annotations

import os
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.session import get_engine, get_session
from app.services.scheduler_health import beat_status

WORKER_HEARTBEAT = Path(os.environ.get("WORKER_HEARTBEAT_PATH", "/tmp/agrayian-worker-heartbeat"))
WORKER_STALE_AFTER = timedelta(seconds=90)
BEAT_STALE_AFTER = timedelta(minutes=3)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


def worker_heartbeat_fresh(path: Path = WORKER_HEARTBEAT, *, now: datetime | None = None, stale_after: timedelta = WORKER_STALE_AFTER) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return False
    try:
        stamped = _aware(datetime.fromisoformat(text))
    except ValueError:
        return False
    return (now or datetime.now(UTC)) - stamped <= stale_after


def beat_heartbeat_fresh(*, stale_after: timedelta = BEAT_STALE_AFTER) -> bool:
    get_engine()
    db = get_session()
    try:
        status = beat_status(db, stale_after=stale_after)
    finally:
        db.close()
    return status.get("state") == "ok"


def api_live() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health/live", timeout=3) as response:
            return int(getattr(response, "status", 0)) == 200
    except Exception:
        return False


def main(argv: list[str]) -> int:
    role = argv[1] if len(argv) > 1 else os.environ.get("SERVICE_ROLE", "api")
    if role == "worker":
        return 0 if worker_heartbeat_fresh() else 1
    if role == "beat":
        return 0 if beat_heartbeat_fresh() else 1
    if role == "api":
        return 0 if api_live() else 1
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
