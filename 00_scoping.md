# RavenStack SaaS Churn & Retention Analysis — Scoping Document

*This document defines the analytical scope for the RavenStack SaaS Churn & Retention Analysis — a portfolio case study applying Revenue & Growth Analytics methodology to a synthetic 24-month SaaS pilot dataset. It serves as the authoritative contract between the scoping phase (Phase 1) and the implementation phase (Phase 2 in Claude Code). All metric definitions, sub-questions, and deliverable specifications in this document take precedence over any ad-hoc instructions during implementation.*

---

## 1. Business Context

RavenStack is a stealth-mode SaaS startup building AI-powered collaboration tools for technical teams. Over the past 24 months, the product was piloted privately with a curated base of accounts — primarily coding bootcamp graduates, indie developers, and early-stage tech teams — under a deliberately closed go-to-market motion designed to refine the product before a public launch. Every account interaction during the pilot was instrumented and logged: subscription lifecycles, feature usage events, support ticket activity, and churn outcomes with stated reasons. That captured history is the substrate of this analysis.

The pilot phase has produced a base of 500 paying accounts across multiple industries, plan tiers, and acquisition channels. As the company prepares to exit stealth mode, the operational picture is no longer optional to understand. Customer Success has just been formalized as a function — until now, retention was managed reactively by the founders, on a per-account basis, when problems surfaced. That model worked at 50 accounts. It will not work at 5,000. The function needs a methodology before scale forces one to emerge by accident.

The role of this analysis is to build that methodology. The Customer Success team needs to know three things before public launch: which accounts in the existing base are at active risk of churning, what operational and behavioral patterns separate accounts that retain from accounts that leave, and what early signals — in feature usage, support activity, or plan movement — can be monitored continuously to identify risk before it becomes loss. None of these are static answers. They are the inputs to a system that has to operate at scale once new accounts arrive at a much higher rate.

There is also a structural information asymmetry that this analysis is built to resolve. Individual accounts experience their own subscription, their own support tickets, their own usage. Founders and product leads have seen patterns anecdotally — the sense that certain industries churn faster, that downgrades often precede cancellations, that high-touch support cases tend to escalate into losses — but anecdote is not a methodology. Customer Success cannot be staffed, trained, or measured against intuition. The platform-level view that aggregates 500 accounts, 5,000 subscription records, 25,000 usage events, and 600 churn outcomes into a single coherent picture is the view this analysis exists to produce, and the view that the new CS function will operate from going forward.

---

## 2. Stakeholder & Decision

The primary stakeholder for this analysis is RavenStack's **VP of Customer Success** — the function's first dedicated hire, responsible for building the retention methodology from scratch before the platform exits stealth mode. This role operates at the intersection of account health monitoring, proactive intervention, and cross-functional feedback: the VP needs to know which accounts are at risk today, what is driving that risk, and what actions — outreach, escalation, plan adjustment, product feedback — are most likely to reverse it. The analysis is designed to be the operational foundation of that function, not a one-time report to be filed and forgotten.

The secondary stakeholders are the **founders**, who retain strategic decision-making authority over pricing architecture, product roadmap prioritization, and go-to-market sequencing ahead of public launch. Where the VP of CS uses the analysis to manage individual accounts, the founders use the same findings to answer structural questions: are we acquiring the right customer segments, is our plan tier structure producing the retention outcomes we need, and are there product gaps that churn data reveals before we scale acquisition? The same dataset serves both levels — operational and strategic — but the framing of findings and recommendations shifts depending on the audience.

This analysis is structured around three types of decisions, ordered by time horizon:

**Primary decision — risk intervention.** Which accounts in the current base need active attention right now? The analysis produces a churn risk score for each account, derived from behavioral signals in feature usage, support history, and subscription movements. This score powers a prioritized intervention list that the VP of CS can act on immediately — not a segment to monitor, but a ranked list of accounts to contact this week.

**Secondary decision — ICP validation and pattern replication.** What do retained accounts have in common? Which industries, acquisition channels, plan tiers, and usage patterns are associated with the best retention outcomes? These patterns inform how the founders position the product at launch — which segments to target in paid acquisition, which onboarding flows to invest in, and which plan configurations to push as the default.

