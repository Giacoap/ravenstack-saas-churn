# RavenStack — SaaS Churn & Retention Analysis

A Revenue & Growth Analytics case study examining churn risk, cohort retention, and segment-level LTV for a fictional B2B SaaS company. Built as an operational monitoring tool for the VP of Customer Success, the project demonstrates cohort-based retention modeling, churn risk scoring, MRR tracking, and ICP segmentation — core capabilities for Revenue & Growth Analytics in SaaS environments.

## Dashboard

Interactive dashboard: [RavenStack — SaaS Churn & Retention Analysis](https://public.tableau.com/app/profile/giacomo.apicella/viz/ravenstack-dashboard/RiskList?publish=yes)

4 views: Risk List · Executive Summary · Cohort Retention · Segment Health

## Dataset

Synthetic dataset generated to simulate a realistic B2B SaaS environment.

| File | Rows | Description |
|---|---|---|
| `account_metrics.tsv` | 403 | One row per non-trial account (active + churned) |
| `churn_risk_scores.csv` | 131 | Active accounts with churn risk scores |
| `cohort_metrics.tsv` | 24 | Monthly cohort retention (wide format) |
| `segment_metrics.tsv` | 18 | Aggregated metrics by segment |
| `subs_flat.tsv` | 5,000 | One row per subscription (8–10 concurrent per account) |

- **Period:** 24 months (Jan 2023 – Dec 2024). December 2024 coincides with the pilot shutdown and is excluded from monthly churn rates as a mass-cancellation artifact.
- **Accounts:** 500 total — 403 non-trial (the churn analysis universe: 272 churned, 131 active at analysis date) and 97 trial accounts.
- **Subscription structure:** each account runs 8–10 concurrent subscriptions. This inflates net revenue retention (NRR) to ~335%, so NRR was excluded and gross revenue retention (GRR) used as the primary dollar-retention metric.
- **Note:** Dataset is synthetic. Findings demonstrate methodology, not real company data.

## Tools

- **Analysis:** Python — pandas, numpy, matplotlib, seaborn
- **Dashboard:** Tableau Public
- **Version control:** Git / GitHub

## Files

- `00_scoping.md` — business question, sub-questions, and metric definitions
- `01_analysis.py` — main analysis script (load/clean → EDA → metrics → analysis → export)
- `02_writeup.md` — narrative case study
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

- **The retention problem is front-loaded.** The M0→M1 drop averages −15.7pp — the steepest loss in the customer lifecycle. Accounts that don't activate in their first month rarely recover; cohort survival falls to 47.1% by Month 12.
- **Logo churn: 67.5% cumulative** over the 24-month pilot (272 of 403 non-trial accounts), inflated by the December shutdown; the monthly rate excluding that artifact is ~15%. Churn concentrates in early-tenure accounts (median tenure of churned accounts is 2.7 months vs. 10.0 for active).
- **GRR: 97.8%** — median of twelve calendar-anchored 12-month rolling windows, expansion excluded. Logo churn (account survival) and GRR (calendar-month dollar base) rest on different denominators and are not directly comparable: high dollar retention coexists with heavy logo attrition because of the concurrent-subscription structure.
- **NRR excluded by design.** The concurrent-subscription architecture inflates NRR to ~335%, making it non-comparable to SaaS benchmarks; GRR is reported in its place — a deliberate rigor decision, not a gap.
- **Churn predicts on usage density, not disengagement.** A standard assumption — that accounts go quiet before cancelling — did not hold: churning accounts were *more* active than retained ones. The real signal is short tenure combined with usage concentrated relative to that tenure, encoded in a churn-risk model (logistic regression, AUC 0.813).
- **17 high-risk accounts** (13% of the active base) flagged for immediate intervention via the risk model, representing ~$317K in monthly recurring revenue (≈$3.8M annualized) — 11.3% of the active base's MRR — concentrated in recently-signed accounts.
- **ICP signal:** Enterprise accounts in FinTech/HealthTech acquired via Ads show the lowest churn (57.7%) and a top-tier avg LTV (~$108K). Organic has the highest raw LTV ($108,291) but the worst retention (73.4% churn); Ads offers the best combination of LTV and retention.

Full narrative: `02_writeup.md`

## Author

Giacomo Apicella · [github.com/Giacoap](https://github.com/Giacoap) · [giacoap.github.io](https://giacoap.github.io)
