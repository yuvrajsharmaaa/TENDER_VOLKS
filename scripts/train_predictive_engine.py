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

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    roc_auc_score
)
from lightgbm import LGBMClassifier

# Setup paths and logging
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env.dev")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("predictive_engine")

MIN_LINKED_COUNT = 600  # Hard halt threshold for Step 1

# =============================================================================
# STEP 0 — COMPANY PROFILE GATE
# =============================================================================
def load_and_validate_company_profile(profile_path: Path = ROOT_DIR / "config" / "company_profile.yaml") -> dict:
    logger.info("=== STEP 0: COMPANY PROFILE GATE ===")
    if not profile_path.exists():
        raise FileNotFoundError(f"Company profile not found at '{profile_path}'")
    
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f)
        
    required_fields = [
        "company_name", "cin", "avg_annual_turnover", "turnover_years_covered",
        "msme_registered", "msme_category", "make_in_india_compliant", "oem_authorized_categories"
    ]
    
    for field in required_fields:
        if field not in profile or profile[field] is None:
            raise ValueError(f"Step 0 Gate Failed: Profile field '{field}' is missing or None in {profile_path}")
        if isinstance(profile[field], str) and profile[field].strip() == "":
            raise ValueError(f"Step 0 Gate Failed: Profile field '{field}' is an empty string in {profile_path}")
        if field == "avg_annual_turnover" and (not isinstance(profile[field], (int, float)) or profile[field] <= 0):
            raise ValueError(f"Step 0 Gate Failed: 'avg_annual_turnover' must be a positive number, got {profile[field]}")

    logger.info(f"Verified Company Profile: '{profile['company_name']}' (CIN: {profile['cin']})")
    logger.info(f"  Avg Annual Turnover: ₹{profile['avg_annual_turnover']:,.2f} ({profile['turnover_years_covered']})")
    logger.info(f"  MSME Registered: {profile['msme_registered']} ({profile['msme_category']})")
    logger.info(f"  Make In India Compliant: {profile['make_in_india_compliant']}")
    logger.info(f"  OEM Authorizations: {profile['oem_authorized_categories']}")
    return profile

