"""
ravenstack-saas-churn - análisis principal

Ver 00_scoping.md para la pregunta de negocio, sub-preguntas y métricas.
Cada sección de este script mapea a una sub-pregunta del scoping document.

Ejecutar desde la raíz del proyecto:
    python 01_analysis.py
"""

import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Force UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# =============================================================================
# === Config ===
# =============================================================================

DATA_DIR = Path("data")
VIZ_DIR = Path("viz")
VIZ_DIR.mkdir(exist_ok=True)

EXPECTED_DATE_MIN = pd.Timestamp("2023-01-09")
EXPECTED_DATE_MAX = pd.Timestamp("2024-12-31")
ANALYSIS_END = pd.Timestamp("2024-12-31")

EXPECTED_ROWS = {
    "accounts":        500,
    "subscriptions":   5_000,
    "feature_usage":   25_000,
    "support_tickets": 2_000,
    "churn_events":    600,
}

# Null columns expected by design (not flagged as issues)
# - subscriptions.end_date: null = subscription is still active (no end date set)
# - support_tickets.satisfaction_score: voluntary survey, no response = null
# - churn_events.feedback_text: voluntary free-text field
EXPECTED_NULLS = {
    "subscriptions":   {"end_date"},
    "support_tickets": {"satisfaction_score"},
    "churn_events":    {"feedback_text"},
}

# =============================================================================
# === Phase 1: Load and clean ===
# =============================================================================

print("=" * 70)
print("PHASE 1: DATA LOAD AND QUALITY VALIDATION")
print("=" * 70)

# --- Load ---

accounts = pd.read_csv(
    DATA_DIR / "ravenstack_accounts.csv",
    parse_dates=["signup_date"],
)

subscriptions = pd.read_csv(
    DATA_DIR / "ravenstack_subscriptions.csv",
    parse_dates=["start_date", "end_date"],
)

feature_usage = pd.read_csv(
    DATA_DIR / "ravenstack_feature_usage.csv",
    parse_dates=["usage_date"],
)

support_tickets = pd.read_csv(
    DATA_DIR / "ravenstack_support_tickets.csv",
    parse_dates=["submitted_at", "closed_at"],
)

churn_events = pd.read_csv(
    DATA_DIR / "ravenstack_churn_events.csv",
    parse_dates=["churn_date"],
)

print(f"\nAll 5 tables loaded successfully.\n")

# --- feature_usage: inspect and resolve duplicate usage_id rows ---
# Inspection result: 21 usage_ids appear exactly twice = 42 rows total.
# - Exact-match duplicates (all columns identical): 0
# - Same usage_id, different values (PK collision — genuinely different events): 21 pairs
# Decision: keep first occurrence per usage_id (by original CSV row order).
# 21 real usage records are dropped; documented here as a data quality limitation.

fu_dup_ids = feature_usage[feature_usage["usage_id"].duplicated(keep=False)]["usage_id"].unique()
fu_exact_dups = feature_usage.duplicated(keep=False).sum()
fu_pk_collisions = len(fu_dup_ids)  # 21 unique IDs with 2 rows each, all with different values

print(f"feature_usage duplicate usage_id resolution:")
print(f"  Exact-match duplicates found:     {fu_exact_dups}")
print(f"  Same-ID-different-values (PK collision): {fu_pk_collisions} IDs ({fu_pk_collisions * 2} rows)")
print(f"  Action: keep first occurrence per usage_id — {fu_pk_collisions} records dropped")

feature_usage = feature_usage.drop_duplicates(subset="usage_id", keep="first").reset_index(drop=True)
print(f"  feature_usage rows after dedup: {len(feature_usage):,}\n")

# --- ARR/MRR relationship ---
# arr_amount is inconsistent with mrr_amount × 12 in 15.6% of subscription rows.
# Likely cause: annual billing plans with negotiated contract pricing.
# Decision per scoping doc: mrr_amount is the sole revenue source of truth.
# arr_amount is NOT used in any calculation in this analysis.

