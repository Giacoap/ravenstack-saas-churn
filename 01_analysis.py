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

# Resolve paths relative to this script's location so the script works
# both from the project root and from a git worktree subdirectory.
SCRIPT_DIR = Path(__file__).resolve().parent

# Walk up from SCRIPT_DIR to find the data/ folder (handles worktree layout)
DATA_DIR = next(
    (p / "data" for p in [SCRIPT_DIR, *SCRIPT_DIR.parents] if (p / "data").exists()),
    SCRIPT_DIR / "data",  # fallback — will produce a clear FileNotFoundError
)

VIZ_DIR = SCRIPT_DIR / "viz"
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

print("=" * 70)
print("PHASE 3: METRIC CALCULATION")
print("=" * 70)

MONTHS = pd.period_range(start="2023-01", end="2024-12", freq="M")

# Non-trial subscriptions only (trials excluded from all revenue metrics per scoping doc)
subs_paid = subscriptions[subscriptions["is_trial"] == False].copy()
subs_paid["start_month"] = subs_paid["start_date"].dt.to_period("M")
subs_paid["end_month"]   = subs_paid["end_date"].dt.to_period("M")

# =============================================================================
# --- 3.0 Monthly MRR panel ---
# One row per (subscription, month) for every month the subscription was active.
# "Active" = start_date <= month_end AND (end_date is null OR end_date >= month_start).
# This panel is the single source of truth for all revenue metrics below.
# =============================================================================

panels = []
for m in MONTHS:
    m_ts  = m.to_timestamp()
    m_end = (m + 1).to_timestamp() - pd.Timedelta(seconds=1)
    mask  = (subs_paid["start_date"] <= m_end) & (
        subs_paid["end_date"].isna() | (subs_paid["end_date"] >= m_ts)
    )
    chunk = subs_paid.loc[mask, [
        "subscription_id", "account_id", "mrr_amount", "plan_tier",
        "churn_flag", "upgrade_flag", "downgrade_flag",
    ]].copy()
    chunk["month"] = m
    panels.append(chunk)

mrr_panel = pd.concat(panels, ignore_index=True)

# Account-level MRR by month (sums concurrent subscriptions per account)
acct_monthly_mrr = (
    mrr_panel
    .groupby(["account_id", "month"])["mrr_amount"]
    .sum()
    .reset_index()
    .rename(columns={"mrr_amount": "mrr"})
)

# =============================================================================
# --- 3.1 Total MRR trend ---
# =============================================================================

monthly_totals = (
    mrr_panel.groupby("month")["mrr_amount"]
    .sum()
    .reset_index()
    .rename(columns={"mrr_amount": "total_mrr"})
)

mrr_start = monthly_totals.iloc[0]["total_mrr"]
mrr_end   = monthly_totals.iloc[-1]["total_mrr"]
mrr_growth_pct = (mrr_end / mrr_start - 1) * 100

print(f"\n{'-' * 60}")
print("3.1 TOTAL MRR TREND")
print(f"{'-' * 60}")
print(monthly_totals.to_string(index=False))
print(f"\n  Start (Jan 2023): ${mrr_start:>12,.0f}")
print(f"  End   (Dec 2024): ${mrr_end:>12,.0f}")
print(f"  Change over period: {mrr_growth_pct:+.1f}%")

# =============================================================================
# --- 3.2 MRR decomposition ---
# Movement categories per subscription when it starts:
#   new        — first paid sub for this account (no prior paid sub)
#   expansion  — subsequent sub, upgrade_flag=True, positive MRR delta
#   contraction— subsequent sub, downgrade_flag=True, negative MRR delta
#   churned    — subs ending this month with churn_flag=True (tracked separately)
# Limitation: delta is vs the immediately preceding subscription for the account,
# which may miss same-month transitions. Documented as approximation.
# =============================================================================

subs_sorted = subs_paid.sort_values(["account_id", "start_date"]).copy()
subs_sorted["prev_mrr"]    = subs_sorted.groupby("account_id")["mrr_amount"].shift(1)
subs_sorted["is_first_sub"] = subs_sorted["prev_mrr"].isna()
subs_sorted["mrr_delta"]   = subs_sorted["mrr_amount"] - subs_sorted["prev_mrr"].fillna(0)

new_mrr_m = (
    subs_sorted[subs_sorted["is_first_sub"]]
    .groupby("start_month")["mrr_amount"].sum()
    .rename("new_mrr")
)
expansion_m = (
    subs_sorted[
        ~subs_sorted["is_first_sub"]
        & subs_sorted["upgrade_flag"]
        & (subs_sorted["mrr_delta"] > 0)
    ]
    .groupby("start_month")["mrr_delta"].sum()
    .rename("expansion_mrr")
)
contraction_m = (
    subs_sorted[
        ~subs_sorted["is_first_sub"]
        & subs_sorted["downgrade_flag"]
        & (subs_sorted["mrr_delta"] < 0)
    ]
    .groupby("start_month")["mrr_delta"].sum()
    .abs()
    .rename("contraction_mrr")
)
churned_mrr_m = (
    subs_paid[subs_paid["churn_flag"] == True]
    .groupby("end_month")["mrr_amount"].sum()
    .rename("churned_mrr")
)

decomp = (
    monthly_totals.set_index("month")
    .join(new_mrr_m, how="left")
    .join(expansion_m, how="left")
    .join(contraction_m, how="left")
    .join(churned_mrr_m, how="left")
    .fillna(0)
    .reset_index()
)
decomp["net_new_mrr"] = (
    decomp["new_mrr"] + decomp["expansion_mrr"]
    - decomp["contraction_mrr"] - decomp["churned_mrr"]
)

print(f"\n{'-' * 60}")
print("3.2 MRR DECOMPOSITION")
print(f"{'-' * 60}")
decomp_display = decomp.copy()
for col in ["total_mrr", "new_mrr", "expansion_mrr", "contraction_mrr", "churned_mrr", "net_new_mrr"]:
    decomp_display[col] = decomp_display[col].map(lambda x: f"${x:,.0f}")
print(decomp_display.to_string(index=False))

print(f"\n  24-month totals:")
print(f"    New MRR:         ${decomp['new_mrr'].sum():>12,.0f}")
print(f"    Expansion MRR:   ${decomp['expansion_mrr'].sum():>12,.0f}")
print(f"    Contraction MRR: ${decomp['contraction_mrr'].sum():>12,.0f}")
print(f"    Churned MRR:     ${decomp['churned_mrr'].sum():>12,.0f}")
print(f"    Net MRR change:  ${decomp['net_new_mrr'].sum():>12,.0f}")

# Chart: MRR trend + waterfall components
fig, axes = plt.subplots(2, 1, figsize=(13, 9))
x            = range(len(MONTHS))
month_labels = [str(m) for m in decomp["month"]]

axes[0].plot(x, decomp["total_mrr"] / 1_000, color=C_BLUE, linewidth=2, marker="o", markersize=3)
axes[0].fill_between(x, decomp["total_mrr"] / 1_000, alpha=0.12, color=C_BLUE)
axes[0].set_title("Total Monthly MRR — Non-Trial Subscriptions", fontsize=12)
axes[0].set_ylabel("MRR ($K)")
axes[0].set_xticks(x)
axes[0].set_xticklabels(month_labels, rotation=45, ha="right", fontsize=8)

axes[1].bar(x, decomp["new_mrr"] / 1_000, label="New MRR", color=C_GREEN)
axes[1].bar(x, decomp["expansion_mrr"] / 1_000,
            bottom=decomp["new_mrr"] / 1_000, label="Expansion MRR", color=C_BLUE)
axes[1].bar(x, -decomp["contraction_mrr"] / 1_000, label="Contraction MRR", color=C_GREY)
axes[1].bar(x, -decomp["churned_mrr"] / 1_000,
            bottom=-decomp["contraction_mrr"] / 1_000, label="Churned MRR", color=C_RED)
axes[1].axhline(0, color="black", linewidth=0.8)
axes[1].set_title("Monthly MRR Movements", fontsize=12)
axes[1].set_ylabel("MRR ($K)")
axes[1].set_xticks(x)
axes[1].set_xticklabels(month_labels, rotation=45, ha="right", fontsize=8)
axes[1].legend(loc="upper right", fontsize=9)

plt.tight_layout()
plt.savefig(VIZ_DIR / "metrics_01_mrr_trend.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/metrics_01_mrr_trend.png")

# =============================================================================
# --- 3.3 Monthly logo churn rate ---
# Denominator: non-trial accounts active at START of month M
#   (signed up before M AND not yet churned as of M start)
# Numerator: non-reactivation churn events with churn_date in M
# =============================================================================

print(f"\n{'-' * 60}")
print("3.3 MONTHLY LOGO CHURN RATE")
print(f"{'-' * 60}")

churn_by_month = (
    churn_events[churn_events["is_reactivation"] == False]
    .assign(churn_month=lambda df: df["churn_date"].dt.to_period("M"))
    .groupby("churn_month")
    .size()
    .rename("churned_accounts")
)

logo_churn_records = []
for m in MONTHS:
    m_ts = m.to_timestamp()
    active_at_start = acct[
        (acct["signup_date"] < m_ts)
        & (acct["first_churn_date"].isna() | (acct["first_churn_date"] >= m_ts))
    ]
    n_active  = len(active_at_start)
    n_churned = int(churn_by_month.get(m, 0))
    logo_churn_records.append({
        "month":              m,
        "active_at_start":    n_active,
        "churned":            n_churned,
        "logo_churn_rate_pct": round(n_churned / n_active * 100, 2) if n_active > 0 else np.nan,
    })

logo_churn_df = pd.DataFrame(logo_churn_records)
print(logo_churn_df.to_string(index=False))

avg_logo_churn = logo_churn_df["logo_churn_rate_pct"].mean()
ann_logo_churn = (1 - (1 - avg_logo_churn / 100) ** 12) * 100
print(f"\n  Average monthly logo churn rate: {avg_logo_churn:.2f}%")
print(f"  Implied annualized rate:         {ann_logo_churn:.1f}%")
print(f"  Min: {logo_churn_df['logo_churn_rate_pct'].min():.2f}%  "
      f"Max: {logo_churn_df['logo_churn_rate_pct'].max():.2f}%")