# =============================================================================
# STEP 1 — CONFIRM BACKFILL STATUS & HARD HALT CHECK
# =============================================================================
def check_backfill_status_and_halt_if_insufficient(min_required: int = MIN_LINKED_COUNT):
    logger.info("\n=== STEP 1: CONFIRM BACKFILL STATUS ===")
    db_url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT outcome, COUNT(*) as count 
        FROM tender_outcomes 
        WHERE tender_id IS NOT NULL 
        GROUP BY outcome;
    """)
    rows = cur.fetchall()
    counts = {r['outcome']: r['count'] for r in rows}
    total_linked = sum(counts.values())
    
    cur.execute("""
        SELECT outcome, COUNT(*) as total_count 
        FROM tender_outcomes 
        WHERE outcome IN ('Won', 'Lost')
        GROUP BY outcome;
    """)
    total_labeled_rows = cur.fetchall()
    total_labeled = {r['outcome']: r['total_count'] for r in total_labeled_rows}
    
    conn.close()
    
    logger.info(f"Live Linked Outcomes: {counts} (Total linked: {total_linked})")
    logger.info(f"Total Labeled in DB:  {total_labeled} (Total labeled: {sum(total_labeled.values())})")
    
    if total_linked < min_required:
        msg = (
            f"\n[HARD HALT] Step 1 Gate Failed: Only {total_linked} linked tenders found "
            f"(expected >= {min_required}).\n"
            f"Won linked: {counts.get('Won', 0)} / {total_labeled.get('Won', 0)}\n"
            f"Lost linked: {counts.get('Lost', 0)} / {total_labeled.get('Lost', 0)}\n"
            f"Halting training to prevent biased model training on incomplete data."
        )
        logger.error(msg)
        raise RuntimeError(msg)
        
    logger.info(f"Step 1 Gate Passed: {total_linked} linked tenders ready for feature engineering.")
    return counts

# =============================================================================
# STEP 2 — FIT-FEATURE ENGINEERING
# =============================================================================
def load_and_engineer_features(profile: dict) -> pd.DataFrame:
    logger.info("\n=== STEP 2: FIT-FEATURE ENGINEERING ===")
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
    logger.info(f"Loaded {len(df)} linked records from Postgres.")
    
    company_turnover = float(profile["avg_annual_turnover"])
    msme_registered = bool(profile["msme_registered"])
    mii_compliant = bool(profile["make_in_india_compliant"])
    
    # 1. Reference date for leak-free chronological ordering
    def resolve_date(row):
        for col in ['publish_date', 'bid_submission_end_date', 'extraction_timestamp']:
            val = row.get(col)
            if pd.notna(val) and val is not None:
                try:
                    return pd.to_datetime(val)
                except Exception:
                    pass
        return pd.to_datetime('2020-01-01')

    df['reference_date'] = df.apply(resolve_date, axis=1)
    df = df.sort_values(by=['reference_date', 'tender_no']).reset_index(drop=True)
    
    # 2. Derive Fit Features
    # 2.1 Turnover Ratio & Indicator
    df['turnover_req_value'] = pd.to_numeric(df['avg_annual_turnover_value'], errors='coerce').fillna(0.0)
    df['turnover_req_applicable'] = (df['turnover_req_value'] > 0).astype(int)
    df['turnover_ratio'] = np.where(
        df['turnover_req_applicable'] == 1,
        df['turnover_req_value'] / company_turnover,
        0.0
    )
    
    # 2.2 EMD Ratio, Amount, & Indicator
    df['emd_amount_clean'] = pd.to_numeric(df['emd_amount'], errors='coerce').fillna(0.0)
    df['emd_required_flag'] = np.where(
        (df['emd_amount_clean'] > 0) | (df['emd_required'].astype(str).str.lower().isin(['yes', 'true', '1'])),
        1, 0
    )
    df['emd_ratio'] = np.where(
        df['emd_required_flag'] == 1,
        df['emd_amount_clean'] / company_turnover,
        0.0
    )
    df['log_emd_amount'] = np.log1p(np.maximum(df['emd_amount_clean'], 0.0))
    
    # 2.3 MSME Match (Tender offers MSE preference AND Company is MSME registered)
    df['mse_preference_flag'] = df['mse_purchase_preference'].astype(str).str.lower().isin(['yes', 'true', '1']).astype(int)
    df['msme_match'] = (df['mse_preference_flag'] == 1) & msme_registered
    df['msme_match'] = df['msme_match'].astype(int)
    
    # 2.4 MII Match (Tender offers MII preference AND Company is MII compliant)
    df['mii_preference_flag'] = df['mii_purchase_preference'].astype(str).str.lower().isin(['yes', 'true', '1']).astype(int)
    df['mii_match'] = (df['mii_preference_flag'] == 1) & mii_compliant
    df['mii_match'] = df['mii_match'].astype(int)
    
    # 2.5 Incumbent-Buyer Status (Strict leak-free chronological lookback on past wins with buyer)
    def clean_org_name(org_str):
        if not org_str or pd.isna(org_str):
            return "UNKNOWN"
        cleaned = str(org_str).upper().strip()
        # Normalization
        for term in ["LTD", "LIMITED", "CORP", "CORPORATION", "GOVT", "GOVERNMENT OF INDIA"]:
            cleaned = cleaned.replace(term, "").strip()
        return cleaned[:30]

    df['org_clean'] = df['organization'].fillna(df['department']).apply(clean_org_name)
    
    incumbent_status = []
    for idx, row in df.iterrows():
        cur_date = row['reference_date']
        cur_org = row['org_clean']
        if cur_org == "UNKNOWN" or cur_org == "":
            incumbent_status.append(0)
            continue
        # Look back strictly at prior won tenders before cur_date
        prior_wins = df[
            (df['reference_date'] < cur_date) & 
            (df['is_won'] == 1) & 
            (df['org_clean'] == cur_org)
        ]
        incumbent_status.append(1 if len(prior_wins) > 0 else 0)
    df['incumbent_buyer_status'] = incumbent_status
    
    # 2.6 PBG Indicator + Magnitude
    df['pbg_percentage_raw'] = pd.to_numeric(df['pbg_percentage'], errors='coerce').fillna(0.0)
    df['pbg_custom_specified'] = (df['pbg_percentage_raw'] > 0).astype(int)
    df['pbg_percentage'] = df['pbg_percentage_raw']
    df['pbg_duration_months'] = pd.to_numeric(df['pbg_duration'], errors='coerce').fillna(0.0)
    
    # 2.7 SD Indicator + Magnitude (Audited)
    df['sd_percentage_raw'] = pd.to_numeric(df['sd_percentage'], errors='coerce').fillna(0.0)
    df['sd_custom_specified'] = (df['sd_percentage_raw'] > 0).astype(int)
    df['sd_percentage'] = df['sd_percentage_raw']
    
    # 2.8 Max LD / PRS Cap Indicator + Magnitude (Audited)
    df['max_ld_percentage_raw'] = pd.to_numeric(df['max_ld_percentage'], errors='coerce').fillna(0.0)
    df['max_ld_custom_specified'] = (df['max_ld_percentage_raw'] > 0).astype(int)
    df['max_ld_cap_percent'] = df['max_ld_percentage_raw']
    
    # 2.9 Experience & Delivery
    df['technical_experience_years_req'] = pd.to_numeric(df['technical_eligibility_age'], errors='coerce').fillna(0.0)
    df['delivery_time_supply_days'] = pd.to_numeric(df['delivery_time_supply'], errors='coerce').fillna(0.0)
    
    # 2.10 MAF & Reverse Auction Flags
    df['maf_required_flag'] = df['maf_required'].astype(str).str.lower().isin(['yes', 'true', '1', 'mandatory']).astype(int)
    df['reverse_auction_flag'] = df['reverse_auction_applicable'].astype(str).str.lower().isin(['yes', 'true', '1', 'applicable']).astype(int)
    
    # 2.11 Tender Scale & Validity (Purged 1.0 stubs)
    raw_tv = pd.to_numeric(df['tender_value'], errors='coerce').fillna(
        pd.to_numeric(df['estimated_cost'], errors='coerce').fillna(0.0)
    )
    # Reject stubs <= 1.0
    clean_tv = np.where(raw_tv > 1.0, raw_tv, 0.0)
    df['tender_value_specified'] = (clean_tv > 0).astype(int)
    df['log_tender_value'] = np.log1p(clean_tv)
    df['bid_validity_days'] = pd.to_numeric(df['bid_validity_days'], errors='coerce').fillna(0.0)
    
    # Optimal regularized feature columns specification
    feature_cols = [
        'emd_ratio',
        'log_tender_value',
        'turnover_ratio',
        'pbg_duration_months',
        'max_ld_cap_percent',
        'delivery_time_supply_days',
        'bid_validity_days',
        'log_emd_amount',
        'maf_required_flag',
        'reverse_auction_flag',
        'incumbent_buyer_status',
        'turnover_req_applicable'
    ]
    
    logger.info(f"Engineered Feature Matrix Shape: {df[feature_cols].shape}")
    logger.info(f"Target distribution: {df['outcome'].value_counts().to_dict()}")
    logger.info(f"Null values across all features:\n{df[feature_cols].isnull().sum()}")
    
    return df, feature_cols

# =============================================================================
# STEP 3 — CLASSIFIER TRAINING & CROSS-VALIDATION
# =============================================================================
def train_and_evaluate_classifier(df: pd.DataFrame, feature_cols: list):
    logger.info("\n=== STEP 3: CLASSIFIER TRAINING ===")
    
    X = df[feature_cols].copy()
    y = df['is_won'].values
    
    # 1. Stratified 80/20 Train/Test Split
    X_train, X_test, y_train, y_test, idx_train, idx_test = train_test_split(
        X, y, df.index, test_size=0.20, stratify=y, random_state=42
    )
    
    logger.info(f"Train split: {len(X_train)} samples ({np.sum(y_train)} Won, {len(y_train) - np.sum(y_train)} Lost)")
    logger.info(f"Test split:  {len(X_test)} samples ({np.sum(y_test)} Won, {len(y_test) - np.sum(y_test)} Lost)")
    
    # Train Regularized LightGBM model
    model = LGBMClassifier(
        class_weight="balanced",
        random_state=42,
        n_estimators=50,
        learning_rate=0.03,
        max_depth=3,
        min_child_samples=25,
        subsample=0.7,
        colsample_bytree=0.7,
        reg_alpha=0.5,
        reg_lambda=1.0,
        importance_type='gain',
        verbose=-1
    )
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    acc = accuracy_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_prob)
    report_dict = classification_report(y_test, y_pred, target_names=["Lost", "Won"], output_dict=True)
    cm = confusion_matrix(y_test, y_pred)
    
    logger.info(f"\n--- HELD-OUT TEST SET PERFORMANCE ---")
    logger.info(f"Accuracy: {acc:.4f} | ROC-AUC: {roc_auc:.4f}")
    logger.info(f"Confusion Matrix:\n{cm}")
    logger.info(f"Classification Report:\n{classification_report(y_test, y_pred, target_names=['Lost', 'Won'])}")
    
    # 2. 5-Fold Stratified Cross-Validation
    logger.info("\n--- 5-FOLD STRATIFIED CROSS-VALIDATION ---")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_metrics = {
        'accuracy': [],
        'roc_auc': [],
        'precision_won': [],
        'recall_won': [],
        'f1_won': [],
        'precision_lost': [],
        'recall_lost': [],
        'f1_lost': [],
        'macro_f1': []
    }
    
    fold_idx = 1
    for tr_idx, val_idx in skf.split(X, y):
        X_tr, X_val = X.iloc[tr_idx], X.iloc[val_idx]
        y_tr, y_val = y[tr_idx], y[val_idx]
        
        fold_model = LGBMClassifier(
            class_weight="balanced",
            random_state=42,
            n_estimators=100,
            learning_rate=0.05,
            max_depth=5,
            min_child_samples=10,
            subsample=0.8,
            colsample_bytree=0.8,
            importance_type='gain',
            verbose=-1
        )
        fold_model.fit(X_tr, y_tr)
        
        y_val_pred = fold_model.predict(X_val)
        y_val_prob = fold_model.predict_proba(X_val)[:, 1]
        
        fold_acc = accuracy_score(y_val, y_val_pred)
        fold_auc = roc_auc_score(y_val, y_val_prob)
        fold_rep = classification_report(y_val, y_val_pred, target_names=["Lost", "Won"], output_dict=True)
        
        cv_metrics['accuracy'].append(fold_acc)
        cv_metrics['roc_auc'].append(fold_auc)
        cv_metrics['precision_won'].append(fold_rep['Won']['precision'])
        cv_metrics['recall_won'].append(fold_rep['Won']['recall'])
        cv_metrics['f1_won'].append(fold_rep['Won']['f1-score'])
        cv_metrics['precision_lost'].append(fold_rep['Lost']['precision'])
        cv_metrics['recall_lost'].append(fold_rep['Lost']['recall'])
        cv_metrics['f1_lost'].append(fold_rep['Lost']['f1-score'])
        cv_metrics['macro_f1'].append(fold_rep['macro avg']['f1-score'])
        
        logger.info(
            f"Fold {fold_idx}: Acc={fold_acc:.3f}, Won F1={fold_rep['Won']['f1-score']:.3f}, "
            f"Lost F1={fold_rep['Lost']['f1-score']:.3f}, ROC-AUC={fold_auc:.3f}"
        )
        fold_idx += 1
        
    logger.info("\n=== 5-FOLD CV SUMMARY (MEAN ± STD) ===")
    for metric_name, values in cv_metrics.items():
        logger.info(f"{metric_name:<16}: {np.mean(values):.4f} ± {np.std(values):.4f} (range: [{np.min(values):.4f}, {np.max(values):.4f}])")
        
    return {
        'model': model,
        'X_train': X_train,
        'X_test': X_test,
        'y_train': y_train,
        'y_test': y_test,
        'idx_test': idx_test,
        'y_pred': y_pred,
        'y_prob': y_prob,
        'test_metrics': {
            'accuracy': acc,
            'roc_auc': roc_auc,
            'confusion_matrix': cm,
            'report': report_dict
        },
        'cv_metrics': cv_metrics
    }

# =============================================================================
# STEP 4 — SHAP EXPLAINABILITY & PROCUREMENT INSIGHTS
# =============================================================================
def compute_shap_explanations(model_results: dict, df: pd.DataFrame, feature_cols: list):
    logger.info("\n=== STEP 4: SHAP EXPLAINABILITY ===")
    model = model_results['model']
    X_test = model_results['X_test']
    y_test = model_results['y_test']
    idx_test = model_results['idx_test']
    y_pred = model_results['y_pred']
    y_prob = model_results['y_prob']
    
    # 1. Native LightGBM TreeSHAP computation (pred_contrib=True)
    # Returns [n_samples, n_features + 1] where the last column is the base value / bias
    shap_contrib = model.booster_.predict(X_test, pred_contrib=True)
    sv_won = shap_contrib[:, :-1]
    base_value = shap_contrib[0, -1]
        
    os.makedirs(ROOT_DIR / "artifacts", exist_ok=True)
    
    # 1. Global Mean Absolute SHAP Ranking
    mean_abs_shap = np.mean(np.abs(sv_won), axis=0)
    shap_importance_df = pd.DataFrame({
        'feature': feature_cols,
        'mean_abs_shap': mean_abs_shap
    }).sort_values(by='mean_abs_shap', ascending=False).reset_index(drop=True)
    
    logger.info("\n--- GLOBAL SHAP FEATURE IMPORTANCE RANKING ---")
    for rank, row in shap_importance_df.iterrows():
        logger.info(f"{rank+1:2d}. {row['feature']:<30}: {row['mean_abs_shap']:.4f}")
        
    shap_importance_df.to_csv(ROOT_DIR / "artifacts" / "feature_importance.csv", index=False)
    
    # 2. Save Global SHAP Plots (Publication Quality)
    # 2a. Global Bar Plot
    top_n = min(15, len(feature_cols))
    top_shap = shap_importance_df.head(top_n).iloc[::-1]
    
    plt.figure(figsize=(10, 7))
    bars = plt.barh(top_shap['feature'], top_shap['mean_abs_shap'], color='#2563eb', alpha=0.85, edgecolor='#1d4ed8')
    plt.xlabel("Mean |SHAP Value| (Average Impact on Win Probability)", fontsize=11, fontweight='bold')
    plt.title(f"Global Feature Importance Ranking (Top {top_n} Features)", fontsize=13, fontweight='bold', pad=12)
    plt.grid(axis='x', linestyle='--', alpha=0.5)
    for bar in bars:
        w = bar.get_width()
        plt.text(w + 0.005, bar.get_y() + bar.get_height()/2, f"{w:.4f}", va='center', ha='left', fontsize=9, color='#1e293b')
    plt.tight_layout()
    plt.savefig(ROOT_DIR / "artifacts" / "shap_bar.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2b. Global Summary Beeswarm Plot
    plt.figure(figsize=(11, 8))
    sorted_features = shap_importance_df['feature'].head(top_n).tolist()
    y_positions = list(range(len(sorted_features)))[::-1]
    
    for y_pos, feat_name in zip(y_positions, sorted_features):
        feat_idx = feature_cols.index(feat_name)
        feat_vals = X_test[feat_name].values
        shap_vals = sv_won[:, feat_idx]
        
        # Normalize feature values to [0, 1] for color coding
        val_min, val_max = np.min(feat_vals), np.max(feat_vals)
        if val_max > val_min:
            norm_vals = (feat_vals - val_min) / (val_max - val_min)
        else:
            norm_vals = np.zeros_like(feat_vals) + 0.5
            
        jitter = np.random.normal(0, 0.08, size=len(shap_vals))
        sc = plt.scatter(
            shap_vals,
            [y_pos + j for j in jitter],
            c=norm_vals,
            cmap='coolwarm',
            alpha=0.75,
            edgecolors='none',
            s=35
        )
        
    plt.axvline(0, color='gray', linestyle='--', linewidth=1)
    plt.yticks(y_positions, sorted_features, fontsize=10)
    plt.xlabel("SHAP Value (Impact on Log-Odds of Winning Tender)", fontsize=11, fontweight='bold')
    plt.title(f"SHAP Summary Plot (Top {top_n} Features Impact Distribution)", fontsize=13, fontweight='bold', pad=12)
    cbar = plt.colorbar(sc, orientation='vertical', pad=0.02, shrink=0.7)
    cbar.set_label('Feature Value (Low → High)', fontsize=9, fontweight='bold')
    cbar.set_ticks([0.1, 0.9])
    cbar.set_ticklabels(['Low', 'High'])
    plt.grid(axis='x', linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(ROOT_DIR / "artifacts" / "shap_summary.png", dpi=300, bbox_inches='tight')
    plt.close()
    logger.info("Saved SHAP plots to artifacts/shap_summary.png and artifacts/shap_bar.png")
    
    # 3. Individual Prediction Explanations
    explanation_records = []
    test_df_subset = df.loc[idx_test].copy().reset_index(drop=True)
    
    for i in range(len(X_test)):
        row_feat = X_test.iloc[i]
        row_sv = sv_won[i]
        actual_outcome = "Won" if y_test[i] == 1 else "Lost"
        pred_outcome = "Won" if y_pred[i] == 1 else "Lost"
        win_prob = y_prob[i]
        
        # Sort features by absolute SHAP impact
        top_indices = np.argsort(np.abs(row_sv))[::-1][:3]
        
        driver_phrases = []
        for feat_idx in top_indices:
            feat_name = feature_cols[feat_idx]
            val = row_feat[feat_name]
            sv = row_sv[feat_idx]
            direction = "pushing toward Won" if sv > 0 else "pushing toward Lost"
            
            # Format human-readable procurement driver text
            if feat_name == 'turnover_ratio':
                desc = f"turnover ratio ({val:.2f}x required, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'incumbent_buyer_status':
                desc = f"{'has prior win with buyer' if val == 1 else 'no incumbent relationship'} ({direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'msme_match':
                desc = f"{'MSME preference matched' if val == 1 else 'no MSME match'} ({direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'mii_match':
                desc = f"{'MII preference matched' if val == 1 else 'no MII match'} ({direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'log_emd_amount' or feat_name == 'emd_ratio':
                desc = f"EMD burden (ratio={row_feat['emd_ratio']:.4f}, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'delivery_time_supply_days':
                desc = f"delivery timeline ({int(val)} days, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'technical_experience_years_req':
                desc = f"experience threshold ({int(val)} years, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'pbg_percentage':
                desc = f"PBG guarantee ({val:.1f}%, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'max_ld_cap_percent':
                desc = f"Max LD/PRS cap ({val:.1f}%, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'sd_percentage':
                desc = f"Security deposit ({val:.1f}%, {direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'maf_required_flag':
                desc = f"{'MAF mandatory' if val == 1 else 'MAF not required'} ({direction} [SHAP: {sv:+.3f}])"
            elif feat_name == 'reverse_auction_flag':
                desc = f"{'Reverse auction enabled' if val == 1 else 'No reverse auction'} ({direction} [SHAP: {sv:+.3f}])"
            else:
                desc = f"{feat_name} ({val:.2f}, {direction} [SHAP: {sv:+.3f}])"
            driver_phrases.append(desc)
            
        full_explanation = f"Predicted {pred_outcome} (win_prob={win_prob:.2f}), Actual: {actual_outcome}. Driven by: {'; '.join(driver_phrases)}"
        
        explanation_records.append({
            'tender_no': test_df_subset.loc[i, 'tender_no'],
            'tender_name': test_df_subset.loc[i, 'tender_name'],
            'organization': test_df_subset.loc[i, 'organization'],
            'actual_outcome': actual_outcome,
            'predicted_outcome': pred_outcome,
            'win_probability': round(win_prob, 4),
            'top_3_drivers': "; ".join(driver_phrases),
            'full_narrative': full_explanation
        })
        
    explanations_df = pd.DataFrame(explanation_records)
    explanations_df.to_csv(ROOT_DIR / "artifacts" / "test_predictions_explained.csv", index=False)
    
    logger.info("\n--- SAMPLE INDIVIDUAL PREDICTIONS WITH SHAP DRIVERS ---")
    for idx, row in explanations_df.head(5).iterrows():
        logger.info(f"\nTender: {row['tender_no']} | {str(row['tender_name'])[:40]}...")
        logger.info(f"  {row['full_narrative']}")
        
    return shap_importance_df, explanations_df

# =============================================================================
# MAIN PIPELINE EXECUTION
# =============================================================================
def run_predictive_engine_pipeline():
    logger.info("=================================================================")
    logger.info("WEEK 5: THE PREDICTIVE ENGINE (LightGBM & SHAP)")
    logger.info("=================================================================")
    
    # Step 0
    profile = load_and_validate_company_profile()
    
    # Step 1
    counts = check_backfill_status_and_halt_if_insufficient(MIN_LINKED_COUNT)
    
    # Step 2
    df, feature_cols = load_and_engineer_features(profile)
    
    # Step 3
    model_results = train_and_evaluate_classifier(df, feature_cols)
    
    # Step 4
    shap_importance, explanations = compute_shap_explanations(model_results, df, feature_cols)
    
    logger.info("\n=================================================================")
    logger.info("PREDICTIVE ENGINE PIPELINE COMPLETE!")
    logger.info("=================================================================")

if __name__ == '__main__':
    run_predictive_engine_pipeline()
