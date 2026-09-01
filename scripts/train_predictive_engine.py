import os
import sys
import yaml
import json
import logging
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
    precision_recall_curve,
    auc
)
from lightgbm import LGBMClassifier
import shap
import joblib

# Setup paths and logging
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env.dev")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("predictive_engine")

MIN_LINKED_COUNT = 600  # Hard halt threshold for Step 1


# =============================================================================
# STATISTICAL HELPERS: WILSON 95% CONFIDENCE INTERVAL
# =============================================================================
def wilson_ci(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """
    Computes Wilson score confidence interval for binomial proportions.
    Essential for small positive sample sizes (e.g. ~31 wins in holdout).
    """
    if n == 0:
        return 0.0, 0.0
    z = 1.96  # for 95% confidence
    p = k / n
    denom = 1 + z**2 / n
    centre_adj_prob = p + z**2 / (2 * n)
    adj_se = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    lower = max(0.0, (centre_adj_prob - adj_se) / denom)
    upper = min(1.0, (centre_adj_prob + adj_se) / denom)
    return float(lower), float(upper)


# =============================================================================
# STEP 0 — COMPANY PROFILE GATE
# =============================================================================
def load_and_validate_company_profile(profile_path: Path = ROOT_DIR / "config" / "company_profile.yaml") -> dict:
    logger.info("=== STEP 0: COMPANY PROFILE GATE ===")
    if not profile_path.exists():
        raise FileNotFoundError(f"Company profile not found at '{profile_path}'")
    
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f) or {}
        
    required_fields = [
        "company_name", "cin", "avg_annual_turnover", "turnover_years_covered",
        "msme_registered", "latest_net_worth", "max_bid_validity_tolerance_days"
    ]
    
    for field in required_fields:
        if field not in profile or profile[field] is None:
            raise ValueError(f"Step 0 Gate Failed: Profile field '{field}' is missing or None in {profile_path}")

    logger.info(f"Verified Company Profile: '{profile['company_name']}' (CIN: {profile['cin']})")
    logger.info(f"  Avg Annual Turnover: Rs. {profile['avg_annual_turnover']:,.2f} ({profile['turnover_years_covered']})")
    logger.info(f"  Latest Net Worth: Rs. {profile['latest_net_worth']:,.2f}")
    logger.info(f"  Max Bid Validity Tolerance: {profile['max_bid_validity_tolerance_days']} Days")
    logger.info(f"  Incumbent PSUs: {profile.get('incumbent_psu_list', [])}")
    return profile


