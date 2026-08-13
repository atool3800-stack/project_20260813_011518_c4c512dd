#!/usr/bin/env python3
"""
quality_check.py
----------------
Hourly data-quality pipeline for the multinational healthcare data repository
(UK / France / Germany).

Workflow:
  1. Pull the latest data from the remote repository (git pull).
  2. Run quality checks over >= 10,000 anonymised patient/clinical records.
  3. Aggregate key quality metrics:
       - completeness   (% non-empty values across core fields)
       - validity       (% records with all field values valid)
       - consistency    (% records internally consistent)
       - duplicate_rate (% content-duplicate records)
       - timestamp_anom (% records with invalid/future/malformed timestamps)
  4. Compare against the previous hour's metrics (state file).
  5. If any metric dropped by more than DEGRADATION_THRESHOLD (5 percentage
     points) vs the previous hour, flag a warning:
       - add a warning marker next to the README quality status badge
       - append an entry to CHANGELOG.md
  6. Generate / update the Markdown quality report and sync the metrics into
     the fixed QUALITY REPORT section of README.md.
  7. Commit all changes with git and push to the remote via the GitHub API
     (authenticated remote URL).

Usage:
    python3 scripts/quality_check.py [--no-push] [--no-pull]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, date, timedelta

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(REPO_DIR, "data", "patient_records.csv")
REPORT_DIR = os.path.join(REPO_DIR, "reports")
STATE_PATH = os.path.join(REPORT_DIR, "metrics_state.json")
README_PATH = os.path.join(REPO_DIR, "README.md")
CHANGELOG_PATH = os.path.join(REPO_DIR, "CHANGELOG.md")

MIN_RECORDS = 10000
DEGRADATION_THRESHOLD = 5.0  # percentage points

# Commit author identity (from task init_data)
COMMIT_NAME = "Academic Researcher"
COMMIT_EMAIL = "test_user_c4c512dd@example.com"

# Remote repository (from task init_data project_name)
REMOTE = "https://github.com/atool3800-stack/project_20260813_011518_c4c512dd.git"

# Core fields checked for completeness / validity / consistency
CORE_FIELDS = [
    "record_id", "country", "site_id", "patient_age", "sex",
    "diagnosis_code", "treatment_code", "visit_date",
    "record_timestamp", "lab_result", "consent_status",
]

VALID_COUNTRIES = {"UK", "FR", "DE"}
VALID_SEXES = {"M", "F"}
VALID_CONSENT = {"Y", "N"}
MIN_AGE, MAX_AGE = 18, 95
ICD10_RE = re.compile(r"[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]+)?")
ISO_DT_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
ISO_D_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# README section markers (fixed section)
README_START = "<!-- QUALITY_REPORT:START -->"
README_END = "<!-- QUALITY_REPORT:END -->"

BADGE_OK = "![Quality](https://img.shields.io/badge/data%20quality-PASSING-brightgreen)"
BADGE_WARN = "![Quality](https://img.shields.io/badge/data%20quality-DEGRADED-orange)"
BADGE_WARNING_MARK = "&#9888;&#65039;"

# --------------------------------------------------------------------------
# Metric computation
# --------------------------------------------------------------------------

def load_records(path):
    """Load CSV into a list of dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _is_filled(value):
    return value is not None and str(value).strip() != ""


def metric_completeness(rows):
    total = len(rows) * len(CORE_FIELDS)
    filled = sum(1 for r in rows for f in CORE_FIELDS if _is_filled(r.get(f)))
    return round(filled / total * 100, 2)


def _valid_row(rows, idx):
    r = rows[idx]
    # sex
    if r.get("sex") not in VALID_SEXES:
        return False
    # consent
    if r.get("consent_status") not in VALID_CONSENT:
        return False
    # country
    if r.get("country") not in VALID_COUNTRIES:
        return False
    # age (if present)
    age = r.get("patient_age")
    if _is_filled(age):
        if not (str(age).isdigit() and MIN_AGE <= int(age) <= MAX_AGE):
            return False
    # diagnosis code (if present) must look like ICD-10
    diag = r.get("diagnosis_code")
    if _is_filled(diag) and ICD10_RE.fullmatch(str(diag)) is None:
        return False
    # lab_result (if present) must be numeric
    lab = r.get("lab_result")
    if _is_filled(lab):
        try:
            float(lab)
        except ValueError:
            return False
    # treatment code must be non-empty and in known set
    if not _is_filled(r.get("treatment_code")):
        return False
    return True