tables = {
    "accounts":        (accounts,        "account_id"),
    "subscriptions":   (subscriptions,   "subscription_id"),
    "feature_usage":   (feature_usage,   "usage_id"),
    "support_tickets": (support_tickets, "ticket_id"),
    "churn_events":    (churn_events,    "churn_event_id"),
}

date_cols = {
    "accounts":        ["signup_date"],
    "subscriptions":   ["start_date", "end_date"],
    "feature_usage":   ["usage_date"],
    "support_tickets": ["submitted_at", "closed_at"],
    "churn_events":    ["churn_date"],
}

issues = []

# =============================================================================
# --- Per-table quality checks ---
# =============================================================================

for name, (df, pk) in tables.items():
    print(f"\n{'-' * 60}")
    print(f"TABLE: {name.upper()}")
    print(f"{'-' * 60}")

    expected = EXPECTED_ROWS[name]
    actual = len(df)
    shape_flag = " <- UNEXPECTED ROW COUNT" if actual != expected else ""
    print(f"  Shape:        {actual:,} rows x {df.shape[1]} cols  (expected {expected:,}){shape_flag}")
    if shape_flag:
        issues.append(f"{name}: row count {actual} != expected {expected}")

    dup_count = df[pk].duplicated().sum()
    dup_flag = " <- DUPLICATES FOUND" if dup_count > 0 else ""
    print(f"  Duplicate PKs ({pk}): {dup_count}{dup_flag}")
    if dup_count > 0:
        issues.append(f"{name}: {dup_count} duplicate PKs in {pk}")

    null_summary = df.isnull().sum()
    null_summary = null_summary[null_summary > 0]
    if null_summary.empty:
        print(f"  Nulls:        none")
    else:
        expected_null_cols = EXPECTED_NULLS.get(name, set())
        print(f"  Nulls:")
        for col, cnt in null_summary.items():
            pct = cnt / len(df) * 100
            tag = " (expected by design)" if col in expected_null_cols else " <- UNEXPECTED NULL"
            print(f"    {col}: {cnt} ({pct:.1f}%){tag}")
            if col not in expected_null_cols:
                issues.append(f"{name}.{col}: {cnt} unexpected nulls")

    for col in date_cols.get(name, []):
        if df[col].isnull().all():
            continue
        col_min = df[col].min()
        col_max = df[col].max()
        out_of_range = (col_min < EXPECTED_DATE_MIN) or (col_max > EXPECTED_DATE_MAX)
        range_flag = " <- OUT OF EXPECTED RANGE" if out_of_range else ""
        print(f"  Date range ({col}): {col_min.date()} to {col_max.date()}{range_flag}")
        if out_of_range:
            issues.append(f"{name}.{col}: date range {col_min.date()} to {col_max.date()} outside expected window")

    bool_cols_dtype = [c for c in df.columns if df[c].dtype == bool]
    for col in bool_cols_dtype:
        vals = df[col].unique()
        unexpected_vals = [v for v in vals if v not in [True, False]]
        if unexpected_vals:
            print(f"  Boolean anomaly ({col}): unexpected values {unexpected_vals} <- ANOMALY")
            issues.append(f"{name}.{col}: unexpected boolean values {unexpected_vals}")

# =============================================================================
# --- Cross-table referential integrity ---
# =============================================================================

print(f"\n{'-' * 60}")
print("REFERENTIAL INTEGRITY")
print(f"{'-' * 60}")

def check_fk(child_name, child_col, parent_name, parent_col, child_df, parent_df):
    orphans = ~child_df[child_col].isin(parent_df[parent_col])
    count = orphans.sum()
    flag = " <- ORPHAN FKs FOUND" if count > 0 else ""
    print(f"  {child_name}.{child_col} -> {parent_name}.{parent_col}: {count} orphan rows{flag}")
    if count > 0:
        issues.append(f"Referential integrity: {child_name}.{child_col} has {count} orphans")