**Tertiary decision — root cause diagnosis.** When an account churns, or shows elevated risk, is the driver operational (slow support resolution, unresolved escalations), behavioral (low feature adoption, declining usage), or structural (plan-product fit mismatch, pricing sensitivity)? The `reason_code` field in churn events and the correlation between support ticket patterns and churn outcomes allow the CS team to route problems to the right owner — a pricing complaint goes to the founders, a feature gap goes to product, a support failure goes to the CS team itself.

---

## 3. Central Business Question

*What is the current retention and revenue health of RavenStack's pilot account base — measured through subscription lifecycle, MRR movements, and cohort retention — and which behavioral signals across feature usage, support activity, and plan history allow the Customer Success team to identify accounts at risk of churning before that risk becomes loss?*

This question has two linked components that together define the scope of the analysis. The first is diagnostic: establishing the factual state of the business before public launch — how MRR is moving, where cohort retention breaks down, which segments retain and which churn, and what the revenue impact of that churn has been. The second is predictive: converting those patterns into a forward-looking instrument — a churn risk score at the account level, derived from the behavioral and operational signals that historically preceded cancellation. Neither component is useful without the other. The diagnostic layer without prediction produces a retrospective report the CS team cannot act on. The predictive layer without the diagnostic foundation produces scores with no interpretive context, disconnected from the business reality that generated them.

The three signal sources named in the question — feature usage, support activity, and plan history — are not arbitrary. They correspond directly to the three tables in the dataset that capture account behavior over time: `feature_usage`, `support_tickets`, and `subscriptions`. Each represents a distinct dimension of the customer relationship: whether the product is being used, whether the relationship is under strain, and whether the commercial commitment is stable or eroding. A churn risk score built from all three is more robust than one built from any single dimension, and more interpretable for a CS team that needs to understand *why* an account is flagged, not just *that* it is.

---

## 4. Analytical Sub-Questions

The central business question decomposes into nine sub-questions, ordered to build progressively from revenue health and retention patterns toward behavioral drivers and, finally, a predictive instrument and ICP profile that synthesize all prior findings.

**SQ1 — MRR decomposition and revenue trend.** How is MRR moving across the 24-month pilot period? What is the breakdown of new, expansion, contraction, and churned MRR each month, and is net new MRR positive or negative? This establishes the revenue health baseline — whether RavenStack is growing, plateauing, or losing ground to churn — and frames all subsequent analysis in terms of financial impact rather than account counts alone.

**SQ2 — Cohort retention.** How does retention vary across acquisition cohorts? Are accounts acquired in more recent months retaining better or worse than earlier cohorts, and at which tenure milestone — M1, M3, M6, or M12 — does retention break down most sharply? The cohort retention matrix is the foundational view for understanding whether the product's ability to retain customers is improving over time or deteriorating.

**SQ3 — Churn segmentation.** Where is churn concentrated? Which industries, plan tiers, referral sources, and account sizes — measured by seat count — produce the highest logo churn rate and revenue churn rate? This sub-question distinguishes between churn that is broadly distributed across the base and churn that is structurally concentrated in specific segments, which has direct implications for how the CS team allocates intervention resources.

**SQ4 — Behavioral signals preceding churn.** What patterns in feature usage, support activity, and subscription history appear in the weeks and months before an account churns? Do churned accounts show declining usage, increasing ticket volume, escalations, or plan downgrades in a predictable window before cancellation? Identifying these signals — and quantifying how far in advance they appear — is the prerequisite for any early warning system.

**SQ5 — Feature adoption and retention.** Which features are associated with stronger retention outcomes? Do accounts that adopt specific features within their first 30 or 60 days show meaningfully better M6 and M12 retention than those that do not? This sub-question identifies the behavioral threshold — the product's activation moment — that the CS team can use to guide early onboarding interventions.