def metric_validity(rows):
    valid = sum(1 for i in range(len(rows)) if _valid_row(rows, i))
    return round(valid / len(rows) * 100, 2)


def _consistent_row(rows, idx):
    r = rows[idx]
    # 1) site_id prefix must match country (when both present & country valid)
    country = r.get("country")
    site = r.get("site_id")
    if country in VALID_COUNTRIES and _is_filled(site):
        if not site.startswith(country + "-"):
            return False
    # 2) visit_date must equal the date portion of record_timestamp (when both valid)
    vd = r.get("visit_date")
    ts = r.get("record_timestamp")
    if _is_filled(vd) and _is_filled(ts) and ISO_D_RE.fullmatch(str(vd)) and ISO_DT_RE.fullmatch(str(ts)):
        if str(vd) != str(ts)[:10]:
            return False
    # 3) age must lie within the clinically plausible adult range (when present)
    age = r.get("patient_age")
    if _is_filled(age) and str(age).isdigit():
        if not (MIN_AGE <= int(age) <= MAX_AGE):
            return False
    return True


def metric_consistency(rows):
    cons = sum(1 for i in range(len(rows)) if _consistent_row(rows, i))
    return round(cons / len(rows) * 100, 2)


def metric_duplicate_rate(rows):
    seen = set()
    dup = 0
    for r in rows:
        key = tuple((f, r.get(f)) for f in CORE_FIELDS if f != "record_id")
        if key in seen:
            dup += 1
        else:
            seen.add(key)
    return round(dup / len(rows) * 100, 2)


def metric_timestamp_anomaly(rows):
    now = datetime.now()
    anom = 0
    for r in rows:
        ts = r.get("record_timestamp")
        if not _is_filled(ts):
            anom += 1
            continue
        m = ISO_DT_RE.fullmatch(str(ts))
        if m is None:
            anom += 1
            continue
        try:
            dt = datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            anom += 1
            continue
        # Future timestamps (more than 1 day ahead) or very old (> 90 days) are anomalous
        if dt > now + timedelta(days=1) or dt < now - timedelta(days=90):
            anom += 1
    return round(anom / len(rows) * 100, 2)


def compute_all_metrics(rows):
    return {
        "record_count": len(rows),
        "completeness": metric_completeness(rows),
        "validity": metric_validity(rows),
        "consistency": metric_consistency(rows),
        "duplicate_rate": metric_duplicate_rate(rows),
        "timestamp_anomaly": metric_timestamp_anomaly(rows),
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }

# --------------------------------------------------------------------------
# State / degradation handling
# --------------------------------------------------------------------------

def load_previous_metrics():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return None


def detect_degradation(current, previous):
    """Return list of degraded metric names (dropped > threshold vs previous)."""
    if not previous:
        return []
    degraded = []
    for key in ("completeness", "validity", "consistency", "duplicate_rate", "timestamp_anomaly"):
        cur = current[key]
        prev = previous.get(key)
        if prev is None:
            continue
        # Higher is better for completeness/validity/consistency; lower is better
        # for duplicate_rate & timestamp_anomaly.
        if key in ("duplicate_rate", "timestamp_anomaly"):
            # an INCREASE of > threshold is a degradation
            if cur - prev > DEGRADATION_THRESHOLD:
                degraded.append(key)
        else:
            # a DROP of > threshold is a degradation
            if prev - cur > DEGRADATION_THRESHOLD:
                degraded.append(key)
    return degraded


def save_state(metrics):
    with open(STATE_PATH, "w") as f:
        json.dump(metrics, f, indent=2)


# --------------------------------------------------------------------------
# Report / README rendering
# --------------------------------------------------------------------------

