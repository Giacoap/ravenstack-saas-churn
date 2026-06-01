# RavenStack — SaaS Churn & Retention Analysis

A Revenue & Growth Analytics case study examining churn risk, cohort retention, and segment-level LTV for a fictional B2B SaaS company. Built as an operational monitoring tool for the VP of Customer Success, the project demonstrates cohort-based retention modeling, churn risk scoring, MRR tracking, and ICP segmentation — core capabilities for Revenue & Growth Analytics in SaaS environments.

## Dashboard

Interactive dashboard: [RavenStack — SaaS Churn & Retention Analysis](https://public.tableau.com/app/profile/giacomo.apicella/viz/ravenstack-dashboard/RiskList?publish=yes)

4 views: Risk List · Executive Summary · Cohort Retention · Segment Health

## Dataset

Synthetic dataset generated to simulate a realistic B2B SaaS environment.

| File | Rows | Description |
|---|---|---|
| `account_metrics.tsv` | 403 | One row per account (active + churned) |
| `churn_risk_scores.tsv` | 131 | Active accounts with churn risk scores |
| `cohort_metrics.tsv` | 24 | Monthly cohort retention (wide format) |
| `segment_metrics.tsv` | 18 | Aggregated metrics by segment |
| `subs_flat.tsv` | 5,000 | One row per subscription |

- **Period:** 24 months (Jan 2023 – Nov 2024)
- **Accounts:** 500 total (131 active, 272 churned at analysis date)
- **Note:** Dataset is synthetic. Findings demonstrate methodology, not real company data.

## Tools

- **Analysis:** Python — pandas, numpy, matplotlib, seaborn
- **Dashboard:** Tableau Public
- **Version control:** Git / GitHub

## Files

- `00_scoping.md` — business question, sub-questions, and metric definitions
- `01_analysis.py` — main analysis script (load/clean → EDA → metrics → analysis → export)
- `02_writeup.md` — narrative case study (in progress)
- `export/` — CSV files consumed by the Tableau dashboard
- `viz/` — exported Python visualizations
- `ravenstack-dashboard.twb` — Tableau workbook

## Reproducibility

1. Clone the repository
2. Download the dataset files into `data/`
3. Install dependencies: `pip install pandas numpy matplotlib seaborn`
4. Run: `python 01_analysis.py`
5. Open `ravenstack-dashboard.twb` in Tableau Public Desktop and reconnect to the TSV files in `data/`

## Key Findings

- **17 high-risk accounts** (13% of active base) flagged for immediate intervention, representing meaningful MRR at risk
- **Logo churn rate: 67.5%** — concentrated in SMB and early-tenure accounts
- **GRR: 97.8%** — strong gross revenue retention among accounts that survive past Month 1
- **M0→M1 retention drop: −15.7pp average** — the steepest loss in the customer lifecycle; accounts that don't activate in Month 1 rarely recover
- **ICP signal:** Enterprise accounts in FinTech/HealthTech acquired via Ads show the lowest churn (57.7%) and highest avg LTV (~$108K)
- **Ads channel** outperforms all other acquisition sources on both churn rate and LTV realized

Full narrative: `02_writeup.md` (in progress)

## Author

Giacomo Apicella · [github.com/Giacoap](https://github.com/Giacoap) · [giacoap.github.io](https://giacoap.github.io)