# Dec 2024 shows 68.8% monthly churn (106/154 accounts) — end_date cluster on
# Dec 26-31, 2024 confirms this is a planned pilot shutdown, not organic attrition.
# Operational metric = ex-Dec figure; with-Dec disclosed for transparency.
logo_excl = logo_churn_df[logo_churn_df["month"] != pd.Period("2024-12", "M")]
avg_logo_excl    = logo_excl["logo_churn_rate_pct"].mean()
ann_logo_excl    = (1 - (1 - avg_logo_excl / 100) ** 12) * 100
print(f"\n  Excluding Dec 2024 (end-of-pilot wind-down):")
print(f"  Avg monthly logo churn (ex-Dec):  {avg_logo_excl:.2f}%")
print(f"  Implied annualized (ex-Dec):      {ann_logo_excl:.1f}%")

# =============================================================================
# --- 3.4 Revenue churn rate ---
# Denominator: total active MRR at start of month M (= total_mrr in panel,
#   which includes subscriptions active at any point during M, capturing
#   subscriptions that churn during M in the denominator)
# Numerator: MRR of subscriptions that ended with churn_flag=True in M
# =============================================================================

print(f"\n{'-' * 60}")
print("3.4 REVENUE CHURN RATE")
print(f"{'-' * 60}")

churned_mrr_lookup = (
    subs_paid[subs_paid["churn_flag"] == True]
    .groupby("end_month")["mrr_amount"]
    .sum()
    .rename("churned_mrr_usd")
)

rev_churn_records = []
for _, row in decomp.iterrows():
    m              = row["month"]
    starting_mrr   = row["total_mrr"]
    churned_mrr_v  = float(churned_mrr_lookup.get(m, 0))
    rev_churn_records.append({
        "month":             m,
        "starting_mrr":      starting_mrr,
        "churned_mrr_usd":   churned_mrr_v,
        "rev_churn_rate_pct": round(churned_mrr_v / starting_mrr * 100, 2)
        if starting_mrr > 0 else np.nan,
    })

rev_churn_df = pd.DataFrame(rev_churn_records)
print(rev_churn_df.to_string(index=False))

avg_rev_churn = rev_churn_df["rev_churn_rate_pct"].mean()
print(f"\n  Average monthly revenue churn rate: {avg_rev_churn:.2f}%")

# Chart: logo + revenue churn rates
fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)

axes[0].bar(x, logo_churn_df["logo_churn_rate_pct"], color=C_RED, alpha=0.8)
axes[0].axhline(avg_logo_churn, color="black", linewidth=1.2, linestyle="--",
                label=f"Avg {avg_logo_churn:.1f}%")
axes[0].set_title("Monthly Logo Churn Rate (non-trial accounts)", fontsize=11)
axes[0].set_ylabel("Logo Churn Rate (%)")
axes[0].legend()

axes[1].bar(x, rev_churn_df["rev_churn_rate_pct"], color=C_RED, alpha=0.6)
axes[1].axhline(avg_rev_churn, color="black", linewidth=1.2, linestyle="--",
                label=f"Avg {avg_rev_churn:.1f}%")
axes[1].set_title("Monthly Revenue Churn Rate", fontsize=11)
axes[1].set_ylabel("Revenue Churn Rate (%)")
axes[1].set_xticks(x)
axes[1].set_xticklabels(month_labels, rotation=45, ha="right", fontsize=8)
axes[1].legend()

plt.tight_layout()
plt.savefig(VIZ_DIR / "metrics_02_churn_rates.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/metrics_02_churn_rates.png")

# =============================================================================
# --- 3.4b Revised revenue churn rate (account-level methodology) ---
# Phase 1 finding: subscription churn_flag is incomplete — only 110 accounts
# flagged vs 339 with churn_events. Original 0.90% avg was understated.
# Revised method: for each churn event (non-reactivation), join to the
# churned account's total active subscription MRR at the churn month from the
# monthly panel. This captures the full revenue impact per churned account.
# =============================================================================

rev_churn_acct_mrr = (
    churn_events[churn_events["is_reactivation"] == False]
    .assign(churn_month=lambda df: df["churn_date"].dt.to_period("M"))
    [["account_id", "churn_month"]]
    .merge(
        acct_monthly_mrr.rename(columns={"month": "churn_month"}),
        on=["account_id", "churn_month"],
        how="left",
    )
    .fillna({"mrr": 0})
    .groupby("churn_month")["mrr"]
    .sum()
    .rename("churned_acct_mrr")
)

rev_churn_rev_records = []
for _, row in decomp.iterrows():
    m         = row["month"]
    start_mrr = row["total_mrr"]
    c_mrr     = float(rev_churn_acct_mrr.get(m, 0))
    rev_churn_rev_records.append({
        "month":             m,
        "starting_mrr":      int(start_mrr),
        "churned_mrr_acct":  int(c_mrr),
        "rev_churn_rev_pct": round(c_mrr / start_mrr * 100, 2) if start_mrr > 0 else np.nan,
    })

rev_churn_rev_df  = pd.DataFrame(rev_churn_rev_records)
avg_rev_churn_rev = rev_churn_rev_df["rev_churn_rev_pct"].mean()
rev_excl          = rev_churn_rev_df[rev_churn_rev_df["month"] != pd.Period("2024-12", "M")]
avg_rev_churn_rev_excl = rev_excl["rev_churn_rev_pct"].mean()

print(f"\n{'-' * 60}")
print("3.4b REVISED REVENUE CHURN RATE (account-level, from churn_events)")
print(f"{'-' * 60}")
print(rev_churn_rev_df[["month", "starting_mrr", "churned_mrr_acct", "rev_churn_rev_pct"]]
      .to_string(index=False))
print(f"\n  Avg monthly rev churn (with Dec 2024): {avg_rev_churn_rev:.2f}%")
print(f"  Avg monthly rev churn (excl. Dec):     {avg_rev_churn_rev_excl:.2f}%")
print(f"  Original sub-level avg: 0.90%. Revised captures full account MRR impact.")

# =============================================================================
# --- 3.5 NRR and GRR (12-month rolling) ---
# For each starting month M in 2023 (so that M+12 falls within the dataset):
#   NRR(M) = sum(account MRR at M+12) / sum(account MRR at M) × 100
#   GRR(M) = NRR excluding expansion — each account's M+12 MRR capped at M MRR
# Accounts that churned by M+12 contribute 0 to the numerator.
# =============================================================================

print(f"\n{'-' * 60}")
print("3.5 NRR AND GRR (12-month rolling)")
print(f"  NRR DEPRECATED — accounts average 8-10 concurrent active subscriptions,")
print(f"  inflating NRR to 335% median (subscription accumulation, not expansion).")
print(f"  GRR (97.8%) is the reliable retention metric. NRR limited to limitations.")
print(f"{'-' * 60}")

nrr_records = []
for m in pd.period_range(start="2023-01", end="2023-12", freq="M"):
    m12 = m + 12

    accts_m0  = (acct_monthly_mrr[acct_monthly_mrr["month"] == m]
                 [["account_id", "mrr"]].rename(columns={"mrr": "mrr_m0"}))
    accts_m12 = (acct_monthly_mrr[acct_monthly_mrr["month"] == m12]
                 [["account_id", "mrr"]].rename(columns={"mrr": "mrr_m12"}))

    merged = accts_m0.merge(accts_m12, on="account_id", how="left")
    merged["mrr_m12"] = merged["mrr_m12"].fillna(0)

    sum_m0   = merged["mrr_m0"].sum()
    sum_m12  = merged["mrr_m12"].sum()
    # GRR: cap each account's M+12 MRR at M0 MRR (no expansion credit)
    sum_grr  = merged[["mrr_m0", "mrr_m12"]].min(axis=1).sum()

    nrr_records.append({
        "cohort_month": m,
        "n_accounts":   len(accts_m0),
        "starting_mrr": int(sum_m0),
        "ending_mrr":   int(sum_m12),
        "nrr_pct":      round(sum_m12 / sum_m0 * 100, 1) if sum_m0 > 0 else np.nan,
        "grr_pct":      round(sum_grr / sum_m0 * 100, 1) if sum_m0 > 0 else np.nan,
    })

nrr_df = pd.DataFrame(nrr_records)
print(nrr_df.to_string(index=False))

print(f"\n  Median 12-month NRR: {nrr_df['nrr_pct'].median():.1f}%")
print(f"  Median 12-month GRR: {nrr_df['grr_pct'].median():.1f}%")
print(f"  Average NRR:         {nrr_df['nrr_pct'].mean():.1f}%")
print(f"  Average GRR:         {nrr_df['grr_pct'].mean():.1f}%")
print(f"  NOTE: GRR = NRR excluding expansion (each account capped at starting MRR).")
print(f"  BENCHMARK: healthy SaaS NRR ~100-120%, GRR ~80-90%.")

# =============================================================================
# --- 3.6 Cohort retention ---
# Signup cohort = month of accounts.signup_date (non-trial)
# Retention at offset M_n = % of cohort still active n months after signup
# "Active" = no first-time churn event recorded yet at check_date
# Milestones: M0, M1, M3, M6, M12, M18, M24
#
# ** EDA finding: churned median tenure = 2.7 months vs active median 10.0 months **
# ** Early attrition should be clearly visible at M1 and M3                       **
# =============================================================================

print(f"\n{'-' * 60}")
print("3.6 COHORT RETENTION")
print(f"  EDA signal: churned median tenure = 2.7 mo vs active 10.0 mo")
print(f"  Watch M1 and M3 for early-churn concentration")
print(f"{'-' * 60}")

MILESTONES = [0, 1, 3, 6, 12, 18, 24]

acct_cohort = acct.copy()
acct_cohort["cohort"] = acct_cohort["signup_date"].dt.to_period("M")

retention_rows = []
for cohort_period, group in acct_cohort.groupby("cohort"):
    row = {"cohort": cohort_period, "n": len(group)}
    for offset in MILESTONES:
        check_dates = group["signup_date"] + pd.DateOffset(months=offset)
        valid    = check_dates <= ANALYSIS_END
        active   = group["first_churn_date"].isna() | (group["first_churn_date"] > check_dates)
        n_valid  = valid.sum()
        n_kept   = (active & valid).sum()
        row[f"M{offset}_n"]   = int(n_kept)
        row[f"M{offset}_pct"] = round(n_kept / n_valid * 100, 1) if n_valid > 0 else np.nan
    retention_rows.append(row)