**SQ6 — Support load as a churn predictor.** Do accounts with high ticket volume, frequent escalations, low satisfaction scores, or slow resolution times churn at higher rates than accounts with lighter support footprints? This sub-question tests whether the support system is functioning as an early warning channel or as a lagging indicator that surfaces problems too late to address.

**SQ7 — NRR and expansion patterns.** Is Net Revenue Retention above or below 100%? Which segments generate expansion MRR through upgrades, and which produce contraction MRR through downgrades? What characterizes an account that expands versus one that contracts or churns? NRR is the single metric that most directly answers whether RavenStack's existing base is a growth asset or a liability heading into public launch.

**SQ8 — Predictive churn risk model.** Using the behavioral and operational signals identified in SQ4 through SQ6, can a churn risk score be constructed at the account level that meaningfully separates high-risk from low-risk accounts in the current active base? Which signal categories — usage, support, or plan history — carry the most predictive weight, and how many accounts in the active base are flagged as high-risk today? This sub-question is the analytical synthesis of the prior three, converting diagnostic findings into a forward-looking instrument the CS team can act on immediately.

**SQ9 — ICP profile.** Synthesizing retention, expansion, and estimated LTV across segments: which combination of industry, plan tier, referral source, and account size produces the best customer outcomes on RavenStack's platform? This profile is the strategic output of the entire analysis — the evidence-based answer to which customer segments the go-to-market motion should prioritize at public launch, and which the CS team should weight most heavily in onboarding and expansion efforts.

---

## 5. Key Metrics & Definitions

The following definitions specify exactly how each metric is calculated, which table and column serves as the source of truth, and how edge cases are handled. Claude Code must use these definitions without deviation. Any recalibration discovered during EDA must be proposed explicitly and documented here before implementation.

---

**1. Monthly Recurring Revenue (MRR)**
The sum of `mrr_amount` across all active subscriptions in a given calendar month. A subscription is considered active in month M if its `start_date` ≤ last day of M and either `end_date` is null or `end_date` > last day of M. MRR is calculated as an end-of-month snapshot. `arr_amount` is not used directly — it is treated as a derived field (`mrr_amount × 12`) and used only for ARR reporting in SQ7.

**2. MRR Movement Decomposition**
Net new MRR each month is decomposed into four components, all sourced from `subscriptions`:
- **New MRR**: `mrr_amount` from subscriptions whose `start_date` falls within the month and whose account has no prior subscription with a non-null `end_date` (i.e., genuinely new accounts).
- **Expansion MRR**: incremental `mrr_amount` from accounts that had an active subscription in the prior month and whose current subscription has a higher `mrr_amount` (captured by `upgrade_flag = True`).
- **Contraction MRR**: reduction in `mrr_amount` from accounts whose current subscription has a lower amount than the prior month (captured by `downgrade_flag = True`). Reported as a negative value.
- **Churned MRR**: `mrr_amount` of subscriptions whose `end_date` falls within the month and `churn_flag = True`. Reported as a negative value.
- **Net New MRR** = New MRR + Expansion MRR + Contraction MRR + Churned MRR.

**3. Net Revenue Retention (NRR)**
Measured over a rolling 12-month window. For a cohort of accounts active at the start of the window:
NRR = (Starting MRR + Expansion MRR − Contraction MRR − Churned MRR) / Starting MRR × 100.
NRR > 100% means the existing base grows without new account acquisition. Calculated at the total base level and by segment (industry, plan tier). Accounts with `is_reactivation = True` in `churn_events` are excluded from the starting cohort to avoid double-counting.

**4. Gross Revenue Retention (GRR)**
GRR = (Starting MRR − Contraction MRR − Churned MRR) / Starting MRR × 100.
Calculated alongside NRR. GRR ≤ NRR always. GRR isolates retention without the upward effect of expansion — a useful complement when evaluating whether strong NRR is driven by genuine retention or by upsell masking churn.

**5. Logo Churn Rate**
The percentage of active accounts at the start of a month that have a `churn_date` within that month in `churn_events`, excluding reactivations (`is_reactivation = False`). Calculated monthly and as a trailing 3-month average to smooth volatility. Source of truth: `churn_events.churn_date` joined to `accounts.account_id`. The `churn_flag` in `accounts` is used as a validation check only — it is not the primary churn signal because it does not carry a date.