# =============================================================================
# STEP 1 — DATA INGESTION & F_HARD ELIGIBILITY FILTERING
# =============================================================================
def load_and_filter_eligible_tenders(profile: dict, min_required: int = MIN_LINKED_COUNT) -> pd.DataFrame:
    logger.info("\n=== STEP 1: DATA INGESTION & F_HARD ELIGIBILITY GATE ===")
    db_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            o.tender_no,
            o.tender_id,
            o.outcome,
            CASE WHEN o.outcome = 'Won' THEN 1 ELSE 0 END AS is_won,
            o.label_source,
            i.tender_name,
            i.nit_number,
            i.organization,
            i.department,
            i.client,
            i.publish_date,
            i.bid_submission_end_date,
            i.bid_validity_days,
            i.tender_value,
            i.estimated_cost,
            i.emd_amount,
            i.emd_required,
            i.avg_annual_turnover_value,
            i.pbg_percentage,
            i.pbg_duration,
            i.pbg_required,
            i.sd_percentage,
            i.sd_required,
            i.max_ld_percentage,
            i.ld_required,
            i.technical_eligibility_age,
            i.delivery_time_supply,
            i.maf_required,
            i.reverse_auction_applicable,
            i.mse_purchase_preference,
            i.mii_purchase_preference,
            i.created_at AS extraction_timestamp
        FROM tender_outcomes o
        JOIN tender_information i ON o.tender_id = i.tender_id
        WHERE o.outcome IN ('Won', 'Lost');
    """
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    
    df = pd.DataFrame(rows)
    total_raw = len(df)
    logger.info(f"Loaded {total_raw} linked records from Postgres (Won: {(df['outcome'] == 'Won').sum()}, Lost: {(df['outcome'] == 'Lost').sum()})")
    
    if total_raw < min_required:
        raise RuntimeError(f"Step 1 Gate Failed: Only {total_raw} linked tenders found (expected >= {min_required}).")
        
    # Evaluate F_hard compliance for all tenders
    from backend.app.services.compliance.regulatory import (
        RegulatoryComplianceService,
        VendorProfile,
        ComplianceStatus
    )
    
    vendor = VendorProfile.from_yaml()
    service = RegulatoryComplianceService(default_profile=vendor)
    
    compliance_statuses = []
    for idx, row in df.iterrows():
        field_map = {
            "avg_annual_turnover_value_display": row["avg_annual_turnover_value"],
            "working_capital_value_display": None,
            "experience_criteria_years": row["technical_eligibility_age"],
            "pbg_percentage": row["pbg_percentage"],
            "pbg_required": row["pbg_required"],
            "bid_validity_days": row["bid_validity_days"],
            "required_documents": None,
            "mii_purchase_preference": row["mii_purchase_preference"],
        }
        resp = service.evaluate_compliance(row["tender_no"], field_map, vendor)
        compliance_statuses.append(resp.overall_status.value)
        
    df["compliance_status"] = compliance_statuses
    logger.info(f"F_hard Compliance Status Breakdown on N={total_raw}:")
    logger.info(df["compliance_status"].value_counts().to_dict())
    
    # Filter to QUALIFIED and NEEDS_REVIEW only (exclude true DISQUALIFIED)
    df_eligible = df[df["compliance_status"].isin(["QUALIFIED", "NEEDS_REVIEW"])].copy().reset_index(drop=True)
    disq_count = total_raw - len(df_eligible)
    logger.info(f"Filtered Backtest Population: N={total_raw} -> N={len(df_eligible)} eligible (Excluded {disq_count} DISQUALIFIED)")
    logger.info(f"Eligible distribution: Won: {(df_eligible['outcome'] == 'Won').sum()}, Lost: {(df_eligible['outcome'] == 'Lost').sum()}")
    return df_eligible


# =============================================================================
# STEP 2 — NUMERIC SANITIZATION & FIT-FEATURE ENGINEERING
# =============================================================================
def sanitize_and_engineer_features(df: pd.DataFrame, profile: dict) -> tuple[pd.DataFrame, list[str]]:
    logger.info("\n=== STEP 2: NUMERIC SANITIZATION & FIT-FEATURE ENGINEERING ===")
    
    # 1. Leak-Free Chronological Reference Date
    def resolve_date(row):
        for col in ['publish_date', 'bid_submission_end_date', 'extraction_timestamp']:
            val = row.get(col)
            if pd.notna(val) and val is not None:
                try:
                    return pd.to_datetime(val)
                except Exception:
                    pass
        t_no = str(row.get('tender_no', ''))
        if '2024' in t_no:
            return pd.to_datetime('2024-06-01')
        elif '2025' in t_no:
            return pd.to_datetime('2025-06-01')
        elif '2026' in t_no:
            return pd.to_datetime('2026-01-01')
        return pd.to_datetime('2025-01-01')

    df['reference_date'] = df.apply(resolve_date, axis=1)
    df = df.sort_values(by=['reference_date', 'tender_no']).reset_index(drop=True)
    
    # 2. Organization Name Normalization
    def clean_org_name(org_str):
        if not org_str or pd.isna(org_str):
            return "UNKNOWN"
        cleaned = str(org_str).upper().strip()
        for term in ["LTD", "LIMITED", "CORP", "CORPORATION", "GOVT", "GOVERNMENT OF INDIA"]:
            cleaned = cleaned.replace(term, "").strip()
        return cleaned[:30]

    df['org_clean'] = df['organization'].fillna(df['department']).apply(clean_org_name)
    
    # 3. Numeric Sanitization Pipeline for Tender Value: [10k, 100 Cr] + Clean Org Median Fallback
    MIN_TV = 10_000.0
    MAX_TV = 1_000_000_000.0  # 100 Crore

    raw_tv = pd.to_numeric(df['tender_value'], errors='coerce')
    raw_ec = pd.to_numeric(df['estimated_cost'], errors='coerce')
    comb_tv = raw_tv.combine_first(raw_ec)

    is_clean_tv = (comb_tv >= MIN_TV) & (comb_tv <= MAX_TV)
    clean_subset = df[is_clean_tv].copy()
    clean_subset['clean_val'] = comb_tv[is_clean_tv]
    org_medians = clean_subset.groupby('org_clean')['clean_val'].median().to_dict()
    global_median = clean_subset['clean_val'].median() if not clean_subset.empty else 4_315_000.0

    clean_tv_vals = []
    tv_imputed_flag = []
    for idx, row in df.iterrows():
        val = comb_tv.iloc[idx]
        if pd.notna(val) and MIN_TV <= val <= MAX_TV:
            clean_tv_vals.append(float(val))
            tv_imputed_flag.append(False)
        else:
            fallback = org_medians.get(row['org_clean'], global_median)
            if pd.isna(fallback) or fallback < MIN_TV:
                fallback = global_median
            clean_tv_vals.append(float(fallback))
            tv_imputed_flag.append(True)

    df['clean_tender_value'] = clean_tv_vals
    df['tender_value_imputed'] = tv_imputed_flag
    df['tender_value_imputed_num'] = df['tender_value_imputed'].astype(int)
    df['log_tender_value'] = np.log1p(df['clean_tender_value'])
    logger.info(f"Tender Value Sanitization: {sum(tv_imputed_flag)} imputed ({sum(tv_imputed_flag)/len(df)*100:.1f}%), {(~np.array(tv_imputed_flag)).sum()} clean extracted ({((~np.array(tv_imputed_flag)).sum()/len(df))*100:.1f}%)")

    # 4. Bid Validity Days bounded to [1, 365]
    raw_bv = pd.to_numeric(df['bid_validity_days'], errors='coerce')
    clean_median_bv = raw_bv[(raw_bv >= 1) & (raw_bv <= 365)].median()
    if pd.isna(clean_median_bv):
        clean_median_bv = 90.0
    df['bid_validity_days_bounded'] = raw_bv.clip(lower=1.0, upper=365.0).fillna(clean_median_bv)

    # 5. EMD Amount bounded to [0, 10 Cr] + Ratios
    company_turnover = float(profile["avg_annual_turnover"])
    raw_emd = pd.to_numeric(df['emd_amount'], errors='coerce').fillna(0.0)
    df['emd_amount_bounded'] = raw_emd.clip(lower=0.0, upper=100_000_000.0)
    df['log_emd_amount'] = np.log1p(df['emd_amount_bounded'])
    df['emd_ratio'] = df['emd_amount_bounded'] / company_turnover

    # 6. Turnover Ratios
    raw_to = pd.to_numeric(df['avg_annual_turnover_value'], errors='coerce').fillna(0.0)
    df['turnover_req_applicable'] = (raw_to > 0).astype(int)
    df['turnover_ratio'] = np.where(
        df['turnover_req_applicable'] == 1,
        raw_to / company_turnover,
        0.0
    )

    # 7. PBG, LD & Delivery
    df['pbg_percentage'] = pd.to_numeric(df['pbg_percentage'], errors='coerce').fillna(0.0)
    df['pbg_duration_months'] = pd.to_numeric(df['pbg_duration'], errors='coerce').fillna(0.0)
    df['max_ld_cap_percent'] = pd.to_numeric(df['max_ld_percentage'], errors='coerce').fillna(0.0)
    df['delivery_time_supply_days'] = pd.to_numeric(df['delivery_time_supply'], errors='coerce').fillna(0.0)

    # 8. MAF, Reverse Auction, MSME Matches
    df['maf_required_flag'] = df['maf_required'].astype(str).str.lower().isin(['yes', 'true', '1', 'mandatory']).astype(int)
    df['reverse_auction_flag'] = df['reverse_auction_applicable'].astype(str).str.lower().isin(['yes', 'true', '1', 'applicable']).astype(int)
    msme_registered = bool(profile.get("msme_registered", True))
    df['mse_preference_flag'] = df['mse_purchase_preference'].astype(str).str.lower().isin(['yes', 'true', '1']).astype(int)
    df['msme_match'] = ((df['mse_preference_flag'] == 1) & msme_registered).astype(int)

    # 9. REQUIRED DOMAIN FEATURES: is_incumbent_psu & authority_win_rate
    incumbent_psu_list = [p.upper().strip() for p in profile.get("incumbent_psu_list", [])]
    
    is_incumbent_psu_vals = []
    for idx, row in df.iterrows():
        org_c = str(row['org_clean']).upper()
        dept_c = str(row.get('department', '')).upper()
        client_c = str(row.get('client', '')).upper()
        match = any(psu in org_c or psu in dept_c or psu in client_c for psu in incumbent_psu_list)
        is_incumbent_psu_vals.append(1 if match else 0)
    df['is_incumbent_psu'] = is_incumbent_psu_vals

    # Strictly leak-free chronological rolling authority win rate
    auth_win_rates = []
    incumbent_buyer_status_vals = []
    for idx, row in df.iterrows():
        cur_dt = row['reference_date']
        cur_org = row['org_clean']
        prior_tenders = df[(df['reference_date'] < cur_dt) & (df['org_clean'] == cur_org)]
        if len(prior_tenders) > 0:
            win_rate = prior_tenders['is_won'].mean()
            prior_wins = prior_tenders['is_won'].sum()
        else:
            win_rate = 0.0
            prior_wins = 0
        auth_win_rates.append(float(win_rate))
        incumbent_buyer_status_vals.append(1 if prior_wins > 0 else 0)

    df['authority_win_rate'] = auth_win_rates
    df['incumbent_buyer_status'] = incumbent_buyer_status_vals

    feature_cols = [
        'emd_ratio',
        'log_tender_value',
        'tender_value_imputed_num',
        'turnover_ratio',
        'pbg_duration_months',
        'max_ld_cap_percent',
        'delivery_time_supply_days',
        'bid_validity_days_bounded',
        'log_emd_amount',
        'maf_required_flag',
        'reverse_auction_flag',
        'is_incumbent_psu',
        'authority_win_rate',
        'incumbent_buyer_status',
        'msme_match',
        'turnover_req_applicable'
    ]

    logger.info(f"Engineered Feature Matrix Shape: {df[feature_cols].shape}")
    logger.info(f"Feature set ({len(feature_cols)} features): {feature_cols}")
    return df, feature_cols


# =============================================================================
# STEP 3 — TEMPORAL VALIDATION: 5-FOLD WALK-FORWARD & STATIC HOLDOUT
# =============================================================================
def run_temporal_validation(df: pd.DataFrame, feature_cols: list[str]) -> dict:
    logger.info("\n=== STEP 3: TEMPORAL VALIDATION (5-FOLD WALK-FORWARD + STATIC HOLDOUT) ===")
    
    X = df[feature_cols]
    y = df['is_won'].values
    
    # ── 1. PRIMARY: 5-Fold TimeSeriesSplit Walk-Forward Validation ───────────
    logger.info("--- 1. PRIMARY: 5-FOLD TIMESERIESSPLIT WALK-FORWARD ---")
    tscv = TimeSeriesSplit(n_splits=5)
    
    fold_metrics = {
        'Win Precision': [],
        'Win Recall': [],
        'Win F1': [],
        'PR-AUC': [],
        'Loss Precision': [],
        'Loss Recall': [],
        'Loss F1': [],
        'Balanced Accuracy': [],
        'Macro F1': [],
        'ROC-AUC': [],
        'Val Win Rate (%)': []
    }
    
    fold_details = []
    fold_idx = 1
    for train_idx, val_idx in tscv.split(X):
        X_tr, X_va = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_va = y[train_idx], y[val_idx]
        
        val_win_rate = y_va.mean() * 100
        
        model = LGBMClassifier(
            class_weight="balanced",
            random_state=42,
            n_estimators=60,
            learning_rate=0.03,
            max_depth=4,
            min_child_samples=15,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.5,
            reg_lambda=1.0,
            verbose=-1
        )
        model.fit(X_tr, y_tr)
        
        y_pred = model.predict(X_va)
        y_prob = model.predict_proba(X_va)[:, 1]
        
        wp = precision_score(y_va, y_pred, pos_label=1, zero_division=0)
        wr = recall_score(y_va, y_pred, pos_label=1, zero_division=0)
        wf1 = f1_score(y_va, y_pred, pos_label=1, zero_division=0)
        
        prec_c, rec_c, _ = precision_recall_curve(y_va, y_prob)
        pr_auc_val = auc(rec_c, prec_c)
        
        lp = precision_score(y_va, y_pred, pos_label=0, zero_division=0)
        lr = recall_score(y_va, y_pred, pos_label=0, zero_division=0)
        lf1 = f1_score(y_va, y_pred, pos_label=0, zero_division=0)
        
        bal_acc = balanced_accuracy_score(y_va, y_pred)
        mac_f1 = f1_score(y_va, y_pred, average="macro", zero_division=0)
        roc_auc_val = roc_auc_score(y_va, y_prob)
        
        fold_metrics['Win Precision'].append(wp)
        fold_metrics['Win Recall'].append(wr)
        fold_metrics['Win F1'].append(wf1)
        fold_metrics['PR-AUC'].append(pr_auc_val)
        fold_metrics['Loss Precision'].append(lp)
        fold_metrics['Loss Recall'].append(lr)
        fold_metrics['Loss F1'].append(lf1)
        fold_metrics['Balanced Accuracy'].append(bal_acc)
        fold_metrics['Macro F1'].append(mac_f1)
        fold_metrics['ROC-AUC'].append(roc_auc_val)
        fold_metrics['Val Win Rate (%)'].append(val_win_rate)
        
        fold_info = {
            "fold": fold_idx,
            "train_size": len(X_tr),
            "val_size": len(X_va),
            "val_win_rate": val_win_rate,
            "win_precision": wp,
            "win_recall": wr,
            "win_f1": wf1,
            "pr_auc": pr_auc_val,
            "loss_precision": lp,
            "loss_recall": lr,
            "loss_f1": lf1,
            "balanced_accuracy": bal_acc,
            "macro_f1": mac_f1,
            "roc_auc": roc_auc_val
        }
        fold_details.append(fold_info)
        logger.info(
            f"Fold {fold_idx} (Train N={len(X_tr)}, Val N={len(X_va)}, Win Rate={val_win_rate:.1f}%): "
            f"Win F1={wf1:.4f} | PR-AUC={pr_auc_val:.4f} | Loss F1={lf1:.4f} | Bal Acc={bal_acc:.4f} | ROC-AUC={roc_auc_val:.4f}"
        )
        fold_idx += 1
        
    summary_metrics = {}
    print("\n" + "="*85)
    print(f"{'METRIC':<25} | {'MEAN':<12} | {'STD':<12} | {'WALK-FORWARD (MEAN +/- STD)'}")
    print("-" * 85)
    for m_name, vals in fold_metrics.items():
        m_mean = float(np.mean(vals))
        m_std = float(np.std(vals))
        summary_metrics[m_name] = {"mean": m_mean, "std": m_std}
        if "%" in m_name:
            print(f"{m_name:<25} | {m_mean:>10.2f}% | {m_std:>10.2f}% | {m_mean:.2f}% +/- {m_std:.2f}%")
        else:
            print(f"{m_name:<25} | {m_mean:>12.4f} | {m_std:>12.4f} | {m_mean:.4f} +/- {m_std:.4f}")
    print("="*85 + "\n")

    # ── 2. SECONDARY: Chronological 75/25 Static Holdout (N=165) ─────────────
    logger.info("--- 2. SECONDARY: CHRONOLOGICAL 75/25 STATISTICAL CONFIRMATION ---")
    split_idx = int(len(df) * 0.75)
    X_train_stat, X_test_stat = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train_stat, y_test_stat = y[:split_idx], y[split_idx:]
    df_test_stat = df.iloc[split_idx:].copy()

    stat_model = LGBMClassifier(
        class_weight="balanced",
        random_state=42,
        n_estimators=60,
        learning_rate=0.03,
        max_depth=4,
        min_child_samples=15,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.5,
        reg_lambda=1.0,
        importance_type='gain',
        verbose=-1
    )
    stat_model.fit(X_train_stat, y_train_stat)

    y_stat_pred = stat_model.predict(X_test_stat)
    y_stat_prob = stat_model.predict_proba(X_test_stat)[:, 1]

    cm_stat = confusion_matrix(y_test_stat, y_stat_pred)
    tn, fp, fn, tp = cm_stat.ravel()
    n_test = len(y_test_stat)
    n_wins = int(sum(y_test_stat))

    win_prec = precision_score(y_test_stat, y_stat_pred, pos_label=1, zero_division=0)
    win_rec = recall_score(y_test_stat, y_stat_pred, pos_label=1, zero_division=0)
    win_f1 = f1_score(y_test_stat, y_stat_pred, pos_label=1, zero_division=0)

    prec_c, rec_c, _ = precision_recall_curve(y_test_stat, y_stat_prob)
    pr_auc_stat = auc(rec_c, prec_c)
    roc_auc_stat = roc_auc_score(y_test_stat, y_stat_prob)
    bal_acc_stat = balanced_accuracy_score(y_test_stat, y_stat_pred)
    macro_f1_stat = f1_score(y_test_stat, y_stat_pred, average="macro", zero_division=0)

    loss_prec = precision_score(y_test_stat, y_stat_pred, pos_label=0, zero_division=0)
    loss_rec = recall_score(y_test_stat, y_stat_pred, pos_label=0, zero_division=0)
    loss_f1 = f1_score(y_test_stat, y_stat_pred, pos_label=0, zero_division=0)

    # Compute Wilson 95% Confidence Intervals
    prec_ci_low, prec_ci_high = wilson_ci(tp, tp + fp)
    rec_ci_low, rec_ci_high = wilson_ci(tp, tp + fn)
    acc_ci_low, acc_ci_high = wilson_ci(tp + tn, n_test)

    logger.info(f"Static Holdout Test Size N={n_test} (Wins: {n_wins}, Losses: {n_test - n_wins})")
    logger.info(f"Confusion Matrix: TN={tn}, FP={fp}, FN={fn}, TP={tp}")
    logger.info(f"  Win Precision    : {win_prec:.4f} (Wilson 95% CI: [{prec_ci_low:.4f}, {prec_ci_high:.4f}])")
    logger.info(f"  Win Recall       : {win_rec:.4f} (Wilson 95% CI: [{rec_ci_low:.4f}, {rec_ci_high:.4f}])")
    logger.info(f"  Win F1           : {win_f1:.4f}")
    logger.info(f"  PR-AUC           : {pr_auc_stat:.4f}")
    logger.info(f"  Loss Precision   : {loss_prec:.4f}")
    logger.info(f"  Loss Recall      : {loss_rec:.4f}")
    logger.info(f"  Loss F1          : {loss_f1:.4f}")
    logger.info(f"  Balanced Accuracy: {bal_acc_stat:.4f}")
    logger.info(f"  Macro F1         : {macro_f1_stat:.4f}")
    logger.info(f"  ROC-AUC          : {roc_auc_stat:.4f}")
    logger.info(f"  Accuracy         : {(tp+tn)/n_test:.4f} (Wilson 95% CI: [{acc_ci_low:.4f}, {acc_ci_high:.4f}])")

    # ── 3. SHAP EXPLAINABILITY & EXPORT ARTIFACTS ────────────────────────────
    logger.info("\n--- 3. SHAP EXPLAINABILITY & ARTIFACT EXPORT ---")
    os.makedirs(ROOT_DIR / "artifacts", exist_ok=True)
    
    explainer = shap.TreeExplainer(stat_model)
    shap_values = explainer.shap_values(X_test_stat)
    if isinstance(shap_values, list) and len(shap_values) == 2:
        shap_vals_class1 = shap_values[1]
    else:
        shap_vals_class1 = shap_values

    # Generate SHAP bar plot
    plt.figure(figsize=(10, 6))
    shap.summary_plot(shap_vals_class1, X_test_stat, plot_type="bar", show=False)
    plt.title("LightGBM Feature Importance (SHAP Gain)")
    plt.tight_layout()
    shap_bar_path = ROOT_DIR / "artifacts" / "shap_bar.png"
    plt.savefig(shap_bar_path, dpi=300)
    plt.close()

    # Generate top drivers for each test prediction
    df_test_stat['win_probability'] = y_stat_prob
    df_test_stat['predicted_outcome'] = np.where(y_stat_pred == 1, 'Won', 'Lost')
    
    top_drivers_list = []
    for row_idx in range(len(X_test_stat)):
        row_shap = shap_vals_class1[row_idx]
        top_indices = np.argsort(np.abs(row_shap))[::-1][:3]
        drivers = [
            f"{feature_cols[i]} ({X_test_stat.iloc[row_idx, i]:.2f}, SHAP {row_shap[i]:+.3f})"
            for i in top_indices
        ]
        top_drivers_list.append("; ".join(drivers))
    df_test_stat['top_3_drivers'] = top_drivers_list
    df_test_stat['full_narrative'] = [
        f"Predicted {df_test_stat.iloc[i]['predicted_outcome']} ({df_test_stat.iloc[i]['win_probability']*100:.1f}%) | "
        f"Drivers: {df_test_stat.iloc[i]['top_3_drivers']}"
        for i in range(len(df_test_stat))
    ]

    # Save test_predictions_explained.csv
    pred_path = ROOT_DIR / "artifacts" / "test_predictions_explained.csv"
    df_test_stat.to_csv(pred_path, index=False)
    logger.info(f"Saved test predictions with SHAP drivers to '{pred_path}'")

    # Save training_set_win_loss.csv
    train_export_path = ROOT_DIR / "artifacts" / "training_set_win_loss.csv"
    df.to_csv(train_export_path, index=False)
    logger.info(f"Saved complete training view dataset to '{train_export_path}'")

    # Fit full production model on all eligible data
    full_model = LGBMClassifier(
        class_weight="balanced",
        random_state=42,
        n_estimators=60,
        learning_rate=0.03,
        max_depth=4,
        min_child_samples=15,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.5,
        reg_lambda=1.0,
        importance_type='gain',
        verbose=-1
    )
    full_model.fit(X, y)

    # Save trained LightGBM model artifact
    model_artifact_path = ROOT_DIR / "artifacts" / "lgbm_win_predictor.joblib"
    joblib.dump({
        "model": full_model,
        "stat_model": stat_model,
        "feature_cols": feature_cols,
        "trained_at": datetime.utcnow().isoformat(),
        "n_samples": len(X),
        "n_train_stat": len(X_train_stat)
    }, model_artifact_path)
    logger.info(f"Saved trained LightGBM model to '{model_artifact_path}'")

    # Save model_comparison_cv.csv
    cv_df = pd.DataFrame(fold_details)
    cv_path = ROOT_DIR / "artifacts" / "model_comparison_cv.csv"
    cv_df.to_csv(cv_path, index=False)
    logger.info(f"Saved 5-fold CV metrics to '{cv_path}'")

    # Save temporal_validation_report.json
    report_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_dataset_rows": len(df),
        "eligible_dataset_rows": len(df),
        "feature_count": len(feature_cols),
        "features": feature_cols,
        "walk_forward_5fold_summary": summary_metrics,
        "static_holdout_165": {
            "test_size": n_test,
            "won_count": n_wins,
            "lost_count": n_test - n_wins,
            "win_precision": win_prec,
            "win_precision_wilson_ci": [prec_ci_low, prec_ci_high],
            "win_recall": win_rec,
            "win_recall_wilson_ci": [rec_ci_low, rec_ci_high],
            "win_f1": win_f1,
            "pr_auc": pr_auc_stat,
            "loss_precision": loss_prec,
            "loss_recall": loss_rec,
            "loss_f1": loss_f1,
            "balanced_accuracy": bal_acc_stat,
            "macro_f1": macro_f1_stat,
            "roc_auc": roc_auc_stat,
            "accuracy": (tp + tn) / n_test,
            "accuracy_wilson_ci": [acc_ci_low, acc_ci_high],
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}
        }
    }
    report_path = ROOT_DIR / "artifacts" / "temporal_validation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    logger.info(f"Saved full validation report JSON to '{report_path}'")

    return report_data


def main():
    profile = load_and_validate_company_profile()
    df_eligible = load_and_filter_eligible_tenders(profile)
    df_sanitized, feature_cols = sanitize_and_engineer_features(df_eligible, profile)
    report = run_temporal_validation(df_sanitized, feature_cols)
    logger.info("=== PREDICTIVE ENGINE TEMPORAL VALIDATION COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