cohort_ret = pd.DataFrame(retention_rows)

pct_cols = ["cohort", "n"] + [f"M{m}_pct" for m in MILESTONES]
print("\n  Cohort retention (%)  [blank = insufficient observation window]:")
print(cohort_ret[pct_cols].to_string(index=False))

# Weighted-average aggregate retention curve
agg_retention = {}
for offset in MILESTONES:
    col  = f"M{offset}_pct"
    valid_rows = cohort_ret[cohort_ret[col].notna()]
    if len(valid_rows) > 0:
        agg_retention[f"M{offset}"] = round(
            (valid_rows[col] * valid_rows["n"]).sum() / valid_rows["n"].sum(), 1
        )
    else:
        agg_retention[f"M{offset}"] = np.nan

print(f"\n  Aggregate retention curve (weighted avg, all cohorts):")
for k, v in agg_retention.items():
    bar_len = int(v / 5) if pd.notna(v) else 0
    display = f"{v}%  {'|' * bar_len}" if pd.notna(v) else "N/A"
    print(f"    {k:>4}: {display}")

# Chart: cohort retention heatmap
pct_matrix = cohort_ret.set_index("cohort")[[f"M{m}_pct" for m in MILESTONES]]
pct_matrix.columns = [f"M{m}" for m in MILESTONES]

fig, ax = plt.subplots(figsize=(10, 12))
sns.heatmap(
    pct_matrix,
    annot=True, fmt=".0f", cmap="RdYlGn",
    vmin=0, vmax=100,
    linewidths=0.5, linecolor="white",
    ax=ax,
    cbar_kws={"label": "Retention (%)"},
)
ax.set_title(
    "Cohort Retention (%) by Signup Month\n"
    "Blank = insufficient observation window  |  Early churn visible at M1 & M3",
    fontsize=11,
)
ax.set_xlabel("Months Since Signup")
ax.set_ylabel("Signup Cohort")
plt.tight_layout()
plt.savefig(VIZ_DIR / "metrics_03_cohort_retention.png", dpi=150)
plt.close()
print(f"\n  Chart saved: viz/metrics_03_cohort_retention.png")

# =============================================================================
# --- Phase 3 summary ---
# =============================================================================

print(f"\n{'=' * 70}")
print("PHASE 3 SUMMARY — METRICS")
print(f"{'=' * 70}")
print(f"  MRR Jan 2023:                ${mrr_start:>12,.0f}")
print(f"  MRR Dec 2024:                ${mrr_end:>12,.0f}")
print(f"  MRR change over period:      {mrr_growth_pct:>+.1f}%")
print()
print(f"  Avg monthly logo churn (incl. Dec 2024):  {avg_logo_churn:>8.2f}%  [ann. {ann_logo_churn:.1f}%]")
print(f"  Avg monthly logo churn (ex.  Dec 2024):   {avg_logo_excl:>8.2f}%  [ann. {ann_logo_excl:.1f}%]  <- operational metric")
print(f"  Note: Dec 2024 excluded from ex-Dec figure (pilot shutdown, not organic attrition)")
print()
print(f"  Avg monthly rev churn — original (subs churn_flag):  {avg_rev_churn:>6.2f}%  [understated]")
print(f"  Avg monthly rev churn — revised  (churn_events MRR): {avg_rev_churn_rev:>6.2f}%  <- methodology corrected")
print(f"  Avg monthly rev churn — revised, ex-Dec 2024:        {avg_rev_churn_rev_excl:>6.2f}%  <- operational metric")
print()
print(f"  NRR (median): DEPRECATED — concurrent subscription model inflates to ~335%")
print(f"  12-month GRR (median):       {nrr_df['grr_pct'].median():>8.1f}%  (reliable metric; benchmark: 80-90%)")
print()
print(f"  Aggregate cohort retention:")
for k, v in agg_retention.items():
    display = f"{v}%" if pd.notna(v) else "N/A"
    print(f"    {k:>4}: {display}")
print()
print(f"  Charts saved: metrics_01 through metrics_03 in viz/")
print(f"\n  Ready to proceed to Phase 4 (sub-question analysis): PENDING REVIEW")
print(f"{'=' * 70}\n")

# =============================================================================
# === Phase 4: Analysis (SQ1–SQ7) ===
# =============================================================================

print("\n" + "=" * 70)
print("PHASE 4 — SUB-QUESTION ANALYSIS (SQ1–SQ7)")
print("=" * 70)

# -----------------------------------------------------------------------------
# SQ1: How has MRR evolved over the pilot period, and what plan tiers drive it?
# -----------------------------------------------------------------------------
print("\n--- SQ1: MRR trend by plan tier ---")

# Build monthly MRR by plan tier
# mrr_panel already carries plan_tier (pulled from subs_paid at build time)
tier_monthly = (
    mrr_panel
    .groupby(["month", "plan_tier"])["mrr_amount"]
    .sum()
    .reset_index()
)

# Exclude Dec 2024 (pilot shutdown) from trend analysis per scoping decision
# month column is Period[M] — compare with Period, not Timestamp
tier_monthly_excl = tier_monthly[tier_monthly["month"] < pd.Period("2024-12", "M")]

# Pivot for stacked area chart
tier_pivot = tier_monthly_excl.pivot(index="month", columns="plan_tier", values="mrr_amount").fillna(0)

fig, axes = plt.subplots(2, 1, figsize=(13, 10))

# Top: stacked area by tier
# Actual tier values in data: Enterprise, Pro, Basic (confirmed from subscriptions)
tier_colors = {"Enterprise": "#1a3a5c", "Pro": "#2878b5", "Basic": "#9ecae1"}
tier_order = [t for t in ["Enterprise", "Pro", "Basic"] if t in tier_pivot.columns]
tier_pivot[tier_order].plot(
    kind="area", stacked=True, ax=axes[0],
    color=[tier_colors.get(t, "#cccccc") for t in tier_order], alpha=0.85
)
axes[0].set_title("Monthly MRR by Plan Tier (Jan 2023 – Nov 2024, ex-Dec 2024 pilot shutdown)", fontsize=13)
axes[0].set_xlabel("")
axes[0].set_ylabel("MRR ($)")
axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
axes[0].legend(title="Plan Tier", loc="upper left")

# Bottom: total MRR line (ex-Dec) with annotation of growth direction
monthly_totals_excl = tier_monthly_excl.groupby("month")["mrr_amount"].sum()
# Convert Period index to Timestamp for matplotlib compatibility
_tot_idx = monthly_totals_excl.index.to_timestamp()
axes[1].plot(_tot_idx, monthly_totals_excl.values, color="#1a3a5c", linewidth=2)
axes[1].fill_between(_tot_idx, monthly_totals_excl.values, alpha=0.15, color="#2878b5")
axes[1].set_title("Total MRR Trend (ex-Dec 2024)", fontsize=12)
axes[1].set_xlabel("Month")
axes[1].set_ylabel("Total MRR ($)")
axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))

plt.tight_layout()
plt.savefig(VIZ_DIR / "sq1_mrr_by_tier.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Chart saved: sq1_mrr_by_tier.png")

# SQ1 key metrics
mrr_jan23 = monthly_totals_excl.iloc[0]
mrr_nov24 = monthly_totals_excl.iloc[-1]
mrr_peak = monthly_totals_excl.max()
mrr_peak_month = monthly_totals_excl.idxmax().strftime("%b %Y")

# Tier share at end of period
tier_end = tier_pivot.iloc[-1]
tier_share_end = (tier_end / tier_end.sum() * 100).round(1)

print(f"  MRR Jan 2023:    ${mrr_jan23:>10,.0f}")
print(f"  MRR Nov 2024:    ${mrr_nov24:>10,.0f}")
print(f"  Peak MRR:        ${mrr_peak:>10,.0f}  ({mrr_peak_month})")
print(f"  Tier share at end of period (ex-Dec):")
for tier in tier_order:
    if tier in tier_share_end.index:
        print(f"    {tier:<14}: {tier_share_end[tier]:.1f}%")

# -----------------------------------------------------------------------------
# SQ2: Which cohorts retain best and worst?
# -----------------------------------------------------------------------------
print("\n--- SQ2: Cohort retention analysis ---")

# cohort_ret already computed in Phase 3
# Identify best and worst cohort by M6 retention (enough data for most cohorts)
if "M6" in cohort_ret.columns:
    m6_ret = cohort_ret["M6"].dropna()
    if len(m6_ret) >= 2:
        best_cohort_m6 = m6_ret.idxmax()
        worst_cohort_m6 = m6_ret.idxmin()
        print(f"  Best M6 retention cohort:   {best_cohort_m6.strftime('%b %Y')}  ({m6_ret[best_cohort_m6]:.1f}%)")
        print(f"  Worst M6 retention cohort:  {worst_cohort_m6.strftime('%b %Y')}  ({m6_ret[worst_cohort_m6]:.1f}%)")

# Aggregate retention curve (already in agg_retention from Phase 3)
print(f"  Aggregate retention curve:")
for k, v in agg_retention.items():
    bar = "#" * int(v / 5) if pd.notna(v) else ""
    display = f"{v:.1f}%  {bar}" if pd.notna(v) else "N/A"
    print(f"    {k:>4}: {display}")

# M1 drop is the critical early-churn signal (per Phase 2 finding: churned median tenure 2.7 months)
m1 = agg_retention.get("M1", None)
m0 = agg_retention.get("M0", 100.0)
if m1 is not None and pd.notna(m1):
    m1_drop = m0 - m1
    print(f"  M0→M1 drop: {m1_drop:.1f} pp  (early churn is the dominant driver)")

# -----------------------------------------------------------------------------
# SQ3: How does churn rate vary by segment (plan tier, industry, referral source, seats)?
# -----------------------------------------------------------------------------
print("\n--- SQ3: Churn segmentation ---")

# Minimum segment size: 20 accounts (scoping doc rule)
MIN_SEG = 20

# acct is a filtered copy of accounts — it already carries all accounts columns
# (industry, referral_source, seats, plan_tier, etc.) — no merge needed
seg_base = acct.copy()