**6. Revenue Churn Rate**
The percentage of MRR lost in a month from accounts that fully cancelled — defined as subscriptions where `churn_flag = True` and `end_date` falls within the month. Excludes contraction MRR (partial revenue loss from downgrades). Revenue churn rate = Churned MRR / Starting MRR × 100. Reported alongside logo churn rate — divergence between the two signals whether churn is concentrated in high-MRR or low-MRR accounts.

**7. Cohort Retention Rate**
Accounts grouped by their `signup_date` month in `accounts`. For each cohort, retention rate at period P = (accounts in cohort still active at month P) / (accounts in cohort at month 0) × 100. "Still active" means no `churn_date` in `churn_events` as of month P, or a `churn_date` followed by a reactivation (`is_reactivation = True`) that precedes month P. Retention is measured at M1, M3, M6, and M12. Cohorts with fewer than 10 accounts are excluded from the retention matrix to avoid small-sample distortion. Output: cohort retention matrix visualized as a heatmap with consistent color scale across all cohorts.

**8. Customer Lifetime Value (LTV)**
Estimated LTV per account = average `mrr_amount` across all subscriptions for that account × gross margin assumption of 80%, used as a standard benchmark for SaaS software businesses per industry convention (SaaS Capital, OpenView benchmarks); this assumption should be replaced with actual margin data if cost structure information becomes available / monthly churn rate of its segment. Where individual account churn rate is undefined (active accounts), the segment-level monthly churn rate is used as the denominator. LTV is calculated by segment (industry, plan tier) to support ICP analysis in SQ9. It is not used as a monitoring metric — it is a strategic segmentation variable only.

**9. Churn Definition and Source of Truth**
An account is classified as churned if it has a record in `churn_events` with `is_reactivation = False`. Accounts with `is_reactivation = True` are treated as reactivations and analyzed separately — they are excluded from churn rate calculations but included in a dedicated reactivation segment. The `churn_flag` boolean in both `accounts` and `subscriptions` is used for validation and joins but is not the primary churn date source. Subscriptions with `end_date` not null and `churn_flag = False` represent planned expirations or trial ends — these are not counted as churn events.

**10. Churn Risk Score Features**
The predictive model in SQ8 uses features engineered from three signal categories, all measured over a 60-day observation window preceding the prediction date:

*Usage features* (from `feature_usage` joined to `subscriptions`):
- Total usage events in the last 60 days
- Distinct features used in the last 60 days (feature diversity)
- Days since last usage event (recency)
- Ratio of usage in days 31–60 vs days 1–30 (usage trend — declining vs growing)
- Beta feature usage flag (`is_beta_feature`)

*Support features* (from `support_tickets`):
- Total tickets submitted in the last 60 days
- Escalation rate (escalated tickets / total tickets)
- Average satisfaction score (null scores excluded, not imputed)
- Average resolution time in hours
- Presence of any urgent-priority ticket in the last 60 days

*Plan and account features* (from `subscriptions` and `accounts`):
- Account tenure in months at prediction date
- Current plan tier (encoded)
- `downgrade_flag` in the last 90 days
- `upgrade_flag` in the last 90 days
- Billing frequency (`monthly` vs `annual` — annual contracts have structurally lower churn risk)
- Seat count
- Referral source (encoded)
- Industry (encoded)

**11. Model Evaluation Metrics**
The churn risk model is evaluated using:
- **AUC-ROC** as the primary metric — measures the model's ability to rank high-risk accounts above low-risk accounts regardless of threshold, which is what the CS team needs for a prioritized intervention list.
- **Precision and Recall at a fixed threshold** — threshold set to maximize recall (minimize false negatives) because missing a churner is more costly than a false alarm in a CS intervention context. The operating threshold will be determined empirically from the validation set and documented in the analysis script.
- **Feature importance** — reported from the final model to validate that the signal categories identified in SQ4–SQ6 are actually driving predictions, not noise variables.