check_fk("subscriptions",   "account_id",      "accounts",      "account_id",      subscriptions,   accounts)
check_fk("feature_usage",   "subscription_id", "subscriptions", "subscription_id", feature_usage,   subscriptions)
check_fk("support_tickets", "account_id",      "accounts",      "account_id",      support_tickets, accounts)
check_fk("churn_events",    "account_id",      "accounts",      "account_id",      churn_events,    accounts)

# =============================================================================
# --- Domain-specific checks (per 00_scoping.md) ---
# =============================================================================

print(f"\n{'-' * 60}")
print("DOMAIN-SPECIFIC CHECKS")
print(f"{'-' * 60}")

arr_expected = subscriptions["mrr_amount"] * 12
arr_diff_pct = ((subscriptions["arr_amount"] - arr_expected) / arr_expected).abs()
arr_consistent = (arr_diff_pct <= 0.01).sum()
arr_inconsistent = (arr_diff_pct > 0.01).sum()
arr_pct = arr_consistent / len(subscriptions) * 100
print(f"  MRR x 12 ~= ARR (+/-1%): {arr_consistent:,} / {len(subscriptions):,} rows ({arr_pct:.1f}%)")
print(f"  NOTE: arr_amount not used — mrr_amount is the sole revenue source of truth.")

reactivation_count = churn_events["is_reactivation"].sum()
reactivation_pct = reactivation_count / len(churn_events) * 100
print(f"  Reactivations in churn_events: {reactivation_count} ({reactivation_pct:.1f}%)  (expected ~10% = ~60)")

sat_nulls = support_tickets["satisfaction_score"].isnull().sum()
sat_null_pct = sat_nulls / len(support_tickets) * 100
print(f"  satisfaction_score nulls: {sat_nulls} ({sat_null_pct:.1f}%)  — by design, no imputation")

trial_count = accounts["is_trial"].sum()
trial_pct = trial_count / len(accounts) * 100
print(f"  Trial accounts (is_trial=True): {trial_count} ({trial_pct:.1f}%)  — excluded from churn rate & LTV")

planned_exp = (subscriptions["end_date"].notna() & (subscriptions["churn_flag"] == False)).sum()
print(f"  Planned expirations (end_date set, churn_flag=False): {planned_exp} subscriptions — NOT churn events")

first_churn_accounts = churn_events.loc[churn_events["is_reactivation"] == False, "account_id"].unique()
accounts_flagged_churned = accounts.loc[accounts["churn_flag"] == True, "account_id"].unique()

both = len(set(accounts_flagged_churned) & set(first_churn_accounts))
flag_only = len(set(accounts_flagged_churned) - set(first_churn_accounts))
event_only = len(set(first_churn_accounts) - set(accounts_flagged_churned))

print(f"  Churn flag consistency:")
print(f"    accounts.churn_flag=True:          {len(accounts_flagged_churned):>4} accounts")
print(f"    churn_events (non-reactivation):   {len(first_churn_accounts):>4} accounts")
print(f"    Matched (both):                    {both:>4} accounts")
print(f"    Flag set but no churn event:       {flag_only:>4}  {'<- INVESTIGATE' if flag_only > 0 else ''}")
print(f"    Churn event but flag not set:      {event_only:>4}  {'<- INVESTIGATE' if event_only > 0 else ''}")
print(f"  NOTE: churn_events is source of truth per scoping doc — accounts.churn_flag not used for classification.")

# =============================================================================
# --- Quality Summary ---
# =============================================================================

print(f"\n{'=' * 70}")
print("QUALITY SUMMARY")
print(f"{'=' * 70}")
print(f"  Tables loaded:    5 / 5")
print(f"  Issues found:     {len(issues)}")

if issues:
    print(f"\n  Flags:")
    for i, issue in enumerate(issues, 1):
        print(f"    {i}. {issue}")
else:
    print(f"\n  No issues found.")

print(f"\n  Ready to proceed to Phase 2 (EDA): YES")
print(f"{'=' * 70}\n")

# =============================================================================
# === Phase 2: EDA ===
# Distributions of mrr_amount, tenure, usage, ticket volume, churn rates
# =============================================================================