def churn_rate_by(df, col):
    """Return churn rate per category; suppress categories below MIN_SEG."""
    grp = df.groupby(col).agg(
        total=("account_id", "count"),
        churned=("is_churned", "sum")
    ).reset_index()
    grp["churn_rate_pct"] = (grp["churned"] / grp["total"] * 100).round(1)
    grp["reported"] = grp["total"] >= MIN_SEG
    return grp.sort_values("churn_rate_pct", ascending=False)

seg_tier = churn_rate_by(seg_base, "plan_tier")
seg_industry = churn_rate_by(seg_base, "industry")
seg_referral = churn_rate_by(seg_base, "referral_source")

# Seats: bucket into bands
seg_base["seats_band"] = pd.cut(seg_base["seats"], bins=[0, 5, 10, 25, 50, 999],
                                 labels=["1-5", "6-10", "11-25", "26-50", "51+"])
seg_seats = churn_rate_by(seg_base, "seats_band")

print("\n  By plan tier (all segments reportable):")
for _, row in seg_tier.iterrows():
    flag = "" if row["reported"] else "  [< 20 accounts — count only]"
    rate_str = f"{row['churn_rate_pct']:.1f}%" if row["reported"] else "N/A"
    print(f"    {row['plan_tier']:<14}: {rate_str:>6}  (n={row['total']}){flag}")

print("\n  By industry (top 5 by churn rate, min 20 accounts):")
for _, row in seg_industry[seg_industry["reported"]].head(5).iterrows():
    print(f"    {row['industry']:<20}: {row['churn_rate_pct']:.1f}%  (n={row['total']})")

print("\n  By referral source (min 20 accounts):")
for _, row in seg_referral[seg_referral["reported"]].iterrows():
    print(f"    {row['referral_source']:<20}: {row['churn_rate_pct']:.1f}%  (n={row['total']})")

print("\n  By seats band (min 20 accounts):")
for _, row in seg_seats[seg_seats["reported"]].iterrows():
    print(f"    {row['seats_band']:<10}: {row['churn_rate_pct']:.1f}%  (n={row['total']})")

# Chart: churn rate by plan tier and by top industries (side by side)
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

seg_tier_plot = seg_tier[seg_tier["reported"]].sort_values("churn_rate_pct", ascending=True)
axes[0].barh(seg_tier_plot["plan_tier"], seg_tier_plot["churn_rate_pct"], color="#2878b5")
axes[0].set_title("Churn Rate by Plan Tier", fontsize=12)
axes[0].set_xlabel("Churn Rate (%)")
for i, (_, row) in enumerate(seg_tier_plot.iterrows()):
    axes[0].text(row["churn_rate_pct"] + 0.5, i, f"{row['churn_rate_pct']:.1f}%  n={row['total']}", va="center", fontsize=9)
axes[0].set_xlim(0, seg_tier_plot["churn_rate_pct"].max() * 1.25)

seg_ind_plot = seg_industry[seg_industry["reported"]].sort_values("churn_rate_pct", ascending=True)
axes[1].barh(seg_ind_plot["industry"], seg_ind_plot["churn_rate_pct"], color="#1a6b3c")
axes[1].set_title("Churn Rate by Industry (n >= 20)", fontsize=12)
axes[1].set_xlabel("Churn Rate (%)")
for i, (_, row) in enumerate(seg_ind_plot.iterrows()):
    axes[1].text(row["churn_rate_pct"] + 0.5, i, f"{row['churn_rate_pct']:.1f}%  n={row['total']}", va="center", fontsize=9)
axes[1].set_xlim(0, seg_ind_plot["churn_rate_pct"].max() * 1.25 if len(seg_ind_plot) > 0 else 100)

plt.tight_layout()
plt.savefig(VIZ_DIR / "sq3_churn_segments.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Chart saved: sq3_churn_segments.png")

# -----------------------------------------------------------------------------
# SQ4: What behavioral signals precede churn (60-day observation window)?
# -----------------------------------------------------------------------------
print("\n--- SQ4: Pre-churn behavioral signals (60-day window) ---")

# For churned accounts: 60-day window ending at churn_date
# For active accounts: 60-day window ending at dataset end (2024-12-31)
OBS_END_ACTIVE = pd.Timestamp("2024-12-31")
OBS_WINDOW_DAYS = 60

# Deduplicated feature_usage (already cleaned in Phase 1 via dedup; reload with same logic)
fu = pd.read_csv(DATA_DIR / "ravenstack_feature_usage.csv", parse_dates=["usage_date"])
fu = fu.drop_duplicates(subset="usage_id", keep="first")
# Join subscription → account
fu = fu.merge(subs_paid[["subscription_id", "account_id"]], on="subscription_id", how="inner")

# Churned accounts: window = [churn_date - 60d, churn_date)
churned_windows = churn_first[["account_id", "churn_date"]].copy()
churned_windows["window_start"] = churned_windows["churn_date"] - pd.Timedelta(days=OBS_WINDOW_DAYS)
churned_windows["group"] = "churned"

# Active accounts: window = [OBS_END_ACTIVE - 60d, OBS_END_ACTIVE]
active_ids = acct[acct["is_churned"] == False]["account_id"]
active_windows = pd.DataFrame({
    "account_id": active_ids,
    "churn_date": OBS_END_ACTIVE,
    "window_start": OBS_END_ACTIVE - pd.Timedelta(days=OBS_WINDOW_DAYS),
    "group": "active"
})

windows = pd.concat([churned_windows, active_windows], ignore_index=True)

# Tag each feature_usage row with group membership
fu_tagged = fu.merge(windows[["account_id", "window_start", "churn_date", "group"]], on="account_id", how="inner")
fu_in_window = fu_tagged[
    (fu_tagged["usage_date"] >= fu_tagged["window_start"]) &
    (fu_tagged["usage_date"] < fu_tagged["churn_date"])
]

# Aggregate per account: usage days, total events, distinct features, errors
fu_agg = (
    fu_in_window
    .groupby(["account_id", "group"])
    .agg(
        usage_days=("usage_date", "nunique"),
        total_events=("usage_count", "sum"),
        distinct_features=("feature_name", "nunique"),
        total_errors=("error_count", "sum")
    )
    .reset_index()
)

# Accounts with zero activity in window also matter — fill with 0
all_acct_groups = windows[["account_id", "group"]].drop_duplicates()
fu_agg_full = all_acct_groups.merge(fu_agg.drop(columns="group"), on="account_id", how="left").fillna(0)
fu_agg_full["group"] = all_acct_groups["group"].values

# Summary by group
prechurn_summary = fu_agg_full.groupby("group")[["usage_days", "total_events", "distinct_features", "total_errors"]].median().round(2)
print(f"\n  Median feature usage in 60-day window:")
print(f"  {'Metric':<25} {'Churned':>10} {'Active':>10}")
print(f"  {'-' * 45}")
for metric in ["usage_days", "total_events", "distinct_features", "total_errors"]:
    c_val = prechurn_summary.loc["churned", metric] if "churned" in prechurn_summary.index else float("nan")
    a_val = prechurn_summary.loc["active", metric] if "active" in prechurn_summary.index else float("nan")
    print(f"  {metric:<25} {c_val:>10.1f} {a_val:>10.1f}")

# Support metrics in 60-day window
st = pd.read_csv(DATA_DIR / "ravenstack_support_tickets.csv", parse_dates=["submitted_at", "closed_at"])
st_tagged = st.merge(windows[["account_id", "window_start", "churn_date", "group"]], on="account_id", how="inner")
st_in_window = st_tagged[
    (st_tagged["submitted_at"] >= st_tagged["window_start"]) &
    (st_tagged["submitted_at"] < st_tagged["churn_date"])
]
st_agg = (
    st_in_window
    .groupby(["account_id", "group"])
    .agg(
        ticket_count=("ticket_id", "count"),
        escalations=("escalation_flag", "sum"),
        avg_resolution_hrs=("resolution_time_hours", "mean"),
        avg_satisfaction=("satisfaction_score", "mean")  # nulls excluded by mean()
    )
    .reset_index()
)
st_agg_full = all_acct_groups.merge(st_agg.drop(columns="group"), on="account_id", how="left").fillna({"ticket_count": 0, "escalations": 0})
st_agg_full["group"] = all_acct_groups["group"].values

support_summary = st_agg_full.groupby("group")[["ticket_count", "escalations", "avg_resolution_hrs", "avg_satisfaction"]].median().round(2)
print(f"\n  Median support metrics in 60-day window:")
print(f"  {'Metric':<30} {'Churned':>10} {'Active':>10}")
print(f"  {'-' * 50}")
for metric in ["ticket_count", "escalations", "avg_resolution_hrs", "avg_satisfaction"]:
    c_val = support_summary.loc["churned", metric] if "churned" in support_summary.index else float("nan")
    a_val = support_summary.loc["active", metric] if "active" in support_summary.index else float("nan")
    c_str = f"{c_val:.1f}" if pd.notna(c_val) else "N/A"
    a_str = f"{a_val:.1f}" if pd.notna(a_val) else "N/A"
    print(f"  {metric:<30} {c_str:>10} {a_str:>10}")

# Chart: boxplots of key pre-churn signals
fig, axes = plt.subplots(2, 2, figsize=(12, 9))
metrics_to_plot = [
    (fu_agg_full, "distinct_features", "Distinct Features Used (60d)", axes[0, 0]),
    (fu_agg_full, "usage_days",        "Active Usage Days (60d)",      axes[0, 1]),
    (st_agg_full, "ticket_count",      "Support Tickets Filed (60d)",  axes[1, 0]),
    (fu_agg_full, "total_errors",      "Total Errors (60d)",           axes[1, 1]),
]
pal = {"churned": "#c0392b", "active": "#27ae60"}
for df, col, title, ax in metrics_to_plot:
    for grp, color in pal.items():
        vals = df[df["group"] == grp][col].dropna()
        ax.boxplot(vals, positions=[list(pal.keys()).index(grp)], patch_artist=True,
                   boxprops=dict(facecolor=color, alpha=0.7),
                   medianprops=dict(color="black", linewidth=2),
                   whiskerprops=dict(color=color), capprops=dict(color=color),
                   flierprops=dict(marker=".", markersize=3, alpha=0.4, color=color))
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Churned", "Active"])
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("Count")