The reference algorithm is logistic regression, chosen for interpretability — the CS team needs to understand why an account is flagged, not just that it is. A gradient boosting model (XGBoost or LightGBM) will be trained as a performance benchmark. If the boosting model produces materially better AUC-ROC (> 0.03 improvement), it replaces logistic regression as the primary model with SHAP values used to preserve interpretability.

**12. Minimum Segment Size**
Any segmentation analysis (churn by industry, cohort retention by plan tier, LTV by referral source) requires a minimum of 20 accounts per segment to be included in comparative analysis. Segments below this threshold are reported as counts only and excluded from rate and average calculations. This threshold applies to SQ3, SQ7, and SQ9.

---

## 6. Scope & Constraints

**Dataset scope**
The analysis covers the RavenStack synthetic pilot dataset published by River @ Rivalytics, spanning 24 months from January 2023 to December 2024. The dataset comprises five tables: `accounts` (500 rows), `subscriptions` (5,000 rows), `feature_usage` (25,000 rows), `support_tickets` (2,000 rows), and `churn_events` (600 rows). All tables are referentially complete — no orphaned foreign keys — and are joined through `account_id` as the primary linking key, with `subscription_id` connecting `subscriptions` to `feature_usage`. The 500-account base reflects a deliberately closed pilot go-to-market motion and is not representative of a scaled customer base.

**What is included**
The analysis covers the full customer lifecycle observable in the dataset: account acquisition (signup date, referral source, initial plan tier), subscription activity (plan changes, upgrades, downgrades, billing frequency, MRR), product engagement (feature usage events, usage duration, error counts, beta feature adoption), support interactions (ticket volume, priority, resolution time, satisfaction scores, escalations), and churn outcomes (churn date, reason code, preceding plan movements, reactivation flag). All five tables are used across the nine sub-questions. The analysis spans the complete 24-month window for time-series metrics (MRR trend, cohort retention) and uses the full account base for segmentation and modeling.

**What is excluded**
- Accounts where `is_trial = True` in `accounts` at the time of analysis are excluded from churn rate and LTV calculations — trials that end without converting are not counted as churned paying customers. They are retained in feature usage and support analyses to examine trial-to-paid conversion signals if the data supports it.
- Reactivated accounts (`is_reactivation = True` in `churn_events`) are excluded from logo churn rate and revenue churn rate calculations. They are analyzed separately as a reactivation segment in SQ3.
- Subscription records with `end_date` not null and `churn_flag = False` represent planned expirations or trial endings — excluded from churn event analysis.
- Segments with fewer than 20 accounts are excluded from rate and average calculations in all segmentation analyses (SQ3, SQ7, SQ9) per the minimum segment size defined in Section 5.
- Customer Acquisition Cost (CAC) is not present in the dataset. LTV:CAC ratio — a canonical SaaS unit economics metric — cannot be calculated from available data. LTV is estimated and reported as a standalone metric; the ratio is explicitly flagged as unavailable.

**Known limitations**

*Synthetic data.* This dataset is fully synthetic, generated by a scripted Python pipeline using statistical distributions to simulate realistic SaaS behavior. All account names, domains, feedback text, and identifiers are fictional. The analysis is designed to demonstrate methodology, domain vocabulary, and analytical reasoning applied to a structurally realistic SaaS dataset — not to report findings about a real company. This distinction is stated explicitly in the repository README and in the write-up. Recruiters and data teams evaluating this case study should interpret the findings as a demonstration of analytical process, not as evidence about an actual business.

*Account base size.* 500 accounts is a small pilot base. Some industry segments, referral source categories, and plan tier combinations will fall below the 20-account minimum threshold and will be excluded from comparative analysis. The churn risk model trained on this base may not generalize to a post-launch account population with a materially different acquisition mix or behavioral profile. Both constraints are documented in the analysis script and acknowledged in the write-up limitations section.

*Predictive model observation window.* The 60-day observation window used to engineer churn risk features is a methodological choice, not an empirically derived optimal window. Alternative windows (30 days, 90 days) will be tested in sensitivity analysis during Phase 2. The chosen window and its rationale will be documented explicitly in the analysis script before the model is trained.