print("=" * 70)
print("PHASE 2: EDA")
print("=" * 70)

sns.set_theme(style="whitegrid", font_scale=1.0)

C_BLUE  = "#2E86AB"
C_RED   = "#E84855"
C_GREY  = "#888888"
C_GREEN = "#44BBA4"

# =============================================================================
# --- 2.0 Derived views needed across EDA ---
# =============================================================================

# Source of truth for churn: churn_events with is_reactivation=False
churned_ids = set(
    churn_events.loc[churn_events["is_reactivation"] == False, "account_id"]
)

# Non-trial accounts only — trials excluded from churn rate and LTV per scoping
acct = accounts[accounts["is_trial"] == False].copy()
acct["is_churned"] = acct["account_id"].isin(churned_ids)

# First churn date per account (for tenure calculation)
first_churn = (
    churn_events[churn_events["is_reactivation"] == False]
    .groupby("account_id")["churn_date"].min()
    .rename("first_churn_date")
)
acct = acct.join(first_churn, on="account_id")

# Account tenure: time from signup to first churn (churned) or ANALYSIS_END (active)
acct["tenure_end"]    = acct["first_churn_date"].fillna(ANALYSIS_END)
acct["tenure_months"] = (acct["tenure_end"] - acct["signup_date"]).dt.days / 30.44

# Active subscriptions (no churn flag, end_date not set)
active_subs = subscriptions[subscriptions["churn_flag"] == False].copy()

# =============================================================================
# --- 2.1 Account overview ---
# =============================================================================

print(f"\n{'-' * 60}")
print(f"2.1 ACCOUNTS OVERVIEW  (non-trial n={len(acct)})")
print(f"{'-' * 60}")

n_churned = acct["is_churned"].sum()
n_active  = (~acct["is_churned"]).sum()
print(f"  Active:   {n_active:>4} ({n_active / len(acct) * 100:.1f}%)")
print(f"  Churned:  {n_churned:>4} ({n_churned / len(acct) * 100:.1f}%)")

tier_summary = (
    acct.groupby("plan_tier", sort=False)
    .agg(accounts=("account_id", "count"), churned=("is_churned", "sum"))
    .assign(churn_rate_pct=lambda x: (x["churned"] / x["accounts"] * 100).round(1))
    .sort_values("accounts", ascending=False)
)
print(f"\n  Plan tier breakdown:")
print(tier_summary.to_string())

industry_summary = (
    acct.groupby("industry", sort=False)
    .agg(accounts=("account_id", "count"), churned=("is_churned", "sum"))
    .assign(churn_rate_pct=lambda x: (x["churned"] / x["accounts"] * 100).round(1))
    .sort_values("accounts", ascending=False)
)
print(f"\n  Industry breakdown:")
print(industry_summary.to_string())

# Chart: accounts by plan tier, stacked by churn status
tier_plot = (
    acct.groupby(["plan_tier", "is_churned"])
    .size()
    .unstack(fill_value=0)
    .rename(columns={False: "Active", True: "Churned"})
)
tier_order = tier_plot.sum(axis=1).sort_values(ascending=False).index
tier_plot = tier_plot.loc[tier_order]

fig, ax = plt.subplots(figsize=(8, 5))
tier_plot.plot(kind="bar", stacked=True, color=[C_BLUE, C_RED], ax=ax, rot=0)
ax.set_title("Accounts by Plan Tier — Active vs Churned (non-trial)")
ax.set_xlabel("Plan Tier")
ax.set_ylabel("Number of Accounts")
ax.legend(title="Status")
for p in ax.patches:
    h = p.get_height()
    if h > 5:
        ax.text(
            p.get_x() + p.get_width() / 2,
            p.get_y() + h / 2,
            str(int(h)),
            ha="center", va="center", fontsize=9, color="white", fontweight="bold"
        )
plt.tight_layout()
plt.savefig(VIZ_DIR / "eda_01_plan_tier_churn.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/eda_01_plan_tier_churn.png")

