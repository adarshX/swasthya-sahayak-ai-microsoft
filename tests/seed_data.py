"""
Swasthya Sahayak - Seed Script
================================
Posts realistic fake triage records to the backend to fix the cold-start
problem (empty dashboard on first demo).

Usage:
    python tests/seed_data.py
    python tests/seed_data.py --url https://your-ngrok-url.ngrok-free.app
    python tests/seed_data.py --url http://localhost:8080 --count 20
"""

import argparse
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import urllib.request as req
except ImportError:
    sys.exit("Python 3.x required")

# ── Sample data pools ────────────────────────────────────────────────────────

URGENT_CASES = [
    {"age_under_5": True,  "fever": True,  "fast_breathing": True},
    {"age_under_5": True,  "fever": True,  "fast_breathing": True},
    {"age_under_5": True,  "fever": False, "fast_breathing": True},
]
PHC_CASES = [
    {"age_under_5": True,  "fever": True,  "fast_breathing": False},
    {"age_under_5": True,  "fever": False, "fast_breathing": False},
    {"age_under_5": False, "fever": True,  "fast_breathing": True},
]
HOME_CASES = [
    {"age_under_5": False, "fever": True,  "fast_breathing": False},
    {"age_under_5": False, "fever": False, "fast_breathing": False},
    {"age_under_5": True,  "fever": False, "fast_breathing": False},
]

CASE_POOL = (
    [(s, "Urgent Referral") for s in URGENT_CASES] * 3 +
    [(s, "PHC Visit")       for s in PHC_CASES] * 4 +
    [(s, "Home Care")       for s in HOME_CASES] * 5
)


def post_record(base_url: str, record: dict) -> bool:
    url   = f"{base_url.rstrip('/')}/sync-record"
    data  = json.dumps(record).encode()
    rq    = req.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",
    })
    try:
        with req.urlopen(rq, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def seed(base_url: str, count: int) -> None:
    print(f"\n  Seeding {count} records to {base_url} ...\n")

    now = datetime.now(timezone.utc)
    ok  = 0

    for i in range(count):
        symptoms, triage = random.choice(CASE_POOL)
        # Spread records over the last 48 hours for a realistic timeline
        offset  = timedelta(hours=random.uniform(0, 48))
        ts      = (now - offset).isoformat()

        record = {
            "patient_id": str(uuid.uuid4()),
            "symptoms":   symptoms,
            "triage":     triage,
            "timestamp":  ts,
        }

        label = {
            "Urgent Referral": "🚨",
            "PHC Visit":       "⚠️ ",
            "Home Care":       "✅",
        }[triage]
        print(f"  [{i+1:02d}/{count}] {label} {triage:<18}  patient {record['patient_id'][:8]}…", end=" ")

        if post_record(base_url, record):
            print("OK")
            ok += 1
        else:
            print("FAIL")

        time.sleep(0.15)   # avoid hammering the server

    print(f"\n  Done: {ok}/{count} records seeded.\n")
    if ok == count:
        print("  ✓ Dashboard should now show live data.")
    else:
        print("  ⚠  Some records failed. Is the backend running?")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed fake triage data")
    parser.add_argument("--url", default="http://localhost:8080",
                        help="Backend base URL (default: http://localhost:8080)")
    parser.add_argument("--count", type=int, default=15,
                        help="Number of records to seed (default: 15)")
    args = parser.parse_args()

    # Auto-load .env for base URL override
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    seed(args.url, args.count)
