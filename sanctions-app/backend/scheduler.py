"""
Standalone daily scheduler. Run this as a long-lived process (or replace with
cron / a cloud scheduler hitting POST /api/ingest).

    python backend/scheduler.py
"""

import time
import json
import datetime
import ingest

INTERVAL_HOURS = 24

def main():
    print(f"[scheduler] starting; will ingest every {INTERVAL_HOURS}h")
    while True:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        print(f"[scheduler] {ts} running ingest...")
        try:
            report = ingest.run_ingest()
            print(json.dumps(report, indent=2))
        except Exception as e:
            print(f"[scheduler] ERROR: {e}")
        time.sleep(INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    main()