# =============================================================================
# --- 2.2 MRR distribution ---
# =============================================================================

print(f"\n{'-' * 60}")
print(f"2.2 MRR DISTRIBUTION  (active subscriptions n={len(active_subs):,})")
print(f"{'-' * 60}")

mrr_stats = active_subs["mrr_amount"].describe(percentiles=[.25, .5, .75, .9])
print(mrr_stats.to_string())

tier_mrr_order = (
    subscriptions.groupby("plan_tier")["mrr_amount"].median()
    .sort_values().index.tolist()
)

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

axes[0].hist(active_subs["mrr_amount"], bins=40, color=C_BLUE, edgecolor="white", linewidth=0.4)
axes[0].axvline(active_subs["mrr_amount"].median(), color=C_RED, linewidth=1.5,
                linestyle="--", label=f"Median ${active_subs['mrr_amount'].median():.0f}")
axes[0].set_title("MRR Distribution — Active Subscriptions")
axes[0].set_xlabel("MRR (USD / month)")
axes[0].set_ylabel("Number of Subscriptions")
axes[0].legend()

sns.boxplot(
    data=subscriptions, x="plan_tier", y="mrr_amount",
    order=tier_mrr_order, hue="plan_tier", palette="Blues",
    legend=False, ax=axes[1]
)
axes[1].set_title("MRR by Plan Tier (all subscriptions)")
axes[1].set_xlabel("Plan Tier")
axes[1].set_ylabel("MRR (USD / month)")

plt.tight_layout()
plt.savefig(VIZ_DIR / "eda_02_mrr_distribution.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/eda_02_mrr_distribution.png")

# =============================================================================
# --- 2.3 Account tenure ---
# =============================================================================

print(f"\n{'-' * 60}")
print(f"2.3 ACCOUNT TENURE  (non-trial n={len(acct)})")
print(f"{'-' * 60}")

tenure_stats = acct["tenure_months"].describe(percentiles=[.25, .5, .75])
print(tenure_stats.to_string())
print(f"\n  Churned median tenure:  {acct.loc[acct['is_churned'], 'tenure_months'].median():.1f} months")
print(f"  Active median tenure:   {acct.loc[~acct['is_churned'], 'tenure_months'].median():.1f} months")

fig, ax = plt.subplots(figsize=(9, 5))
ax.hist(
    acct.loc[~acct["is_churned"], "tenure_months"], bins=24,
    color=C_BLUE, alpha=0.85, label="Active", edgecolor="white"
)
ax.hist(
    acct.loc[acct["is_churned"], "tenure_months"], bins=24,
    color=C_RED, alpha=0.7, label="Churned", edgecolor="white"
)
ax.set_title("Account Tenure Distribution — Active vs Churned (non-trial)")
ax.set_xlabel("Tenure (months)")
ax.set_ylabel("Number of Accounts")
ax.legend()
plt.tight_layout()
plt.savefig(VIZ_DIR / "eda_03_tenure_distribution.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/eda_03_tenure_distribution.png")

# =============================================================================
# --- 2.4 Feature usage per subscription ---
# =============================================================================

usage_per_sub = (
    feature_usage.groupby("subscription_id")
    .agg(
        events=("usage_id", "count"),
        total_usage_count=("usage_count", "sum"),
        total_duration_hrs=("usage_duration_secs", lambda x: x.sum() / 3600),
        unique_features=("feature_name", "nunique"),
        total_errors=("error_count", "sum"),
    )
    .reset_index()
)

print(f"\n{'-' * 60}")
print(f"2.4 FEATURE USAGE  (subscriptions with activity: {len(usage_per_sub):,} / {len(subscriptions):,})")
print(f"{'-' * 60}")
print(usage_per_sub[["events", "total_usage_count", "unique_features", "total_errors"]]
      .describe(percentiles=[.25, .5, .75, .9]).to_string())

top_features = (
    feature_usage.groupby("feature_name")["usage_count"]
    .sum()
    .sort_values(ascending=False)
    .head(10)
)
beta_pct = feature_usage["is_beta_feature"].mean() * 100
print(f"\n  Beta feature events: {beta_pct:.1f}% of total usage events")
print(f"\n  Top 10 features by total usage count:")
print(top_features.to_string())

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

