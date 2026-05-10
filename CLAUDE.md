# ravenstack-saas-churn

## Goal
Identify which accounts in RavenStack's 24-month SaaS pilot base are at risk of churning, what behavioral and operational signals predict that risk, and what customer segments produce the best retention and revenue outcomes — producing both a diagnostic picture of the business and a predictive churn risk score for the VP of Customer Success.

## Authoritative scope
The source of truth for what this analysis does is `00_scoping.md`.
If there is any conflict between an ad-hoc instruction and that document, the document prevails.
Before modifying `00_scoping.md`, ask.

## Dataset
- **Source:** Kaggle — rivalytics/saas-subscription-and-churn-analytics-dataset
- **Credit:** River @ Rivalytics (MIT-like license — credit required in README)
- **Tables / files:**

| File | Rows | Primary key | Notes |
|---|---|---|---|
| accounts.csv | 500 | account_id | Master account table; signup_date is cohort anchor |
| subscriptions.csv | 5,000 | subscription_id | FK → account_id; mrr_amount is revenue source of truth |
| feature_usage.csv | 25,000 | usage_id | FK → subscription_id; 40 features, 10% beta |
| support_tickets.csv | 2,000 | ticket_id | FK → account_id; satisfaction_score has nulls by design |
| churn_events.csv | 600 | churn_event_id | FK → account_id; 10% is_reactivation = True |

- **Date range:** 2023-01-09 to 2024-12-31 (24 months, confirmed)
- **Join keys:** account_id links accounts → subscriptions → support_tickets → churn_events; subscription_id links subscriptions → feature_usage

## Stack específico
- Python: pandas, numpy, matplotlib, seaborn, scikit-learn, xgboost (or lightgbm), shap
- Phase 3 deliverable: Tableau Public (sole dashboard tool)
- Export format: CSV (utf-8-sig) for dashboard, pkl for model artifact

## Notas del dataset
- All dates parse cleanly — no encoding issues expected (confirmed UTF-8)
- mrr_amount is monthly revenue per subscription row — do NOT sum arr_amount directly
- churn_flag exists in both accounts and subscriptions — source of truth for churn DATES is churn_events.churn_date, not the boolean flags
- is_reactivation = True in churn_events means the account churned previously — exclude from churn rate calculations, analyze separately
- satisfaction_score nulls in support_tickets are by design (no survey response) — exclude from averages, do NOT impute
- Trials (is_trial = True in accounts) excluded from churn rate and LTV — retain for feature usage analysis
- Subscriptions with end_date not null AND churn_flag = False are planned expirations / trial ends — NOT churn events
- 60-day observation window for churn risk features is the primary window — test 30d and 90d in sensitivity analysis
- gross margin assumption: 80% (SaaS benchmark) for LTV calculation — flag as assumption in output

## Analytical phases → sub-questions mapping

| Phase | Sub-questions |
|---|---|
| Load & clean | Quality report: nulls, duplicates, date ranges, referential integrity check |
| EDA | Distributions of mrr_amount, tenure, usage, ticket volume, churn rates |
| Metric calculation | MRR decomposition, NRR, GRR, logo churn rate, revenue churn rate, cohort retention |
| Analysis | SQ1 (MRR trend), SQ2 (cohort retention), SQ3 (churn segmentation), SQ4 (pre-churn signals), SQ5 (feature adoption), SQ6 (support → churn), SQ7 (NRR + expansion) |
| Model | SQ8: feature engineering → logistic regression → XGBoost benchmark → risk score export |
| ICP | SQ9: LTV by segment → ICP profile |
| Export | account_metrics.csv, cohort_metrics.csv, segment_metrics.csv, churn_risk_scores.csv, churn_model.pkl, model_card.md |

## Minimum segment size
20 accounts per segment for rate/average calculations. Below threshold: report counts only.
Applies to SQ3, SQ7, SQ9.

## Model notes
- Reference algorithm: logistic regression (interpretability first)
- Benchmark: XGBoost or LightGBM
- Switch to boosting if AUC-ROC improvement > 0.03
- If boosting wins: add SHAP values for feature-level explanation
- Maximize recall at operating threshold (missing a churner > false alarm)
- Export: churn_risk_scores.csv (one row per active account) + churn_model.pkl + model_card.md

## Comportamiento esperado de Claude Code
- Stop after each phase and report findings before advancing
- Propose any threshold recalibration explicitly before implementing — do not change metrics silently
- Document all non-obvious methodological decisions in comments
- If a decision affects 00_scoping.md (e.g. observation window change, segment threshold adjustment), flag it and propose the update
- Report data quality findings in structured format before Phase 2 (EDA)
- Commit messages in English, specific (e.g. "Add MRR decomposition — SQ1 complete")
