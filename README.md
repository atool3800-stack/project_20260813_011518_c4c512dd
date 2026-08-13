# Multinational Healthcare Data Quality Repository

[![Hourly Sync](https://github.com/atool3800-stack/project_20260813_011518_c4c512dd/actions/workflows/hourly_quality_sync.yml/badge.svg)](https://github.com/atool3800-stack/project_20260813_011518_c4c512dd/actions/workflows/hourly_quality_sync.yml)

This repository hosts **anonymised patient-level and clinical-trial records**
contributed by partner institutions in the **United Kingdom, France and Germany**
(more than 10,000 records). It is operated by an academic research group that
coordinates a cross-border healthcare **data-quality improvement programme**.

To guarantee **transparency and traceability**, an automated pipeline runs
**every hour** to:

1. pull the latest data from this remote repository;
2. run a battery of quality checks over the dataset;
3. aggregate key quality indicators (completeness, validity, consistency,
   duplicate rate, timestamp anomalies, …);
4. generate/update a Markdown quality report;
5. sync the metrics into the fixed **Data Quality Status** section below;
6. commit the changes with `git` and push them back via the GitHub API;
7. if any metric degrades by more than **5 percentage points** versus the
   previous hour, append a warning marker next to the status badge and record
   the event in [`CHANGELOG.md`](CHANGELOG.md).

---

<!-- QUALITY_REPORT:START -->
## Data Quality Status

![Quality](https://img.shields.io/badge/data%20quality-PASSING-brightgreen)

**Status:** PASSING

**Last check:** 2026-08-13 03:06:40

**Records checked:** 10,500


| Metric | Value |
|--------|------:|
| Completeness | 99.85% |
| Validity | 98.39% |
| Consistency | 99.49% |
| Duplicate rate | 0.37% |
| Timestamp anomaly | 0.98% |

*Full report: [reports/quality_report_20260813_030640.md](reports/quality_report_20260813_030640.md)*
<!-- QUALITY_REPORT:END -->

---

## Repository layout

| Path | Purpose |
|------|---------|
| `data/patient_records.csv` | Anonymised patient/clinical-trial records (UK, FR, DE) |
| `scripts/quality_check.py` | Hourly data-quality pipeline (metrics, report, README sync, git push) |
| `scripts/generate_data.py` | Reproducible dataset generator (seeded) |
| `scripts/run_sync.sh` | Hourly runner wrapper (pull → check → report → push) |
| `reports/` | Timestamped Markdown quality reports |
| `CHANGELOG.md` | Hourly changelog incl. degradation alerts |
| `.github/workflows/hourly_quality_sync.yml` | Hourly automation (GitHub Actions) |

## How to run manually

```bash
cd project_20260813_011518_c4c512dd
# run the full hourly sync (pull + check + report + push)
bash scripts/run_sync.sh
# or run the checks without pushing
python3 scripts/quality_check.py --no-push
```

## Automation

The pipeline is scheduled **every hour** through two complementary mechanisms:

1. **GitHub Actions workflow** (`.github/workflows/hourly_quality_sync.yml`)
   triggered on a cron schedule (`0 * * * *`).
2. **Local cron entry** (see `scripts/install_cron.sh`) for environments where
   Actions is not available.

## Contact

Academic research coordinator — email: `test_user_c4c512dd@example.com`