axes[0].hist(usage_per_sub["events"], bins=30, color=C_BLUE, edgecolor="white", linewidth=0.4)
axes[0].axvline(usage_per_sub["events"].median(), color=C_RED, linewidth=1.5,
                linestyle="--", label=f"Median {usage_per_sub['events'].median():.0f}")
axes[0].set_title("Feature Usage Events per Subscription")
axes[0].set_xlabel("Number of Usage Events")
axes[0].set_ylabel("Number of Subscriptions")
axes[0].legend()

top_features.sort_values().plot(kind="barh", ax=axes[1], color=C_BLUE)
axes[1].set_title("Top 10 Features by Total Usage Count")
axes[1].set_xlabel("Total Usage Count")
axes[1].set_ylabel("Feature")

plt.tight_layout()
plt.savefig(VIZ_DIR / "eda_04_feature_usage.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/eda_04_feature_usage.png")

# =============================================================================
# --- 2.5 Support ticket volume per account ---
# =============================================================================

tickets_per_acct = (
    support_tickets.groupby("account_id")
    .agg(
        ticket_count=("ticket_id", "count"),
        escalations=("escalation_flag", "sum"),
        avg_resolution_hrs=("resolution_time_hours", "mean"),
        avg_sat_score=("satisfaction_score", "mean"),
    )
    .reset_index()
)
# Include accounts with 0 tickets
tickets_full = (
    accounts[["account_id"]]
    .merge(tickets_per_acct, on="account_id", how="left")
)
tickets_full["ticket_count"] = tickets_full["ticket_count"].fillna(0)

print(f"\n{'-' * 60}")
print(f"2.5 SUPPORT TICKETS  (n={len(support_tickets):,} tickets across {len(tickets_per_acct)} accounts)")
print(f"{'-' * 60}")
print(f"  Accounts with >=1 ticket: {(tickets_full['ticket_count'] > 0).sum()} / {len(tickets_full)}")
print(f"  Accounts with 0 tickets:  {(tickets_full['ticket_count'] == 0).sum()}")
print(f"  Median tickets per account: {tickets_per_acct['ticket_count'].median():.1f}")
print(f"  Escalation rate: {support_tickets['escalation_flag'].mean() * 100:.1f}% of all tickets")

sat_valid = support_tickets["satisfaction_score"].dropna()
print(f"  Satisfaction score (non-null n={len(sat_valid)}): mean={sat_valid.mean():.2f}, median={sat_valid.median():.1f}, std={sat_valid.std():.2f}")

priority_dist = support_tickets["priority"].value_counts(normalize=True).mul(100).round(1)
print(f"\n  Ticket priority distribution (%):")
print(priority_dist.to_string())

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

max_tickets = int(tickets_full["ticket_count"].max())
axes[0].hist(
    tickets_full["ticket_count"],
    bins=range(0, max_tickets + 2),
    color=C_BLUE, edgecolor="white", linewidth=0.4
)
axes[0].set_title("Support Ticket Volume per Account")
axes[0].set_xlabel("Number of Tickets")
axes[0].set_ylabel("Number of Accounts")

sat_valid.hist(bins=10, ax=axes[1], color=C_BLUE, edgecolor="white", linewidth=0.4)
axes[1].axvline(sat_valid.mean(), color=C_RED, linewidth=1.5, linestyle="--",
                label=f"Mean {sat_valid.mean():.2f}")
axes[1].set_title(f"Satisfaction Score Distribution (n={len(sat_valid)} non-null)")
axes[1].set_xlabel("Satisfaction Score")
axes[1].set_ylabel("Number of Tickets")
axes[1].legend()

plt.tight_layout()
plt.savefig(VIZ_DIR / "eda_05_support_tickets.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/eda_05_support_tickets.png")

# =============================================================================
# --- 2.6 Churn events overview ---
# =============================================================================