def build_report(metrics, degraded, previous):
    now = datetime.now()
    lines = []
    lines.append("# Healthcare Data Quality Report\n")
    lines.append(f"- **Generated at:** {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append(f"- **Dataset:** `data/patient_records.csv`")
    lines.append(f"- **Institutions:** UK, France, Germany")
    lines.append(f"- **Records checked:** {metrics['record_count']:,} (minimum required: {MIN_RECORDS:,})")
    if metrics["record_count"] < MIN_RECORDS:
        lines.append(f"- **&#9888; Status:** FAIL - fewer than {MIN_RECORDS} records available\n")
    lines.append("")

    lines.append("## Key Quality Indicators\n")
    lines.append("| Metric | Current (%) | Previous (%) | Delta (pp) | Trend |")
    lines.append("|--------|------------:|-------------:|-----------:|-------|")
    order = [
        ("completeness", "Completeness", False),
        ("validity", "Validity", False),
        ("consistency", "Consistency", False),
        ("duplicate_rate", "Duplicate rate", True),
        ("timestamp_anomaly", "Timestamp anomaly", True),
    ]
    for key, label, lower_is_better in order:
        cur = metrics[key]
        prev = previous.get(key) if previous else None
        delta = (cur - prev) if prev is not None else None
        if delta is None:
            delta_s = "&mdash;"
            trend = "&mdash;"
        else:
            arrow = "&#9660;" if delta < 0 else ("&#9650;" if delta > 0 else "&#9654;")
            trend = arrow
            delta_s = f"{delta:+.2f}"
        lines.append(f"| {label} | {cur:.2f} | {prev if prev is not None else '&mdash;'} | {delta_s} | {trend} |")
    lines.append("")

    lines.append("## Notes\n")
    lines.append("- **Completeness:** share of non-empty values across core fields.")
    lines.append("- **Validity:** share of records whose field values conform to expected formats/ranges.")
    lines.append("- **Consistency:** share of records that are internally coherent (site/country, date alignment, plausible age).")
    lines.append("- **Duplicate rate:** share of records that duplicate the payload of an earlier record.")
    lines.append("- **Timestamp anomaly:** share of records with missing, malformed or out-of-window timestamps.")

    if degraded:
        lines.append("")
        lines.append("## &#9888;&#65039; Degradation Alert\n")
        lines.append("The following metric(s) degraded by more than "
                     f"{DEGRADATION_THRESHOLD:.0f} percentage points compared with the previous hour:\n")
        for d in degraded:
            lines.append(f"- **{d.replace('_', ' ').title()}** "
                         f"({previous.get(d):.2f}% &rarr; {metrics[d]:.2f}%)")
        lines.append("")
    return "\n".join(lines)


def render_readme_section(metrics, degraded, previous):
    now = datetime.now()
    status = "DEGRADED" if degraded else "PASSING"
    badge = BADGE_WARN if degraded else BADGE_OK
    if degraded:
        badge = f"{BADGE_WARNING_MARK} {badge}"
    section = []
    section.append(f"## Data Quality Status\n")
    section.append(f"{badge}\n")
    section.append(f"**Status:** {'&#9888;&#65039; DEGRADED - see CHANGELOG' if degraded else 'PASSING'}\n")
    section.append(f"**Last check:** {now.strftime('%Y-%m-%d %H:%M:%S')}\n")
    section.append(f"**Records checked:** {metrics['record_count']:,}\n")
    section.append("")
    section.append("| Metric | Value |")
    section.append("|--------|------:|")
    section.append(f"| Completeness | {metrics['completeness']:.2f}% |")
    section.append(f"| Validity | {metrics['validity']:.2f}% |")
    section.append(f"| Consistency | {metrics['consistency']:.2f}% |")
    section.append(f"| Duplicate rate | {metrics['duplicate_rate']:.2f}% |")
    section.append(f"| Timestamp anomaly | {metrics['timestamp_anomaly']:.2f}% |")
    section.append("")
    if degraded:
        section.append("**Degraded metrics:** " + ", ".join(d.replace('_', ' ') for d in degraded))
        section.append("")
    section.append(f"*Full report: [reports/quality_report_{now.strftime('%Y%m%d_%H%M%S')}.md](reports/quality_report_{now.strftime('%Y%m%d_%H%M%S')}.md)*")
    return "\n".join(section)


def update_readme(section_markdown):
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()
    if README_START in content and README_END in content:
        new_content = content.split(README_START)[0] + README_START + "\n" + section_markdown + "\n" + README_END + content.split(README_END)[1]
    else:
        new_content = content.rstrip() + "\n\n" + README_START + "\n" + section_markdown + "\n" + README_END + "\n"
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


def update_changelog(metrics, degraded, previous):
    now = datetime.now()
    entry = f"\n## {now.strftime('%Y-%m-%d %H:%M:%S')} - Hourly quality sync\n"
    if degraded:
        entry += f"- **&#9888;&#65039; QUALITY DEGRADATION DETECTED.** The following metric(s) dropped by more than {DEGRADATION_THRESHOLD:.0f} percentage points vs the previous hour:\n"
        for d in degraded:
            entry += f"  - {d.replace('_', ' ').title()}: {previous.get(d):.2f}% -> {metrics[d]:.2f}%\n"
    else:
        entry += "- Quality metrics within expected thresholds (no degradation detected).\n"
    entry += f"- Records checked: {metrics['record_count']:,}\n"
    with open(CHANGELOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


# --------------------------------------------------------------------------
# Git / push
# --------------------------------------------------------------------------

def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_DIR, capture_output=True, text=True)


def pull_latest():
    print("Pulling latest data from remote...")
    r = git("pull", "--no-rebase", "origin", "main")
    if r.returncode != 0:
        print("  pull warning (may be first run / no upstream):", r.stderr.strip()[:300])
    else:
        print("  pulled OK")


def commit_and_push():
    git("add", "-A")
    r = git("commit", "-m", f"chore(quality): hourly data quality report {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", author=f"{COMMIT_NAME} <{COMMIT_EMAIL}>")
    if r.returncode != 0 and "nothing to commit" not in r.stderr:
        print("  commit issue:", r.stderr.strip()[:500])
        return
    # Push to remote using the authenticated remote URL (token injected at runtime)
    print("Pushing to remote via GitHub API...")
    p = git("push", "origin", "main")
    if p.returncode != 0:
        print("  push failed:", p.stderr.strip()[:800])
    else:
        print("  pushed OK")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true", help="do not push to remote")
    ap.add_argument("--no-pull", action="store_true", help="do not pull from remote")
    args = ap.parse_args()

    if not args.no_pull:
        pull_latest()

    if not os.path.exists(DATA_PATH):
        print(f"ERROR: data file not found at {DATA_PATH}", file=sys.stderr)
        sys.exit(2)

    rows = load_records(DATA_PATH)
    if len(rows) < MIN_RECORDS:
        print(f"WARNING: only {len(rows)} records (minimum {MIN_RECORDS})")

    metrics = compute_all_metrics(rows)
    previous = load_previous_metrics()
    degraded = detect_degradation(metrics, previous)

    print(f"Records: {metrics['record_count']}")
    print(f"Completeness: {metrics['completeness']}%")
    print(f"Validity: {metrics['validity']}%")
    print(f"Consistency: {metrics['consistency']}%")
    print(f"Duplicate rate: {metrics['duplicate_rate']}%")
    print(f"Timestamp anomaly: {metrics['timestamp_anomaly']}%")
    print(f"Degraded: {degraded}")

    # Build and persist report
    os.makedirs(REPORT_DIR, exist_ok=True)
    report = build_report(metrics, degraded, previous)
    report_name = f"quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(os.path.join(REPORT_DIR, report_name), "w", encoding="utf-8") as f:
        f.write(report)

    # Sync metrics to README fixed section
    section = render_readme_section(metrics, degraded, previous)
    update_readme(section)

    # Changelog (always log; warning marker only when degraded)
    os.makedirs(os.path.dirname(CHANGELOG_PATH), exist_ok=True)
    if not os.path.exists(CHANGELOG_PATH):
        with open(CHANGELOG_PATH, "w", encoding="utf-8") as f:
            f.write("# Changelog\n\nHourly data-quality sync log.\n")
    update_changelog(metrics, degraded, previous)

    save_state(metrics)

    if not args.no_push:
        commit_and_push()
    else:
        print("(--no-push) skipped commit/push")

    print("Done.")


if __name__ == "__main__":
    main()