plt.suptitle("Pre-Churn Behavioral Signals: Churned vs Active Accounts (60-Day Window)", fontsize=12, y=1.01)
plt.tight_layout()
plt.savefig(VIZ_DIR / "sq4_prechurn_signals.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Chart saved: sq4_prechurn_signals.png")

# Sensitivity check: repeat for 30d and 90d windows (median distinct_features only)
for window_d in [30, 90]:
    fu_sens = fu_tagged.copy()
    fu_sens["window_start_sens"] = fu_sens["churn_date"] - pd.Timedelta(days=window_d)
    fu_in_sens = fu_sens[
        (fu_sens["usage_date"] >= fu_sens["window_start_sens"]) &
        (fu_sens["usage_date"] < fu_sens["churn_date"])
    ]
    sens_agg = fu_in_sens.groupby(["account_id", "group"])["feature_name"].nunique().reset_index(name="distinct_features")
    sens_full = all_acct_groups.merge(sens_agg.drop(columns="group"), on="account_id", how="left").fillna(0)
    sens_full["group"] = all_acct_groups["group"].values
    sens_med = sens_full.groupby("group")["distinct_features"].median()
    c = sens_med.get("churned", float("nan"))
    a = sens_med.get("active", float("nan"))
    print(f"  Sensitivity {window_d}d window — median distinct features: churned={c:.1f}  active={a:.1f}")

# -----------------------------------------------------------------------------
# SQ5: Which features are associated with better retention?
# -----------------------------------------------------------------------------
print("\n--- SQ5: Feature adoption vs churn ---")

# Lifetime feature breadth per account (all time, not windowed)
fu_lifetime = (
    fu.groupby("account_id")
    .agg(
        lifetime_features=("feature_name", "nunique"),
        lifetime_events=("usage_count", "sum"),
        lifetime_errors=("error_count", "sum")
    )
    .reset_index()
)
acct_feat = acct.merge(fu_lifetime, on="account_id", how="left").fillna(0)

feat_by_churn = acct_feat.groupby("is_churned")[["lifetime_features", "lifetime_events", "lifetime_errors"]].median().round(2)
print(f"\n  Median lifetime feature metrics:")
print(f"  {'Metric':<25} {'Churned (True)':>14} {'Active (False)':>14}")
print(f"  {'-' * 53}")
for metric in ["lifetime_features", "lifetime_events", "lifetime_errors"]:
    c_val = feat_by_churn.loc[True, metric] if True in feat_by_churn.index else float("nan")
    a_val = feat_by_churn.loc[False, metric] if False in feat_by_churn.index else float("nan")
    print(f"  {metric:<25} {c_val:>14.1f} {a_val:>14.1f}")

# Per-feature retention index: P(not churned | used feature) vs baseline
# baseline = overall non-churn rate among non-trial accounts
baseline_retention = 1 - acct["is_churned"].mean()

all_features = fu["feature_name"].unique()
feat_retention = []
for feat in all_features:
    users = fu[fu["feature_name"] == feat]["account_id"].unique()
    users_acct = acct[acct["account_id"].isin(users)]
    n = len(users_acct)
    if n < MIN_SEG:
        continue
    ret_rate = 1 - users_acct["is_churned"].mean()
    feat_retention.append({
        "feature": feat,
        "n_accounts": n,
        "retention_rate_pct": ret_rate * 100,
        "retention_index": ret_rate / baseline_retention  # >1 = above average retention
    })

feat_ret_df = pd.DataFrame(feat_retention).sort_values("retention_index", ascending=False)
print(f"\n  Baseline retention rate: {baseline_retention * 100:.1f}%")
print(f"\n  Top 10 features by retention index (n >= {MIN_SEG}):")
print(f"  {'Feature':<35} {'n':>5} {'Ret %':>7} {'Index':>7}")
print(f"  {'-' * 56}")
for _, row in feat_ret_df.head(10).iterrows():
    print(f"  {row['feature']:<35} {int(row['n_accounts']):>5} {row['retention_rate_pct']:>7.1f}% {row['retention_index']:>7.2f}x")

print(f"\n  Bottom 5 features by retention index:")
for _, row in feat_ret_df.tail(5).iterrows():
    print(f"  {row['feature']:<35} {int(row['n_accounts']):>5} {row['retention_rate_pct']:>7.1f}% {row['retention_index']:>7.2f}x")

# Chart: feature retention index (top 15, sorted)
top_feat = feat_ret_df.head(15).sort_values("retention_index", ascending=True)
fig, ax = plt.subplots(figsize=(10, 7))
colors = ["#27ae60" if v >= 1 else "#c0392b" for v in top_feat["retention_index"]]
ax.barh(top_feat["feature"], top_feat["retention_index"], color=colors)
ax.axvline(1.0, color="black", linestyle="--", linewidth=1, label="Baseline (1.0x)")
ax.set_title("Feature Retention Index — Top 15 Features\n(>1.0x = above-average retention among users)", fontsize=12)
ax.set_xlabel("Retention Index (feature users vs baseline)")
ax.legend()
plt.tight_layout()
plt.savefig(VIZ_DIR / "sq5_feature_adoption.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Chart saved: sq5_feature_adoption.png")

# -----------------------------------------------------------------------------
# SQ6: How does support volume and quality relate to churn?
# -----------------------------------------------------------------------------
print("\n--- SQ6: Support → churn relationship ---")

# Lifetime support metrics per account
st_lifetime = (
    st.groupby("account_id")
    .agg(
        total_tickets=("ticket_id", "count"),
        total_escalations=("escalation_flag", "sum"),
        avg_resolution_hrs=("resolution_time_hours", "mean"),
        avg_satisfaction=("satisfaction_score", "mean"),  # nulls excluded
        pct_high_priority=("priority", lambda x: (x == "High").mean() * 100)
    )
    .reset_index()
)
acct_support = acct.merge(st_lifetime, on="account_id", how="left").fillna({"total_tickets": 0, "total_escalations": 0})

supp_by_churn = acct_support.groupby("is_churned")[
    ["total_tickets", "total_escalations", "avg_resolution_hrs", "avg_satisfaction", "pct_high_priority"]
].median().round(2)

print(f"\n  Median lifetime support metrics by churn status:")
print(f"  {'Metric':<30} {'Churned (True)':>14} {'Active (False)':>14}")
print(f"  {'-' * 58}")
for metric in ["total_tickets", "total_escalations", "avg_resolution_hrs", "avg_satisfaction", "pct_high_priority"]:
    c_val = supp_by_churn.loc[True, metric] if True in supp_by_churn.index else float("nan")
    a_val = supp_by_churn.loc[False, metric] if False in supp_by_churn.index else float("nan")
    c_str = f"{c_val:.1f}" if pd.notna(c_val) else "N/A"
    a_str = f"{a_val:.1f}" if pd.notna(a_val) else "N/A"
    print(f"  {metric:<30} {c_str:>14} {a_str:>14}")

# Escalation flag: churn rate among escalated vs non-escalated accounts
escalated = acct_support[acct_support["total_escalations"] > 0]
non_escalated = acct_support[acct_support["total_escalations"] == 0]
esc_churn = escalated["is_churned"].mean() * 100
non_esc_churn = non_escalated["is_churned"].mean() * 100
print(f"\n  Churn rate — accounts with escalation:     {esc_churn:.1f}%  (n={len(escalated)})")
print(f"  Churn rate — accounts without escalation:  {non_esc_churn:.1f}%  (n={len(non_escalated)})")

# Chart: support metrics by churn status
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
supp_metrics = [
    ("total_tickets",      "Total Lifetime Tickets",      axes[0]),
    ("total_escalations",  "Total Escalations",           axes[1]),
    ("avg_satisfaction",   "Avg Satisfaction Score",      axes[2]),
]
for col, title, ax in supp_metrics:
    data_c = acct_support[acct_support["is_churned"] == True][col].dropna()
    data_a = acct_support[acct_support["is_churned"] == False][col].dropna()
    ax.boxplot([data_c, data_a], patch_artist=True,
               boxprops=dict(facecolor="#c0392b", alpha=0.7),
               medianprops=dict(color="black", linewidth=2))
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Churned", "Active"])
    ax.set_title(title, fontsize=11)
    ax.set_ylabel(col.replace("_", " ").title())

# Fix: boxplot for active gets blue color override
for col, title, ax in supp_metrics:
    patches = ax.patches
    if len(patches) >= 2:
        patches[1].set_facecolor("#27ae60")

plt.suptitle("Support Metrics by Churn Status (Lifetime)", fontsize=12)
plt.tight_layout()
plt.savefig(VIZ_DIR / "sq6_support_churn.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Chart saved: sq6_support_churn.png")

# -----------------------------------------------------------------------------
# SQ7: What is GRR by segment, and where does expansion MRR come from?
# NRR deprecated (concurrent subscription accumulation inflates to ~335%).
# GRR is the reliable revenue retention metric.
# -----------------------------------------------------------------------------
print("\n--- SQ7: GRR + expansion analysis ---")

# GRR from nrr_df (rolling 12-month, computed in Phase 3)
# nrr_df columns: cohort_month (Period[M]), n_accounts, starting_mrr, ending_mrr, nrr_pct, grr_pct
print(f"\n  12-month rolling GRR (overall):")
print(f"    Median: {nrr_df['grr_pct'].median():.1f}%")
print(f"    Min:    {nrr_df['grr_pct'].min():.1f}%  ({nrr_df.loc[nrr_df['grr_pct'].idxmin(), 'cohort_month']})")
print(f"    Max:    {nrr_df['grr_pct'].max():.1f}%  ({nrr_df.loc[nrr_df['grr_pct'].idxmax(), 'cohort_month']})")
print(f"    Benchmark: 80–90% (SaaS standard)")

# Expansion: subscriptions with upgrade_flag = True
# subs_paid already carries plan_tier — no merge needed
upgrades = subs_paid[subs_paid["upgrade_flag"] == True]
upgrade_counts = upgrades.groupby("plan_tier").agg(
    upgrade_events=("subscription_id", "count"),
    upgrade_mrr=("mrr_amount", "sum")
).reset_index()

