#!/usr/bin/env python3
"""
generate_data.py
----------------
Generates anonymized patient-level / clinical-trial records for the
multinational healthcare data quality repository (UK, France, Germany).

Output: data/patient_records.csv  (>= 10,000 rows)

The generator intentionally injects a small, controlled amount of data-quality
issues (missing values, invalid values, duplicates, timestamp anomalies) so the
quality metrics are meaningful yet healthy. Seeded for reproducibility.
"""
import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)

NUM_RECORDS = 10500  # > 10,000 records

# -------- Country / site definitions --------
SITES = {
    "UK": ["UK-LDN-01", "UK-MAN-02", "UK-OXF-03"],
    "FR": ["FR-PAR-01", "FR-LYO-02", "FR-MRS-03"],
    "DE": ["DE-BER-01", "DE-MUC-02", "DE-HAM-03"],
}

# Plausible ICD-10 diagnosis codes per country (simplified)
DIAGNOSES = {
    "UK": ["E11.9", "I10", "J45.9", "N18.3", "M54.5", "F32.9", "E78.5", "I25.1"],
    "FR": ["E11.9", "I10", "J44.1", "K21.0", "E66.9", "F41.1", "I48", "M17.1"],
    "DE": ["E11.9", "I10", "J44.9", "E78.0", "I63.9", "F33.1", "K29.7", "N39.0"],
}

TREATMENTS = ["MET", "INS", "ACE", "BETA", "CORT", "STAT", "SURG", "RAD", "CHEM", "NONE"]

SEXES = ["M", "F"]
CONSENT = ["Y", "N"]

# Valid ISO country codes used in consistency checks
VALID_COUNTRIES = {"UK", "FR", "DE"}

# Age bounds
MIN_AGE, MAX_AGE = 18, 95

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "patient_records.csv")

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # Anchor: generate all records around a fixed reference time (stable for reproducibility)
    ref_time = datetime(2026, 8, 13, 1, 0, 0)

    rows = []
    seen_record_ids = set()

    for i in range(1, NUM_RECORDS + 1):
        country = random.choice(list(SITES.keys()))
        site = random.choice(SITES[country])
        record_id = f"PAT-{country}-{i:06d}"
        seen_record_ids.add(record_id)

        age = random.randint(MIN_AGE, MAX_AGE)
        sex = random.choice(SEXES)
        diagnosis = random.choice(DIAGNOSES[country])
        treatment = random.choice(TREATMENTS)
        consent = random.choice(CONSENT)

        # Timestamp within the last 24h window (hourly sync scenario)
        ts = ref_time - timedelta(seconds=random.randint(0, 24 * 3600))
        visit_date = ts.date().isoformat()
        record_timestamp = ts.strftime("%Y-%m-%dT%H:%M:%S")

        lab_result = round(random.uniform(0.5, 400.0), 2)

        # -------- Inject controlled quality issues --------
        # 1) Missing values (~1.5% of records have a missing field)
        missing_field = None
        if random.random() < 0.015:
            missing_field = random.choice(["patient_age", "diagnosis_code", "lab_result", "consent_status"])

        # 2) Invalid values (~1% of records)
        invalid_field = None
        if random.random() < 0.01:
            invalid_field = random.choice(["sex", "diagnosis_code", "consent_status", "country"])

        # 3) Consistency issue (~0.6% of records): age outside clinical plausible range for diagnosis
        consistency_issue = False
        if random.random() < 0.006:
            consistency_issue = True

        # 4) Timestamp anomaly (~1% of records): future timestamp or malformed
        timestamp_anomaly = False
        if random.random() < 0.01:
            timestamp_anomaly = True

        # 5) Duplicate (~0.3% of records): duplicate of a previous row (content-level)
        duplicate_of = None
        if i > 1 and random.random() < 0.003:
            duplicate_of = random.choice(rows[: i - 1])

        # -------- Apply issues --------
        if duplicate_of is not None:
            row = dict(duplicate_of)
            row["record_id"] = record_id  # keep unique id, duplicate the payload
            rows.append(row)
            continue

        # Apply missing
        if missing_field == "patient_age":
            age = ""
        elif missing_field == "diagnosis_code":
            diagnosis = ""
        elif missing_field == "lab_result":
            lab_result = ""
        elif missing_field == "consent_status":
            consent = ""

        # Apply invalid
        if invalid_field == "sex":
            sex = random.choice(["X", "U", ""])
        elif invalid_field == "diagnosis_code":
            diagnosis = random.choice(["ZZZ.99", "123", "E11"])
        elif invalid_field == "consent_status":
            consent = random.choice(["X", ""])
        elif invalid_field == "country":
            country = random.choice(["ES", "US", "CN"])

        if consistency_issue:
            # age too high for a paediatric-adjacent code, or age below min for adults
            if random.random() < 0.5:
                age = random.choice([16, 17, 99, 105])
            else:
                sex = "F" if sex == "M" else "M"

        if timestamp_anomaly:
            if random.random() < 0.6:
                record_timestamp = (ref_time + timedelta(days=random.randint(1, 5))).strftime("%Y-%m-%dT%H:%M:%S")
                visit_date = record_timestamp[:10]
            else:
                record_timestamp = random.choice(["2026-13-45T99:99:99", "not-a-date", ""])

        row = {
            "record_id": record_id,
            "country": country,
            "site_id": site,
            "patient_age": age,
            "sex": sex,
            "diagnosis_code": diagnosis,
            "treatment_code": treatment,
            "visit_date": visit_date,
            "record_timestamp": record_timestamp,
            "lab_result": lab_result,
            "consent_status": consent,
        }
        rows.append(row)

    # Write CSV
    fieldnames = list(rows[0].keys())
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} records to {OUT}")

if __name__ == "__main__":
    main()
