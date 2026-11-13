"""Send email alerts on their own (the daily refresh also does this automatically).

    python -m scripts.send_alerts            # send using SMTP_* settings
    ALERTS_CONSOLE=1 python -m scripts.send_alerts   # print emails instead of sending
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.alerts.digest import send_alerts  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Database  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    db = Database(settings.database_url)
    db.create_all()
    report = send_alerts(db, settings)
    print(json.dumps(report, indent=2))
    return 1 if report.get("status") == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