acct_counts = seg_base.groupby("plan_tier").agg(total_accounts=("account_id", "count")).reset_index()
upgrade_summary = upgrade_counts.merge(acct_counts, on="plan_tier", how="left")
upgrade_summary["upgrades_per_account"] = (upgrade_summary["upgrade_events"] / upgrade_summary["total_accounts"]).round(2)
upgrade_summary["avg_upgrade_mrr"] = (upgrade_summary["upgrade_mrr"] / upgrade_summary["upgrade_events"]).round(0)

print(f"\n  Upgrade events by plan tier:")
print(f"  {'Tier':<14} {'Upgrades':>9} {'Upgrades/Acct':>14} {'Avg Upgrade MRR':>16} {'Total Upgrade MRR':>18}")
print(f"  {'-' * 73}")
for _, row in upgrade_summary.sort_values("upgrade_events", ascending=False).iterrows():
    print(f"  {row['plan_tier']:<14} {int(row['upgrade_events']):>9} {row['upgrades_per_account']:>14.2f} ${row['avg_upgrade_mrr']:>15,.0f} ${row['upgrade_mrr']:>17,.0f}")

# Downgrade events for contrast — subs_paid already has plan_tier
downgrades = subs_paid[subs_paid["downgrade_flag"] == True]
downgrade_counts = downgrades.groupby("plan_tier").agg(
    downgrade_events=("subscription_id", "count"),
    downgrade_mrr=("mrr_amount", "sum")
).reset_index()

print(f"\n  Downgrade events by plan tier:")
for _, row in downgrade_counts.sort_values("downgrade_events", ascending=False).iterrows():
    print(f"    {row['plan_tier']:<14}: {int(row['downgrade_events'])} events  (${row['downgrade_mrr']:,.0f} MRR)")

# Chart: GRR trend over time + upgrade MRR by tier
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# cohort_month is Period[M] — filter and convert to Timestamp for matplotlib
grr_excl = nrr_df[nrr_df["cohort_month"] < pd.Period("2024-12", "M")]
axes[0].plot(grr_excl["cohort_month"].dt.to_timestamp(), grr_excl["grr_pct"], color="#1a3a5c", linewidth=2, marker="o", markersize=4)
axes[0].axhline(80, color="#c0392b", linestyle="--", linewidth=1, label="80% benchmark (floor)")
axes[0].axhline(90, color="#27ae60", linestyle="--", linewidth=1, label="90% benchmark (target)")
axes[0].set_title("12-Month Rolling GRR (ex-Dec 2024)", fontsize=12)
axes[0].set_xlabel("Month")
axes[0].set_ylabel("GRR (%)")
axes[0].legend(fontsize=9)
axes[0].set_ylim(0, 120)

tier_upg = upgrade_summary.sort_values("upgrade_mrr", ascending=True)
axes[1].barh(tier_upg["plan_tier"], tier_upg["upgrade_mrr"] / 1000, color="#2878b5")
axes[1].set_title("Total Upgrade MRR by Plan Tier", fontsize=12)
axes[1].set_xlabel("Upgrade MRR ($K)")
axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.0f}K"))

plt.tight_layout()
plt.savefig(VIZ_DIR / "sq7_grr_expansion.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Chart saved: sq7_grr_expansion.png")

# =============================================================================
# --- Phase 4 summary ---
# =============================================================================

print(f"\n{'=' * 70}")
print("PHASE 4 SUMMARY — SUB-QUESTION ANALYSIS (SQ1–SQ7)")
print(f"{'=' * 70}")
print()
print("  SQ1 — MRR Trend:")
print(f"    MRR grew from ${mrr_jan23:,.0f} to ${mrr_nov24:,.0f} (ex-Dec 2024)")
print(f"    Peak MRR: ${mrr_peak:,.0f} ({mrr_peak_month})")
print(f"    Tier mix at end of period:")
for tier in tier_order:
    if tier in tier_share_end.index:
        print(f"      {tier:<14}: {tier_share_end[tier]:.1f}%")
print()
print("  SQ2 — Cohort Retention:")
m1 = agg_retention.get("M1", None)
if m1 is not None and pd.notna(m1):
    print(f"    M0→M1 drop: {m0 - m1:.1f} pp (dominant early-churn signal)")
if "M6" in cohort_ret.columns and len(m6_ret) >= 2:
    print(f"    Best M6 cohort:  {best_cohort_m6.strftime('%b %Y')}  ({m6_ret[best_cohort_m6]:.1f}%)")
    print(f"    Worst M6 cohort: {worst_cohort_m6.strftime('%b %Y')}  ({m6_ret[worst_cohort_m6]:.1f}%)")
print()
print("  SQ3 — Churn Segmentation:")
print("    (see printed tables above for full segment breakdown)")
print()
print("  SQ4 — Pre-Churn Signals (60d window):")
print("    (see printed tables above; sensitivity check at 30d and 90d)")
print()
print("  SQ5 — Feature Adoption:")
print(f"    Baseline retention rate: {baseline_retention * 100:.1f}%")
if len(feat_ret_df) > 0:
    top_f = feat_ret_df.iloc[0]
    print(f"    Highest retention-index feature: {top_f['feature']} ({top_f['retention_index']:.2f}x)")
print()
print("  SQ6 — Support → Churn:")
print(f"    Churn rate with escalation:    {esc_churn:.1f}%")
print(f"    Churn rate without escalation: {non_esc_churn:.1f}%")
print()
print("  SQ7 — GRR + Expansion:")
print(f"    Median GRR: {nrr_df['grr_pct'].median():.1f}%  (benchmark: 80–90%)")
print(f"    NRR deprecated (concurrent subscription model)")
print()
print("  Charts saved: sq1_mrr_by_tier, sq3_churn_segments, sq4_prechurn_signals,")
print("                sq5_feature_adoption, sq6_support_churn, sq7_grr_expansion")
print()
print(f"\n  Ready to proceed to Phase 5 (model / SQ8): PENDING REVIEW")
print(f"{'=' * 70}\n")

# =============================================================================
# === Phase 5: Model (SQ8) + ICP (SQ9) ===
# =============================================================================

print("\n" + "=" * 70)
print("PHASE 5 — MODEL (SQ8) + ICP (SQ9)")
print("=" * 70)

# ML imports (scoping doc stack: scikit-learn, xgboost, shap)
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    roc_auc_score, precision_recall_curve, roc_curve,
    classification_report, precision_score, recall_score, f1_score
)
from xgboost import XGBClassifier
import shap
import pickle

# Export directory (CSV + pkl outputs per scoping doc)
EXPORT_DIR = SCRIPT_DIR / "export"
EXPORT_DIR.mkdir(exist_ok=True)

# Gross margin assumption: 80% SaaS benchmark (flagged per scoping doc)
GROSS_MARGIN = 0.80

# =============================================================================
# --- SQ8.0: Feature engineering ---
# Target: is_churned (non-trial accounts)
# Observation window: 60d pre-churn (churned) / last 60d of dataset (active)
# Window data already computed in SQ4: fu_agg_full, st_agg_full, windows, fu_tagged
# =============================================================================
print("\n--- SQ8: Feature engineering ---")

# -- Base features --
feat_base = acct[["account_id", "is_churned", "tenure_months", "plan_tier", "seats"]].copy()

# Ordinal encode plan tier (Basic < Pro < Enterprise)
TIER_RANK = {"Basic": 0, "Pro": 1, "Enterprise": 2}
feat_base["plan_tier_num"] = feat_base["plan_tier"].map(TIER_RANK).fillna(0).astype(int)

# early_churn_flag: account still in first 90 days at observation (high-risk per M0→M1 drop)
feat_base["early_churn_flag"] = (feat_base["tenure_months"] <= 3).astype(int)

# -- Usage trend: ratio of activity in last-30d vs first-30d of the 60d window --
# fu_tagged from SQ4 already has window_start and churn_date per account
fu_w = fu_tagged.copy()
fu_w["midpoint"] = fu_w["window_start"] + pd.Timedelta(days=30)

usage_first = (
    fu_w[(fu_w["usage_date"] >= fu_w["window_start"]) & (fu_w["usage_date"] < fu_w["midpoint"])]
    .groupby("account_id")["usage_date"].nunique()
    .rename("days_first30")
)
usage_last = (
    fu_w[(fu_w["usage_date"] >= fu_w["midpoint"]) & (fu_w["usage_date"] < fu_w["churn_date"])]
    .groupby("account_id")["usage_date"].nunique()
    .rename("days_last30")
)
trend_df = pd.concat([usage_first, usage_last], axis=1).fillna(0)
# +1 in denominator avoids div/0; >1 = accelerating, <1 = decelerating
trend_df["usage_trend"] = trend_df["days_last30"] / (trend_df["days_first30"] + 1)

# -- 60-day window features (from fu_agg_full / st_agg_full in SQ4) --
feat_60d = fu_agg_full[["account_id", "usage_days", "total_events", "distinct_features", "total_errors"]].copy()
feat_60d.columns = ["account_id", "usage_days_60d", "events_60d", "features_60d", "errors_60d"]
# error_rate: errors per usage event (+1 avoids div/0)
feat_60d["error_rate"] = feat_60d["errors_60d"] / (feat_60d["events_60d"] + 1)

# tenure-normalized usage: events in window / tenure (controls for observation window length)
feat_60d = feat_60d.merge(feat_base[["account_id", "tenure_months"]], on="account_id", how="left")
feat_60d["tenure_norm_usage"] = feat_60d["events_60d"] / (feat_60d["tenure_months"] + 1)
feat_60d = feat_60d.drop(columns="tenure_months")

feat_supp = st_agg_full[["account_id", "ticket_count", "escalations", "avg_satisfaction"]].copy()
feat_supp.columns = ["account_id", "tickets_60d", "escalations_60d", "satisfaction_60d"]

# -- Lifetime features (feature breadth, from SQ5 fu_lifetime) --
feat_life = fu_lifetime[["account_id", "lifetime_features"]].copy()

# -- Assemble master feature table --
features = (
    feat_base
    .merge(feat_60d, on="account_id", how="left")
    .merge(feat_supp, on="account_id", how="left")
    .merge(trend_df[["usage_trend"]], left_on="account_id", right_index=True, how="left")
    .merge(feat_life, on="account_id", how="left")
)
# Fill satisfaction with column median (avoids conflating missing with 0)
med_sat = features["satisfaction_60d"].median()
features["satisfaction_60d"] = features["satisfaction_60d"].fillna(
    med_sat if pd.notna(med_sat) else 4.0
)
features = features.fillna(0)

