#!/usr/bin/env python3
"""
generate_degraded_data.py
-------------------------
Simulates a "bad hour" for the data-quality improvement programme, e.g. a
partner institution uploading a malformed / incomplete batch. Used to exercise
the degradation-detection path of the hourly pipeline:

    python3 scripts/generate_degraded_data.py
    python3 scripts/quality_check.py        # detects >5pp degradation, warns

Heavily injects:
  - ~10% missing diagnosis codes
  - ~15% invalid sex values
  - ~10% future/malformed timestamps
  - ~8%  content duplicates
  - ~8%  consistency issues (out-of-range ages, site/country mismatch)

Output overwrites data/patient_records.csv (back up the good file first).
"""
import csv
import os
import random
from datetime import datetime, timedelta

random.seed(2026)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "data", "patient_records.csv")

VALID_COUNTRIES = {"UK", "FR", "DE"}

def corrupt(r):
    roll = random.random()
    r = dict(r)
    # missing diagnosis
    if roll < 0.10:
        r["diagnosis_code"] = ""
    # invalid sex
    if 0.10 <= roll < 0.25:
        r["sex"] = random.choice(["X", "U", "", "Q"])
    # timestamp anomaly
    if 0.25 <= roll < 0.35:
        r["record_timestamp"] = random.choice([
            (datetime.now() + timedelta(days=random.randint(2, 9))).strftime("%Y-%m-%dT%H:%M:%S"),
            "2026-13-45T99:99:99", "", "not-a-date",
        ])
    # consistency issue
    if 0.35 <= roll < 0.43:
        if random.random() < 0.5:
            r["patient_age"] = random.choice(["15", "16", "99", "104", "7"])
        else:
            r["site_id"] = random.choice(["ES-MAD-01", "US-NYC-01", "CN-BJS-01"])
    # duplicate (handled below)
    return r

def main():
    with open(SRC, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    fieldnames = list(rows[0].keys())

    out = []
    seen = set()
    dup_count = 0
    for r in rows:
        c = corrupt(r)
        # ~8% duplicates: repeat the (already corrupt) payload with new id
        key = tuple((f, c.get(f)) for f in fieldnames if f != "record_id")
        if key in seen and random.random() < 0.08:
            dup_count += 1
            out.append(c)
            continue
        seen.add(key)
        out.append(c)

    with open(SRC, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out)

    print(f"Overwrote {SRC} with {len(out)} degraded records "
          f"(duplicates injected: {dup_count}). Run quality_check.py now.")

if __name__ == "__main__":
    main()
