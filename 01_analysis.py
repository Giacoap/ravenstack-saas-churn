"""
ravenstack-saas-churn — análisis principal

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

EXPECTED_DATE_MIN = pd.Timestamp("2023-01-09")
EXPECTED_DATE_MAX = pd.Timestamp("2024-12-31")

# Expected row counts from scoping doc
EXPECTED_ROWS = {
    "accounts":        500,
    "subscriptions":   5_000,
    "feature_usage":   25_000,
    "support_tickets": 2_000,
    "churn_events":    600,
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

# satisfaction_score is null by design — not flagged as unexpected
EXPECTED_NULLS = {"support_tickets": {"satisfaction_score"}}

print(f"\nAll 5 tables loaded successfully.\n")

# =============================================================================
# --- Per-table quality checks ---
# =============================================================================

issues = []  # accumulate flag strings for summary

for name, (df, pk) in tables.items():
    print(f"\n{'-' * 60}")
    print(f"TABLE: {name.upper()}")
    print(f"{'-' * 60}")

    # Shape
    expected = EXPECTED_ROWS[name]
    actual = len(df)
    shape_flag = " ← UNEXPECTED ROW COUNT" if actual != expected else ""
    print(f"  Shape:        {actual:,} rows × {df.shape[1]} cols  (expected {expected:,}){shape_flag}")
    if shape_flag:
        issues.append(f"{name}: row count {actual} ≠ expected {expected}")

    # Duplicate PKs
    dup_count = df[pk].duplicated().sum()
    dup_flag = " ← DUPLICATES FOUND" if dup_count > 0 else ""
    print(f"  Duplicate PKs ({pk}): {dup_count}{dup_flag}")
    if dup_count > 0:
        issues.append(f"{name}: {dup_count} duplicate PKs in {pk}")

    # Nulls
    null_summary = df.isnull().sum()
    null_summary = null_summary[null_summary > 0]
    if null_summary.empty:
        print(f"  Nulls:        none")
    else:
        expected_null_cols = EXPECTED_NULLS.get(name, set())
        print(f"  Nulls:")
        for col, cnt in null_summary.items():
            pct = cnt / len(df) * 100
            tag = " (expected by design)" if col in expected_null_cols else " ← UNEXPECTED NULL"
            print(f"    {col}: {cnt} ({pct:.1f}%){tag}")
            if col not in expected_null_cols:
                issues.append(f"{name}.{col}: {cnt} unexpected nulls")

    # Date range
    for col in date_cols.get(name, []):
        col_min = df[col].min()
        col_max = df[col].max()
        out_of_range = (col_min < EXPECTED_DATE_MIN) or (col_max > EXPECTED_DATE_MAX)
        range_flag = " ← OUT OF EXPECTED RANGE" if out_of_range else ""
        print(f"  Date range ({col}): {col_min.date()} to {col_max.date()}{range_flag}")
        if out_of_range:
            issues.append(f"{name}.{col}: date range {col_min.date()}–{col_max.date()} outside expected window")

    # Boolean validity
    bool_cols = [c for c in df.columns if df[c].dtype == object and
                 df[c].dropna().isin(["True", "False", True, False]).all()]
    # Also check actual bool dtype
    bool_cols_dtype = [c for c in df.columns if df[c].dtype == bool]
    for col in bool_cols_dtype:
        vals = df[col].unique()
        unexpected_vals = [v for v in vals if v not in [True, False]]
        if unexpected_vals:
            print(f"  Boolean anomaly ({col}): unexpected values {unexpected_vals} ← ANOMALY")
            issues.append(f"{name}.{col}: unexpected boolean values {unexpected_vals}")
        else:
            print(f"  Boolean ({col}): OK — values {sorted(str(v) for v in vals)}")

# =============================================================================
# --- Cross-table referential integrity ---
# =============================================================================

print(f"\n{'-' * 60}")
print("REFERENTIAL INTEGRITY")
print(f"{'-' * 60}")

def check_fk(child_name, child_col, parent_name, parent_col, child_df, parent_df):
    orphans = ~child_df[child_col].isin(parent_df[parent_col])
    count = orphans.sum()
    flag = " ← ORPHAN FKs FOUND" if count > 0 else ""
    print(f"  {child_name}.{child_col} → {parent_name}.{parent_col}: {count} orphan rows{flag}")
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

# MRR vs ARR consistency
# arr_amount should equal mrr_amount × 12 (±1% tolerance for rounding)
arr_expected = subscriptions["mrr_amount"] * 12
arr_diff_pct = ((subscriptions["arr_amount"] - arr_expected) / arr_expected).abs()
arr_consistent = (arr_diff_pct <= 0.01).sum()
arr_inconsistent = (arr_diff_pct > 0.01).sum()
arr_pct = arr_consistent / len(subscriptions) * 100
flag = " ← INCONSISTENCIES FOUND" if arr_inconsistent > 0 else ""
print(f"  MRR × 12 ≈ ARR (±1%): {arr_consistent:,} / {len(subscriptions):,} rows ({arr_pct:.1f}%){flag}")
if arr_inconsistent > 0:
    issues.append(f"subscriptions: {arr_inconsistent} rows where arr ≠ mrr × 12 (±1%)")

# is_reactivation count
reactivation_count = churn_events["is_reactivation"].sum()
reactivation_pct = reactivation_count / len(churn_events) * 100
print(f"  Reactivations in churn_events: {reactivation_count} ({reactivation_pct:.1f}%)  (expected ~10% = ~60)")

# satisfaction_score nulls
sat_nulls = support_tickets["satisfaction_score"].isnull().sum()
sat_null_pct = sat_nulls / len(support_tickets) * 100
print(f"  satisfaction_score nulls: {sat_nulls} ({sat_null_pct:.1f}%)  — by design, no imputation")

# Trial accounts
trial_count = accounts["is_trial"].sum()
trial_pct = trial_count / len(accounts) * 100
print(f"  Trial accounts (is_trial=True): {trial_count} ({trial_pct:.1f}%)  — excluded from churn rate & LTV")

# Planned expirations — end_date not null AND churn_flag = False (not churn events)
planned_exp = (subscriptions["end_date"].notna() & (subscriptions["churn_flag"] == False)).sum()
print(f"  Planned expirations (end_date set, churn_flag=False): {planned_exp} subscriptions — NOT churn events")

# Churn flag consistency: accounts.churn_flag vs churn_events coverage
# First-time churners only (exclude reactivations) in churn_events
first_churn_accounts = churn_events.loc[churn_events["is_reactivation"] == False, "account_id"].unique()
accounts_flagged_churned = accounts.loc[accounts["churn_flag"] == True, "account_id"].unique()

both = len(set(accounts_flagged_churned) & set(first_churn_accounts))
flag_only = len(set(accounts_flagged_churned) - set(first_churn_accounts))
event_only = len(set(first_churn_accounts) - set(accounts_flagged_churned))

print(f"  Churn flag consistency:")
print(f"    accounts.churn_flag=True:          {len(accounts_flagged_churned):>4} accounts")
print(f"    churn_events (non-reactivation):   {len(first_churn_accounts):>4} accounts")
print(f"    Matched (both):                    {both:>4} accounts")
print(f"    Flag set but no churn event:       {flag_only:>4}  {'← INVESTIGATE' if flag_only > 0 else ''}")
print(f"    Churn event but flag not set:      {event_only:>4}  {'← INVESTIGATE' if event_only > 0 else ''}")
if flag_only > 0:
    issues.append(f"accounts: {flag_only} accounts have churn_flag=True but no matching churn_events row")
if event_only > 0:
    issues.append(f"churn_events: {event_only} accounts have churn event but churn_flag=False in accounts")

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

proceed = "YES" if len(issues) == 0 else "PENDING REVIEW"
print(f"\n  Ready to proceed to Phase 2 (EDA): {proceed}")
print(f"{'=' * 70}\n")

# =============================================================================
# === Phase 2: EDA ===
# =============================================================================

# === Phase 3: Metric calculation ===

# === Phase 4: Analysis (mapped to SQ1–SQ9) ===

# === Phase 5 / Model: SQ8 — feature engineering + logistic regression + XGBoost ===

# === Phase 6 / ICP: SQ9 — LTV by segment ===

# === Phase 7: Export ===
