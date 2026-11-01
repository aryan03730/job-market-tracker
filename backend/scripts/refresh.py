"""Run one refresh from the command line (this is what GitHub Actions calls).

    python -m scripts.refresh                 # refresh now
    python -m scripts.refresh --if-stale 20   # only if last good run is >20h old
    python -m scripts.refresh --only remotive,jobicy
    python -m scripts.refresh --demo          # offline: use saved sample responses

Exit codes: 0 = ok/partial/skipped, 1 = every provider failed, 2 = database unreachable.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.pipeline.refresh import hours_since_last_success, run_refresh  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-stale", type=float, metavar="HOURS",
                        help="skip unless the last successful run is older than HOURS")
    parser.add_argument("--only", help="comma-separated provider names")
    parser.add_argument("--demo", action="store_true", help="use bundled sample data, no network")
    parser.add_argument("--summary-file", help="write the run summary JSON here")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    db = Database(settings.database_url)
    try:
        db.wait_until_ready()
    except Exception as exc:
        logging.error("Database unreachable: %s", exc)
        return 2

    if args.if_stale is not None:
        db.create_all()
        age = hours_since_last_success(db)
        if age is not None and age < args.if_stale:
            logging.info("Data is fresh (%.1fh old); nothing to do.", age)
            return 0

    kwargs = {}
    env = None
    if args.demo:
        from tests.fake_http import FakeSession, demo_env
        kwargs["http_factory"] = FakeSession
        env = demo_env()
    only = args.only.split(",") if args.only else None
    summary = run_refresh(db, settings, env=env, only=only, **kwargs)

    text = json.dumps(summary, indent=2, default=str)
    print(text)
    if args.summary_file:
        Path(args.summary_file).write_text(text)
    return 1 if summary.get("status") == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