FEATURE_COLS = [
    "tenure_months",        # account age at observation
    "plan_tier_num",        # ordinal tier (Basic=0, Pro=1, Enterprise=2)
    "seats",                # account size
    "early_churn_flag",     # in first 90 days (high-risk window)
    "usage_days_60d",       # active days in 60d window
    "events_60d",           # total usage events in 60d window
    "features_60d",         # distinct features used in 60d window
    "error_rate",           # errors per usage event (quality signal)
    "tenure_norm_usage",    # events / tenure_months (normalized activity)
    "usage_trend",          # last-30d usage_days / first-30d + 1 (trend direction)
    "tickets_60d",          # support tickets in 60d window
    "escalations_60d",      # escalations in 60d window
    "satisfaction_60d",     # avg satisfaction score in 60d window
    "lifetime_features",    # total distinct features used ever
]

X = features[FEATURE_COLS].values
y = features["is_churned"].astype(int).values

print(f"\n  Feature matrix: {X.shape[0]} accounts x {X.shape[1]} features")
print(f"  Class balance: {y.sum()} churned ({y.mean()*100:.1f}%) | {(1-y).sum()} active ({(1-y).mean()*100:.1f}%)")

# =============================================================================
# --- SQ8.1: Train/test split (stratified, 80/20) ---
# =============================================================================
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)
print(f"  Train: {len(y_train)} | Test: {len(y_test)}  (stratified 80/20)")

# =============================================================================
# --- SQ8.2: Logistic Regression (reference — interpretability first) ---
# =============================================================================
print("\n--- SQ8.2: Logistic Regression (reference) ---")

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s  = scaler.transform(X_test)

lr = LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced")
lr.fit(X_train_s, y_train)

lr_proba = lr.predict_proba(X_test_s)[:, 1]
lr_auc   = roc_auc_score(y_test, lr_proba)

# Operating threshold: maximize F2 score (weights recall 2x — missing a churner costs more)
prec_lr, rec_lr, thresh_lr = precision_recall_curve(y_test, lr_proba)
f2_lr = (5 * prec_lr * rec_lr) / (4 * prec_lr + rec_lr + 1e-9)
best_idx_lr   = np.argmax(f2_lr[:-1])
best_thresh_lr = thresh_lr[best_idx_lr]
lr_pred = (lr_proba >= best_thresh_lr).astype(int)

lr_precision = precision_score(y_test, lr_pred, pos_label=1, zero_division=0)
lr_recall    = recall_score(y_test, lr_pred, pos_label=1, zero_division=0)

print(f"  AUC-ROC:   {lr_auc:.4f}")
print(f"  Operating threshold (F2-max): {best_thresh_lr:.3f}")
print(f"  Precision (Churned): {lr_precision:.3f}")
print(f"  Recall    (Churned): {lr_recall:.3f}")
print("\n  Full classification report:")
print(classification_report(y_test, lr_pred, target_names=["Active", "Churned"]))

# LR feature importances (coefficient magnitudes after scaling)
coef_df = pd.DataFrame({
    "feature": FEATURE_COLS,
    "coef": lr.coef_[0],
    "abs_coef": np.abs(lr.coef_[0])
}).sort_values("abs_coef", ascending=False)
print("  LR feature importances (|coefficient|):")
for _, row in coef_df.head(10).iterrows():
    print(f"    {row['feature']:<25} {row['coef']:+.4f}")

# =============================================================================
# --- SQ8.3: XGBoost benchmark ---
# =============================================================================
print("\n--- SQ8.3: XGBoost benchmark ---")

# scale_pos_weight handles class imbalance: ratio of negative to positive samples
spw = (1 - y_train.mean()) / y_train.mean()
xgb_model = XGBClassifier(
    n_estimators=200,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=spw,
    random_state=42,
    eval_metric="logloss",
    verbosity=0,
    use_label_encoder=False,
)
xgb_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

xgb_proba = xgb_model.predict_proba(X_test)[:, 1]
xgb_auc   = roc_auc_score(y_test, xgb_proba)

# Operating threshold for XGB
prec_xgb, rec_xgb, thresh_xgb = precision_recall_curve(y_test, xgb_proba)
f2_xgb = (5 * prec_xgb * rec_xgb) / (4 * prec_xgb + rec_xgb + 1e-9)
best_idx_xgb    = np.argmax(f2_xgb[:-1])
best_thresh_xgb = thresh_xgb[best_idx_xgb]
xgb_pred = (xgb_proba >= best_thresh_xgb).astype(int)

xgb_precision = precision_score(y_test, xgb_pred, pos_label=1, zero_division=0)
xgb_recall    = recall_score(y_test, xgb_pred, pos_label=1, zero_division=0)

print(f"  AUC-ROC:   {xgb_auc:.4f}")
print(f"  Operating threshold (F2-max): {best_thresh_xgb:.3f}")
print(f"  Precision (Churned): {xgb_precision:.3f}")
print(f"  Recall    (Churned): {xgb_recall:.3f}")
print("\n  Full classification report:")
print(classification_report(y_test, xgb_pred, target_names=["Active", "Churned"]))

# =============================================================================
# --- SQ8.4: Model selection (scoping doc rule: switch if AUC improvement > 0.03) ---
# =============================================================================
print("\n--- SQ8.4: Model selection ---")
auc_delta = xgb_auc - lr_auc
print(f"  LR  AUC-ROC: {lr_auc:.4f}")
print(f"  XGB AUC-ROC: {xgb_auc:.4f}")
print(f"  Delta: {auc_delta:+.4f}  (threshold for switch: +0.03)")

if auc_delta > 0.03:
    WINNING_MODEL   = "XGBoost"
    best_proba      = xgb_proba
    best_pred_test  = xgb_pred
    best_auc        = xgb_auc
    best_thresh     = best_thresh_xgb
    best_precision  = xgb_precision
    best_recall     = xgb_recall
    use_shap        = True
    print(f"  DECISION: XGBoost selected (delta > 0.03 threshold).")
else:
    WINNING_MODEL   = "Logistic Regression"
    best_proba      = lr_proba
    best_pred_test  = lr_pred
    best_auc        = lr_auc
    best_thresh     = best_thresh_lr
    best_precision  = lr_precision
    best_recall     = lr_recall
    use_shap        = False
    print(f"  DECISION: Logistic Regression retained (delta <= 0.03 threshold).")

# =============================================================================
# --- SQ8.5: SHAP values (if XGBoost wins) ---
# =============================================================================
if use_shap:
    print("\n--- SQ8.5: SHAP feature importance (XGBoost) ---")
    explainer   = shap.TreeExplainer(xgb_model)
    shap_vals   = explainer.shap_values(X_test)
    shap_imp    = pd.DataFrame({
        "feature":       FEATURE_COLS,
        "mean_abs_shap": np.abs(shap_vals).mean(axis=0)
    }).sort_values("mean_abs_shap", ascending=False)
    feature_importance = shap_imp.rename(columns={"mean_abs_shap": "importance"})
    print(f"  Top 10 features by mean |SHAP|:")
    for _, row in shap_imp.head(10).iterrows():
        print(f"    {row['feature']:<25}  {row['mean_abs_shap']:.4f}")

    shap.summary_plot(shap_vals, X_test, feature_names=FEATURE_COLS, show=False)
    plt.tight_layout()
    plt.savefig(VIZ_DIR / "sq8_shap_summary.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Chart saved: sq8_shap_summary.png")
else:
    feature_importance = coef_df.rename(columns={"abs_coef": "importance"})[["feature", "importance"]]

# =============================================================================
# --- SQ8.6: Model performance chart (ROC + Precision-Recall) ---
# =============================================================================
fpr, tpr, _ = roc_curve(y_test, best_proba)
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

axes[0].plot(fpr, tpr, color="#1a3a5c", linewidth=2,
             label=f"{WINNING_MODEL} (AUC={best_auc:.3f})")
axes[0].plot([0, 1], [0, 1], "k--", linewidth=1, label="Random baseline")
axes[0].set_title(f"ROC Curve — {WINNING_MODEL}", fontsize=12)
axes[0].set_xlabel("False Positive Rate")
axes[0].set_ylabel("True Positive Rate")
axes[0].legend()

p_arr, r_arr = (prec_xgb, rec_xgb) if use_shap else (prec_lr, rec_lr)
t_arr        = thresh_xgb if use_shap else thresh_lr
axes[1].plot(t_arr, p_arr[:-1], color="#27ae60", linewidth=2, label="Precision")
axes[1].plot(t_arr, r_arr[:-1], color="#c0392b", linewidth=2, label="Recall")
axes[1].axvline(best_thresh, color="black", linestyle="--", linewidth=1,
                label=f"Operating threshold ({best_thresh:.3f})")
axes[1].set_title("Precision & Recall vs Threshold", fontsize=12)
axes[1].set_xlabel("Threshold")
axes[1].set_ylabel("Score")
axes[1].legend()

plt.tight_layout()
plt.savefig(VIZ_DIR / "sq8_model_performance.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\n  Chart saved: sq8_model_performance.png")

# =============================================================================
# --- SQ8.7: Score active accounts + risk tier assignment ---
# =============================================================================
print("\n--- SQ8.7: Scoring active accounts ---")

active_feat = features[features["is_churned"] == False].copy()

if WINNING_MODEL == "XGBoost":
    active_scores = xgb_model.predict_proba(active_feat[FEATURE_COLS].values)[:, 1]
else:
    active_scores = lr.predict_proba(
        scaler.transform(active_feat[FEATURE_COLS].values)
    )[:, 1]

active_feat["churn_risk_score"] = active_scores

# Risk tiers: thresholds chosen symmetrically around operating threshold
# High >= 0.65 (above operating threshold by design), Low <= 0.40
active_feat["risk_tier"] = pd.cut(
    active_feat["churn_risk_score"],
    bins=[0.0, 0.40, 0.65, 1.001],
    labels=["Low", "Medium", "High"],
    right=False
)

risk_counts = active_feat["risk_tier"].value_counts()
print(f"  Active accounts scored: {len(active_feat)}")
print(f"  Risk tier distribution:")
for tier in ["High", "Medium", "Low"]:
    n = risk_counts.get(tier, 0)
    pct = n / len(active_feat) * 100
    print(f"    {tier:<8}: {n:>4} accounts ({pct:.1f}%)")