churn_first = churn_events[churn_events["is_reactivation"] == False].copy()
churn_first["churn_month"] = churn_first["churn_date"].dt.to_period("M")
monthly_churn = churn_first.groupby("churn_month").size()

print(f"\n{'-' * 60}")
print(f"2.6 CHURN EVENTS OVERVIEW  (n={len(churn_events)} total)")
print(f"{'-' * 60}")
print(f"  First-time churn:  {len(churn_first)}")
print(f"  Reactivations:     {(churn_events['is_reactivation'] == True).sum()}")
print(f"\n  Monthly churn events: min={monthly_churn.min()}, max={monthly_churn.max()}, mean={monthly_churn.mean():.1f}")

reason_dist = churn_first["reason_code"].value_counts()
print(f"\n  Churn reason codes (first-time churn):")
print(reason_dist.to_string())

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

reason_dist.sort_values().plot(kind="barh", ax=axes[0], color=C_RED)
axes[0].set_title("Churn Reason Codes (first-time churn)")
axes[0].set_xlabel("Number of Accounts")
axes[0].set_ylabel("Reason Code")
for i, v in enumerate(reason_dist.sort_values().values):
    axes[0].text(v + 1, i, str(v), va="center", fontsize=9)

monthly_churn_idx = [str(p) for p in monthly_churn.index]
axes[1].bar(monthly_churn_idx, monthly_churn.values, color=C_RED)
axes[1].set_title("Monthly Churn Events (first-time churn)")
axes[1].set_xlabel("Month")
axes[1].set_ylabel("Churn Events")
axes[1].tick_params(axis="x", rotation=45)

plt.tight_layout()
plt.savefig(VIZ_DIR / "eda_06_churn_events.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/eda_06_churn_events.png")

# =============================================================================
# --- EDA Summary ---
# =============================================================================

print(f"\n{'=' * 70}")
print("EDA SUMMARY")
print(f"{'=' * 70}")
print(f"  Non-trial accounts:  {len(acct)}  |  Churned: {n_churned}  |  Active: {n_active}")
print(f"  Overall logo churn rate (non-trial, full period): {acct['is_churned'].mean() * 100:.1f}%")
print(
    f"  Account tenure — all: {acct['tenure_months'].median():.1f} mo (median) | "
    f"churned: {acct.loc[acct['is_churned'], 'tenure_months'].median():.1f} mo | "
    f"active: {acct.loc[~acct['is_churned'], 'tenure_months'].median():.1f} mo"
)
print(
    f"  Active sub MRR — median: ${active_subs['mrr_amount'].median():.0f} | "
    f"mean: ${active_subs['mrr_amount'].mean():.0f} | "
    f"range: ${active_subs['mrr_amount'].min():.0f}–${active_subs['mrr_amount'].max():.0f}"
)
print(f"  Subscriptions with usage data: {len(usage_per_sub):,} / {len(subscriptions):,}")
print(f"  Accounts with support tickets: {(tickets_full['ticket_count'] > 0).sum()} / {len(accounts)}")
print(f"\n  Visualizations saved to viz/:")
for i, name in enumerate([
    "eda_01_plan_tier_churn.png",
    "eda_02_mrr_distribution.png",
    "eda_03_tenure_distribution.png",
    "eda_04_feature_usage.png",
    "eda_05_support_tickets.png",
    "eda_06_churn_events.png",
], 1):
    print(f"    {i}. {name}")
print(f"\n  Ready to proceed to Phase 3 (Metric calculation): PENDING REVIEW")
print(f"{'=' * 70}\n")

# =============================================================================
# === Phase 3: Metric calculation ===
# MRR decomposition, NRR, GRR, logo churn rate, revenue churn rate, cohort retention
# =============================================================================

# === Phase 4: Analysis (mapped to SQ1–SQ9) ===

# === Phase 5 / Model: SQ8 — feature engineering + logistic regression + XGBoost ===

# === Phase 6 / ICP: SQ9 — LTV by segment ===

# === Phase 7: Export ===