*Support satisfaction scores.* The `satisfaction_score` field in `support_tickets` contains nulls by design (customers who did not respond to the survey). These are excluded from average satisfaction calculations rather than imputed, to avoid introducing systematic bias. The null rate will be quantified in the Phase 2 data quality report. If the null rate exceeds 50%, satisfaction score will be demoted from a primary feature to a supplementary signal in the churn risk model.

*No carrier-equivalent confound.* Unlike the Olist dataset where delivery delays were partly attributable to logistics carriers outside seller control, the RavenStack dataset does not contain an equivalent structural confound. Churn reason codes in `churn_events` are treated as self-reported signals — they reflect the customer's stated reason, which may not fully capture the underlying driver. This is noted where reason code analysis is used in SQ3 and SQ4.

---

## 7. Expected Deliverables

This project produces five deliverables, each serving a distinct purpose and audience.

**1. Python analysis script (`01_analysis.py`)**
A clean, commented script structured by analytical phase: data loading and quality validation, exploratory data analysis, metric calculation (MRR decomposition, NRR, cohort retention, LTV, churn rates), sub-question analysis (SQ1–SQ9), churn risk model training and evaluation, and export. Each section maps explicitly to one or more sub-questions from Section 4. The script is fully reproducible: anyone who downloads the dataset from Kaggle and clones the repository can run the analysis from scratch without modification.

**2. Python visualizations**
A set of exploratory and analytical charts produced with matplotlib and seaborn, embedded directly in the analysis script. Each visualization includes a descriptive title, labeled axes with units, and an intentional color palette. Key charts include the cohort retention heatmap (consistent color scale across all cohorts), MRR waterfall decomposition by month, churn rate trend by segment, feature importance bar chart from the predictive model, and the churn risk score distribution across the active account base.

**3. Tableau Public dashboard (primary deliverable)**
The full operational dashboard built in Tableau Public, designed for use by the VP of Customer Success and the founders. Published with a public URL accessible without login or account creation, optimized for frictionless review by recruiters and portfolio reviewers. Includes four interconnected views: an executive summary with MRR trend, GRR, and logo churn rate as headline KPIs; a cohort retention matrix filterable by industry and plan tier; a churn risk account list ranked by risk score with the three component signals (usage, support, plan history) visible for each flagged account; and a segment health view comparing retention and revenue metrics across industries, plan tiers, and referral sources. Risk tiers use a double-coded accessibility approach (color + shape + label) to remain readable for color-blind users. The Tableau packaged workbook (`.twbx`) is committed to the repository for reproducibility, alongside high-resolution screenshots of each view for the README.

**4. Write-up and README (`02_writeup.md` + `README.md`)**
A narrative write-up in English structured as: executive summary → context → approach → key findings → tool in action → recommendations → limitations and future work. The executive summary explicitly names the SaaS metrics addressed (NRR, cohort retention, MRR decomposition, churn risk scoring) to make the case scannable for recruiters targeting Revenue & Growth Analytics roles. The README makes the repository self-explanatory: dataset source and credit to River @ Rivalytics, setup instructions, file structure, stack used (Python, Tableau Public), and a summary of key findings with a link to the Tableau Public dashboard URL. Both documents are written for an international recruiter and data team audience, with SaaS domain vocabulary used throughout without translation.

**5. Exported model artifacts**
The churn risk model produces two exported artifacts committed to `export/`:
- `churn_risk_scores.csv` — one row per active account, containing `account_id`, `account_name`, `risk_score` (0–1 probability), `risk_tier` (High / Medium / Low based on empirically determined thresholds), and the three component scores (usage signal, support signal, plan signal) that explain the composite score. This file feeds the Tableau Public dashboard directly.
- `churn_model.pkl` — the serialized trained model (scikit-learn pipeline including preprocessing and classifier), committed as evidence that a real trained object exists. Includes a `model_card.md` in the same directory documenting: algorithm used, training period, feature list, evaluation metrics (AUC-ROC, precision, recall at operating threshold), and known limitations.