# =============================================================================
# --- SQ8.8: Export churn_risk_scores.csv + churn_model.pkl ---
# =============================================================================
print("\n--- SQ8.8: Exporting model artifacts ---")

risk_export = active_feat[
    ["account_id", "churn_risk_score", "risk_tier", "plan_tier", "tenure_months",
     "early_churn_flag", "error_rate", "usage_trend"]
].copy()
risk_export["churn_risk_score"] = risk_export["churn_risk_score"].round(4)
risk_export = risk_export.sort_values("churn_risk_score", ascending=False)
risk_export.to_csv(EXPORT_DIR / "churn_risk_scores.csv", index=False, encoding="utf-8-sig")
print(f"  Exported: export/churn_risk_scores.csv  ({len(risk_export)} rows)")

model_artifact = {
    "model":        xgb_model if WINNING_MODEL == "XGBoost" else lr,
    "scaler":       None if WINNING_MODEL == "XGBoost" else scaler,
    "feature_cols": FEATURE_COLS,
    "threshold":    best_thresh,
    "model_name":   WINNING_MODEL,
    "auc_roc":      best_auc,
}
with open(EXPORT_DIR / "churn_model.pkl", "wb") as f:
    pickle.dump(model_artifact, f)
print(f"  Exported: export/churn_model.pkl")

# =============================================================================
# --- SQ9: ICP Profile — LTV by segment ---
# LTV (realized): sum of monthly MRR across all active months * gross_margin (80%)
# Forward-looking LTV would require a churn rate assumption per segment —
# using realized LTV here for precision; flag as limitation in writeup.
# =============================================================================
print("\n--- SQ9: ICP Profile — LTV by segment ---")
print(f"  (Gross margin assumption: {GROSS_MARGIN*100:.0f}% — SaaS benchmark, flagged)")

# Realized LTV per account from mrr_panel (one row per active subscription-month)
acct_ltv_raw = mrr_panel.groupby("account_id")["mrr_amount"].sum().reset_index()
acct_ltv_raw.columns = ["account_id", "total_lifetime_mrr"]
acct_ltv_raw["ltv_realized"] = (acct_ltv_raw["total_lifetime_mrr"] * GROSS_MARGIN).round(0)

# Merge with acct (has industry, referral_source, is_churned, tenure_months)
acct_ltv = acct.merge(acct_ltv_raw, on="account_id", how="left").fillna(0)

def ltv_segment_summary(df, col, min_n=MIN_SEG):
    """Segment LTV + churn — suppress segments below min_n."""
    grp = df.groupby(col).agg(
        n           =("account_id", "count"),
        avg_ltv     =("ltv_realized", "mean"),
        median_ltv  =("ltv_realized", "median"),
        churn_pct   =("is_churned", lambda x: x.mean() * 100),
        avg_tenure  =("tenure_months", "mean"),
    ).reset_index()
    grp = grp[grp["n"] >= min_n].sort_values("avg_ltv", ascending=False)
    grp["avg_ltv"]    = grp["avg_ltv"].round(0)
    grp["median_ltv"] = grp["median_ltv"].round(0)
    grp["churn_pct"]  = grp["churn_pct"].round(1)
    grp["avg_tenure"] = grp["avg_tenure"].round(1)
    return grp

ltv_tier     = ltv_segment_summary(acct_ltv, "plan_tier")
ltv_industry = ltv_segment_summary(acct_ltv, "industry")
ltv_referral = ltv_segment_summary(acct_ltv, "referral_source")

print(f"\n  Realized LTV by plan tier:")
print(f"  {'Tier':<14} {'n':>5} {'Avg LTV':>12} {'Median LTV':>12} {'Churn%':>8} {'Avg Tenure':>11}")
print(f"  {'-' * 62}")
for _, row in ltv_tier.iterrows():
    print(f"  {row['plan_tier']:<14} {int(row['n']):>5} "
          f"${int(row['avg_ltv']):>11,} ${int(row['median_ltv']):>11,} "
          f"{row['churn_pct']:>7.1f}% {row['avg_tenure']:>10.1f}mo")

print(f"\n  Realized LTV by industry (top 5 by avg LTV, n >= {MIN_SEG}):")
print(f"  {'Industry':<25} {'n':>5} {'Avg LTV':>12} {'Churn%':>8}")
print(f"  {'-' * 52}")
for _, row in ltv_industry.head(5).iterrows():
    print(f"  {row['industry']:<25} {int(row['n']):>5} ${int(row['avg_ltv']):>11,} {row['churn_pct']:>7.1f}%")

print(f"\n  Realized LTV by referral source (n >= {MIN_SEG}):")
print(f"  {'Source':<22} {'n':>5} {'Avg LTV':>12} {'Churn%':>8}")
print(f"  {'-' * 49}")
for _, row in ltv_referral.iterrows():
    print(f"  {row['referral_source']:<22} {int(row['n']):>5} ${int(row['avg_ltv']):>11,} {row['churn_pct']:>7.1f}%")

# ICP: highest avg LTV AND below-average churn rate
overall_churn_rate = acct_ltv["is_churned"].mean() * 100
avg_ltv_overall    = acct_ltv["ltv_realized"].mean()

print(f"\n  Overall baseline: churn {overall_churn_rate:.1f}%  |  avg LTV ${avg_ltv_overall:,.0f}")
print(f"\n  ICP candidates (above avg LTV AND below avg churn — by tier):")
icp_tier = ltv_tier[
    (ltv_tier["avg_ltv"] > avg_ltv_overall) &
    (ltv_tier["churn_pct"] < overall_churn_rate)
]
if len(icp_tier) > 0:
    for _, row in icp_tier.iterrows():
        print(f"    {row['plan_tier']:<14}: avg LTV ${int(row['avg_ltv']):,}  "
              f"churn {row['churn_pct']:.1f}%  avg tenure {row['avg_tenure']:.1f}mo")
else:
    print("    No single tier clears both thresholds — highest LTV tier listed below.")
    print(f"    {ltv_tier.iloc[0]['plan_tier']}: avg LTV ${int(ltv_tier.iloc[0]['avg_ltv']):,}  "
          f"churn {ltv_tier.iloc[0]['churn_pct']:.1f}%")

# ICP expansion profile (from SQ7 upgrade_summary)
print(f"\n  Expansion MRR by tier (from SQ7):")
for _, row in upgrade_summary.sort_values("upgrade_mrr", ascending=False).iterrows():
    print(f"    {row['plan_tier']:<14}: ${int(row['upgrade_mrr']):>10,} total upgrade MRR  "
          f"({row['upgrades_per_account']:.2f} upgrades/account)")

# LTV chart: average LTV by tier + industry (side by side)
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

ltv_tier_plot = ltv_tier.sort_values("avg_ltv", ascending=True)
bars = axes[0].barh(ltv_tier_plot["plan_tier"], ltv_tier_plot["avg_ltv"] / 1000,
                    color="#1a3a5c")
axes[0].set_title("Average Realized LTV by Plan Tier\n(gross margin 80% — assumed)", fontsize=11)
axes[0].set_xlabel("Avg LTV ($K)")
axes[0].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.0f}K"))
for bar, (_, row) in zip(bars, ltv_tier_plot.iterrows()):
    axes[0].text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                 f"churn {row['churn_pct']:.1f}%", va="center", fontsize=9)

ltv_ind_plot = ltv_industry.head(8).sort_values("avg_ltv", ascending=True)
axes[1].barh(ltv_ind_plot["industry"], ltv_ind_plot["avg_ltv"] / 1000, color="#1a6b3c")
axes[1].set_title(f"Avg Realized LTV by Industry (top 8, n >= {MIN_SEG})", fontsize=11)
axes[1].set_xlabel("Avg LTV ($K)")
axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.0f}K"))

plt.tight_layout()
plt.savefig(VIZ_DIR / "sq9_icp_ltv.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"\n  Chart saved: sq9_icp_ltv.png")

# =============================================================================
# --- Phase 5 summary ---
# =============================================================================

print(f"\n{'=' * 70}")
print("PHASE 5 SUMMARY — MODEL (SQ8) + ICP (SQ9)")
print(f"{'=' * 70}")
print()
print(f"  SQ8 — Churn Risk Model")
print(f"    Logistic Regression AUC-ROC:   {lr_auc:.4f}")
print(f"    XGBoost AUC-ROC:               {xgb_auc:.4f}  (delta vs LR: {auc_delta:+.4f})")
print(f"    Winning model:                 {WINNING_MODEL}")
print(f"    Operating threshold (F2-max):  {best_thresh:.3f}")
print(f"    Precision at threshold:        {best_precision:.3f}")
print(f"    Recall at threshold:           {best_recall:.3f}")
print()
print(f"    Top 5 features by importance:")
for _, row in feature_importance.head(5).iterrows():
    print(f"      {row['feature']:<25}  {row['importance']:.4f}")
print()
print(f"    Risk tier distribution (active accounts, n={len(active_feat)}):")
for tier in ["High", "Medium", "Low"]:
    n = risk_counts.get(tier, 0)
    print(f"      {tier:<8}: {n:>4}  ({n / len(active_feat) * 100:.1f}%)")
print()
print(f"  SQ9 — ICP Profile")
print(f"    Overall avg realized LTV: ${avg_ltv_overall:,.0f}  "
      f"(gross margin {GROSS_MARGIN*100:.0f}% — assumed)")
print(f"    LTV by tier:")
for _, row in ltv_tier.iterrows():
    print(f"      {row['plan_tier']:<14}: avg LTV ${int(row['avg_ltv']):>10,}  "
          f"churn {row['churn_pct']:.1f}%")
print()
print(f"  Exports:")
print(f"    export/churn_risk_scores.csv  ({len(risk_export)} active accounts)")
print(f"    export/churn_model.pkl        ({WINNING_MODEL})")
print()
print(f"  Charts saved: sq8_model_performance, sq8_shap_summary (if XGB), sq9_icp_ltv")
print()
print(f"\n  Ready to proceed to Phase 6 (export): PENDING REVIEW")
print(f"{'=' * 70}\n")

# === Phase 6: Export ===
