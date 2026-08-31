import os
import sys
import yaml
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from dotenv import load_dotenv

import psycopg2
from psycopg2.extras import RealDictCursor

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, classification_report, roc_auc_score, confusion_matrix
)
from lightgbm import LGBMClassifier
import shap

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("predictive_engine")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env.dev")

# =============================================================================
# STEP 0 — COMPANY PROFILE & BASELINE CONFIG
# =============================================================================
def load_company_profile(config_path: Path = ROOT_DIR / "config" / "company_profile.yaml") -> dict:
    logger.info("=== STEP 0: COMPANY PROFILE & BASELINE CONFIG ===")
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f)
        
    required_keys = [
        "company_name", "cin", "avg_annual_turnover", "latest_net_worth",
        "msme_registered", "incumbent_psu_list"
    ]
    for key in required_keys:
        if key not in profile or profile[key] is None:
            raise ValueError(f"Missing mandatory profile key: '{key}'")
            
    logger.info(f"Loaded Profile: '{profile['company_name']}' (CIN: {profile['cin']})")
    logger.info(f"  Avg Annual Turnover: INR {profile['avg_annual_turnover']:,}")
    logger.info(f"  Latest Net Worth:     INR {profile['latest_net_worth']:,}")
    logger.info(f"  MSME Registered:      {profile['msme_registered']}")
    logger.info(f"  Incumbent PSU List:   {profile['incumbent_psu_list']}")
    return profile

# =============================================================================
# STEP 1 — CONFIRM BACKFILL STATUS
# =============================================================================
def confirm_backfill_status() -> pd.DataFrame:
    logger.info("\n=== STEP 1: CONFIRM BACKFILL STATUS ===")
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    
    query = """
        SELECT outcome, COUNT(*) 
        FROM tender_outcomes 
        WHERE tender_id IS NOT NULL 
        GROUP BY outcome;
    """
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    
    counts_df = pd.DataFrame(rows, columns=['outcome', 'count'])
    logger.info(f"PostgreSQL Linked Outcome Counts:\n{counts_df.to_string(index=False)}")
    
    total_linked = counts_df['count'].sum()
    logger.info(f"Total Linked Tenders in DB: {total_linked}")
    return counts_df

# =============================================================================
# STEP 2 — FIT-FEATURE ENGINEERING (PANDAS)
# =============================================================================
def load_and_engineer_features(profile: dict) -> tuple[pd.DataFrame, list]:
    logger.info("\n=== STEP 2: FIT-FEATURE ENGINEERING (PANDAS) ===")
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            o.tender_no,
            o.tender_id,
            o.outcome,
            CASE WHEN o.outcome = 'Won' THEN 1 ELSE 0 END AS is_won,
            i.tender_name,
            i.organization,
            i.department,
            i.publish_date,
            i.bid_submission_end_date,
            i.created_at,
            i.bid_validity_days,
            i.tender_value,
            i.emd_amount,
            i.emd_required,
            i.avg_annual_turnover_value,
            i.net_worth_value,
            i.pbg_duration,
            i.max_ld_percentage,
            i.delivery_time_supply,
            i.maf_required,
            i.reverse_auction_applicable,
            i.mse_purchase_preference
        FROM tender_outcomes o
        JOIN tender_information i ON o.tender_id = i.tender_id
        WHERE o.outcome IN ('Won', 'Lost');
    """
    cur.execute(query)
    rows = cur.fetchall()
    conn.close()
    
    df = pd.DataFrame(rows)
    logger.info(f"Loaded {len(df)} linked historical records from Postgres.")
    
    # 1. Chronological Date for Time-Series Ordering (Zero Leakage)
    def resolve_date(row):
        for col in ['publish_date', 'bid_submission_end_date', 'created_at']:
            val = row.get(col)
            if pd.notna(val) and val is not None:
                try:
                    return pd.to_datetime(val)
                except Exception:
                    pass
        return pd.to_datetime('2020-01-01')
        
    df['reference_date'] = df.apply(resolve_date, axis=1)
    df = df.sort_values(by=['reference_date', 'tender_no']).reset_index(drop=True)
    
    company_turnover = float(profile["avg_annual_turnover"])
    company_net_worth = float(profile["latest_net_worth"])
    msme_registered = bool(profile["msme_registered"])
    incumbent_psus = [p.upper().strip() for p in profile.get("incumbent_psu_list", [])]
    
    # 2. Fit Features Computation
    # 2.1 Turnover Ratio (Float)
    df['turnover_req_value'] = pd.to_numeric(df['avg_annual_turnover_value'], errors='coerce').fillna(0.0)
    df['turnover_req_applicable'] = (df['turnover_req_value'] > 0).astype(int)
    df['turnover_ratio'] = np.where(
        df['turnover_req_applicable'] == 1,
        df['turnover_req_value'] / company_turnover,
        0.0
    ).astype(float)
    
    # 2.2 Net Worth Ratio (Float)
    df['net_worth_req_value'] = pd.to_numeric(df['net_worth_value'], errors='coerce').fillna(0.0)
    df['net_worth_ratio'] = np.where(
        df['net_worth_req_value'] > 0,
        df['net_worth_req_value'] / company_net_worth,
        0.0
    ).astype(float)
    
    # 2.3 MSME Match (Category/Bool)
    mse_pref = df['mse_purchase_preference'].astype(str).str.lower().isin(['yes', 'true', '1'])
    df['msme_match'] = (mse_pref & msme_registered).astype(bool)
    
    # 2.4 Incumbent Advantage (Category/Bool)
    def check_incumbent_psu(row):
        org = str(row.get('organization') or row.get('department') or '').upper().strip()
        if not org:
            return False
        # Direct match or substring match in PSU list
        for psu in incumbent_psus:
            if psu in org:
                return True
        if 'POWERGRID' in org and ('PGETL' in incumbent_psus or 'POWERGRID' in incumbent_psus):
            return True
        return False
        
    df['incumbent_advantage'] = df.apply(check_incumbent_psu, axis=1).astype(bool)
    
    # 2.5 Other Core Procurement & Risk Features
    df['emd_amount_clean'] = pd.to_numeric(df['emd_amount'], errors='coerce').fillna(0.0)
    df['emd_required_flag'] = np.where(
        (df['emd_amount_clean'] > 0) | (df['emd_required'].astype(str).str.lower().isin(['yes', 'true', '1'])),
        1, 0
    )
    df['emd_ratio'] = np.where(
        df['emd_required_flag'] == 1,
        df['emd_amount_clean'] / company_turnover,
        0.0
    ).astype(float)
    df['log_emd_amount'] = np.log1p(np.maximum(df['emd_amount_clean'], 0.0)).astype(float)
    
    raw_tv = pd.to_numeric(df['tender_value'], errors='coerce').fillna(0.0)
    clean_tv = np.where(raw_tv > 1.0, raw_tv, 0.0)
    df['log_tender_value'] = np.log1p(clean_tv).astype(float)
    
    df['pbg_duration_months'] = pd.to_numeric(df['pbg_duration'], errors='coerce').fillna(0.0).astype(float)
    df['max_ld_cap_percent'] = pd.to_numeric(df['max_ld_percentage'], errors='coerce').fillna(0.0).astype(float)
    df['delivery_time_supply_days'] = pd.to_numeric(df['delivery_time_supply'], errors='coerce').fillna(0.0).astype(float)
    df['bid_validity_days'] = pd.to_numeric(df['bid_validity_days'], errors='coerce').fillna(0.0).astype(float)
    
    df['maf_required_flag'] = df['maf_required'].astype(str).str.lower().isin(['yes', 'true', '1']).astype(bool)
    df['reverse_auction_flag'] = df['reverse_auction_applicable'].astype(str).str.lower().isin(['yes', 'true', '1']).astype(bool)
    df['turnover_req_applicable'] = df['turnover_req_applicable'].astype(bool)
    
    # Cast all boolean features to 'category' dtype for optimal LightGBM handling
    category_cols = [
        'msme_match', 'incumbent_advantage', 'maf_required_flag',
        'reverse_auction_flag', 'turnover_req_applicable'
    ]
    for c in category_cols:
        df[c] = df[c].astype('category')
        
    feature_cols = [
        'turnover_ratio',
        'net_worth_ratio',
        'msme_match',
        'incumbent_advantage',
        'emd_ratio',
        'log_emd_amount',
        'log_tender_value',
        'pbg_duration_months',
        'max_ld_cap_percent',
        'delivery_time_supply_days',
        'bid_validity_days',
        'maf_required_flag',
        'reverse_auction_flag',
        'turnover_req_applicable'
    ]
    
    logger.info(f"Engineered Feature Matrix Shape: {df[feature_cols].shape}")
    logger.info(f"Feature Dtypes:\n{df[feature_cols].dtypes}")
    logger.info(f"Target Distribution: {df['outcome'].value_counts().to_dict()}")
    logger.info(f"Nulls across features:\n{df[feature_cols].isnull().sum()}")
    
    return df, feature_cols

# =============================================================================
# STEP 3 — CLASSIFIER TRAINING (LIGHTGBM & TIMESERIESSPLIT)
# =============================================================================
def train_and_evaluate_classifier(df: pd.DataFrame, feature_cols: list) -> dict:
    logger.info("\n=== STEP 3: CLASSIFIER TRAINING (LIGHTGBM & TIMESERIESSPLIT) ===")
    
    X = df[feature_cols].copy()
    y = df['is_won'].values
    
    tscv = TimeSeriesSplit(n_splits=5)
    
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
    
    fold_details = []
    
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[test_idx]
        y_tr, y_val = y[train_idx], y[test_idx]
        
        clf = LGBMClassifier(
            class_weight="balanced",
            random_state=42,
            n_estimators=50,
            learning_rate=0.03,
            max_depth=3,
            min_child_samples=20,
            subsample=0.7,
            colsample_bytree=0.7,
            reg_alpha=0.5,
            reg_lambda=1.0,
            verbose=-1
        )
        clf.fit(X_tr, y_tr)
        
        preds = clf.predict(X_val)
        probs = clf.predict_proba(X_val)[:, 1]
        
        rep = classification_report(y_val, preds, target_names=["Lost", "Won"], output_dict=True, zero_division=0)
        
        acc = accuracy_score(y_val, preds)
        auc = roc_auc_score(y_val, probs) if len(np.unique(y_val)) > 1 else 0.5
        
        cv_metrics['accuracy'].append(acc)
        cv_metrics['roc_auc'].append(auc)
        cv_metrics['precision_won'].append(rep['Won']['precision'])
        cv_metrics['recall_won'].append(rep['Won']['recall'])
        cv_metrics['f1_won'].append(rep['Won']['f1-score'])
        cv_metrics['precision_lost'].append(rep['Lost']['precision'])
        cv_metrics['recall_lost'].append(rep['Lost']['recall'])
        cv_metrics['f1_lost'].append(rep['Lost']['f1-score'])
        cv_metrics['macro_f1'].append(rep['macro avg']['f1-score'])
        
        fold_details.append({
            'fold': fold,
            'train_size': len(train_idx),
            'test_size': len(test_idx),
            'train_wins': int(np.sum(y_tr)),
            'test_wins': int(np.sum(y_val)),
            'acc': acc,
            'auc': auc,
            'won_f1': rep['Won']['f1-score'],
            'lost_f1': rep['Lost']['f1-score'],
            'macro_f1': rep['macro avg']['f1-score']
        })
        
        logger.info(
            f"Fold {fold}: Train={len(train_idx)} ({np.sum(y_tr)} Won), "
            f"Test={len(test_idx)} ({np.sum(y_val)} Won) | "
            f"Acc={acc:.3f}, ROC-AUC={auc:.3f}, Won F1={rep['Won']['f1-score']:.3f}, Lost F1={rep['Lost']['f1-score']:.3f}, Macro F1={rep['macro avg']['f1-score']:.3f}"
        )
        
    logger.info("\n=== 5-FOLD TIME-SERIES CV SUMMARY (MEAN ± STD) ===")
    for k, v in cv_metrics.items():
        logger.info(f"{k:<18}: {np.mean(v):.4f} ± {np.std(v):.4f} (range: [{np.min(v):.4f}, {np.max(v):.4f}])")
        
    # Fit Final Model on Train Splits (Fold 1-4) and Evaluate on Final Time-Series Test Split (Fold 5)
    splits = list(tscv.split(X))
    final_train_idx, final_test_idx = splits[-1]
    X_train_final, X_test_final = X.iloc[final_train_idx], X.iloc[final_test_idx]
    y_train_final, y_test_final = y[final_train_idx], y[final_test_idx]
    
    final_model = LGBMClassifier(
        class_weight="balanced",
        random_state=42,
        n_estimators=50,
        learning_rate=0.03,
        max_depth=3,
        min_child_samples=20,
        subsample=0.7,
        colsample_bytree=0.7,
        reg_alpha=0.5,
        reg_lambda=1.0,
        verbose=-1
    )
    final_model.fit(X_train_final, y_train_final)
    
    final_preds = final_model.predict(X_test_final)
    final_probs = final_model.predict_proba(X_test_final)[:, 1]
    
    logger.info("\n--- FINAL TIME-SERIES TEST FOLD PERFORMANCE ---")
    logger.info(f"Test Accuracy: {accuracy_score(y_test_final, final_preds):.4f}")
    logger.info(f"Test ROC-AUC:  {roc_auc_score(y_test_final, final_probs):.4f}")
    logger.info(f"Confusion Matrix:\n{confusion_matrix(y_test_final, final_preds)}")
    logger.info(f"Classification Report:\n{classification_report(y_test_final, final_preds, target_names=['Lost', 'Won'])}")
    
    return {
        'model': final_model,
        'X_train': X_train_final,
        'X_test': X_test_final,
        'y_train': y_train_final,
        'y_test': y_test_final,
        'idx_train': final_train_idx,
        'idx_test': final_test_idx,
        'cv_metrics': cv_metrics,
        'fold_details': fold_details
    }

# =============================================================================
# STEP 4 — SHAP EXPLAINABILITY & PROCUREMENT NARRATIVES
# =============================================================================
def generate_shap_explainability(model: LGBMClassifier, X_test: pd.DataFrame, df: pd.DataFrame, idx_test: np.ndarray, feature_cols: list):
    logger.info("\n=== STEP 4: SHAP EXPLAINABILITY ===")
    os.makedirs("artifacts", exist_ok=True)
    
    # Calculate SHAP values via LightGBM booster native TreeSHAP (pred_contrib=True)
    # This avoids numba / Windows Application Control security blocks while remaining mathematically exact
    shap_contrib = model.booster_.predict(X_test, pred_contrib=True)
    shap_values = shap_contrib[:, :-1]  # (N, n_features)
    base_value = shap_contrib[0, -1]    # bias log-odds
    
    # 1. Global Mean |SHAP| Feature Importance
    mean_abs_shap = np.mean(np.abs(shap_values), axis=0)
    feat_imp_df = pd.DataFrame({
        'feature': feature_cols,
        'mean_abs_shap': mean_abs_shap
    }).sort_values(by='mean_abs_shap', ascending=False).reset_index(drop=True)
    
    logger.info("\n--- GLOBAL SHAP FEATURE IMPORTANCE RANKING ---")
    for idx, r in feat_imp_df.iterrows():
        logger.info(f"{idx+1:>2}. {r['feature']:<28}: {r['mean_abs_shap']:.4f}")
        
    feat_imp_df.to_csv("artifacts/feature_importance.csv", index=False)
    
    # 2. Visualizations
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    # Bar Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(feat_imp_df['feature'][::-1], feat_imp_df['mean_abs_shap'][::-1], color='#1f77b4', edgecolor='none', height=0.65)
    ax.set_xlabel('Mean |SHAP Value| (Average Impact on Prediction Magnitude)', fontsize=11, fontweight='bold')
    ax.set_title('Global Feature Importance (TreeSHAP - Predictive Engine)', fontsize=13, fontweight='bold', pad=12)
    plt.tight_layout()
    plt.savefig("artifacts/shap_bar.png", dpi=300)
    plt.close()
    
    # Summary Distribution Plot
    fig, ax = plt.subplots(figsize=(11, 7))
    top_indices = np.argsort(mean_abs_shap)[::-1][:12]
    top_features = [feature_cols[i] for i in top_indices]
    
    for i, f_idx in enumerate(top_indices[::-1]):
        vals = shap_values[:, f_idx]
        y_pos = np.random.normal(i, 0.08, size=len(vals))
        raw_f_vals = X_test.iloc[:, f_idx].values
        # Normalize raw feature values for colormap
        if raw_f_vals.dtype.name == 'category':
            norm_c = raw_f_vals.astype(int)
        else:
            min_v, max_v = np.min(raw_f_vals), np.max(raw_f_vals)
            norm_c = (raw_f_vals - min_v) / (max_v - min_v + 1e-8)
        scatter = ax.scatter(vals, y_pos, c=norm_c, cmap='coolwarm', alpha=0.75, s=28, edgecolors='none')
        
    ax.set_yticks(range(len(top_features)))
    ax.set_yticklabels(top_features[::-1], fontsize=10, fontweight='bold')
    ax.set_xlabel('SHAP Value (Impact on Log-Odds of Winning: Positive = GO, Negative = NO GO)', fontsize=11, fontweight='bold')
    ax.set_title('SHAP Feature Impact Distribution (Test Fold)', fontsize=13, fontweight='bold', pad=12)
    ax.axvline(0, color='black', linestyle='--', linewidth=0.8, alpha=0.7)
    cbar = plt.colorbar(scatter, ax=ax, orientation='vertical', pad=0.02)
    cbar.set_label('Relative Feature Value (Low to High)', fontsize=10)
    plt.tight_layout()
    plt.savefig("artifacts/shap_summary.png", dpi=300)
    plt.close()
    logger.info("Saved SHAP visual plots to artifacts/shap_summary.png and artifacts/shap_bar.png")
    
    # 3. Per-Prediction Explainability & Narrative Formatting
    test_sub_df = df.iloc[idx_test].copy().reset_index(drop=True)
    probs = model.predict_proba(X_test)[:, 1]
    preds = model.predict(X_test)
    
    def human_feature_phrase(feat_name, val, shap_val):
        direction = "pushing toward GO" if shap_val > 0 else "pushing toward NO GO"
        
        if feat_name == 'turnover_ratio':
            return f"turnover ratio ({val:.1f}x required, {direction})" if val > 0 else f"no turnover requirement ({direction})"
        elif feat_name == 'net_worth_ratio':
            return f"net worth ratio ({val:.1f}x required, {direction})" if val > 0 else f"no net worth requirement ({direction})"
        elif feat_name == 'incumbent_advantage':
            return f"incumbent PSU advantage ({direction})" if bool(val) else f"non-incumbent buyer ({direction})"
        elif feat_name == 'msme_match':
            return f"MSME purchase preference match ({direction})" if bool(val) else f"no MSME preference ({direction})"
        elif feat_name == 'emd_ratio':
            return f"EMD liquidity burden (ratio={val:.4f}, {direction})"
        elif feat_name == 'log_emd_amount':
            return f"EMD deposit scale (log={val:.1f}, {direction})"
        elif feat_name == 'log_tender_value':
            return f"contract monetary scale (log={val:.1f}, {direction})"
        elif feat_name == 'pbg_duration_months':
            return f"PBG lock-in duration ({val:.0f} months, {direction})"
        elif feat_name == 'max_ld_cap_percent':
            return f"Max LD/PRS penalty cap ({val:.1f}%, {direction})"
        elif feat_name == 'delivery_time_supply_days':
            return f"delivery supply timeline ({val:.0f} days, {direction})"
        elif feat_name == 'bid_validity_days':
            return f"bid validity window ({val:.0f} days, {direction})"
        elif feat_name == 'maf_required_flag':
            return f"OEM MAF required ({direction})" if bool(val) else f"no MAF required ({direction})"
        elif feat_name == 'reverse_auction_flag':
            return f"e-Reverse Auction enabled ({direction})" if bool(val) else f"no Reverse Auction ({direction})"
        elif feat_name == 'turnover_req_applicable':
            return f"turnover requirement mandated ({direction})" if bool(val) else f"turnover exempt ({direction})"
        else:
            return f"{feat_name} ({val}, {direction})"

    explained_records = []
    for i in range(len(X_test)):
        row_shap = shap_values[i]
        top_3_indices = np.argsort(np.abs(row_shap))[::-1][:3]
        
        pred_label = "GO" if preds[i] == 1 else "NO GO"
        actual_label = "Won" if test_sub_df.loc[i, 'is_won'] == 1 else "Lost"
        prob_win = probs[i]
        
        driver_phrases = []
        for f_idx in top_3_indices:
            f_name = feature_cols[f_idx]
            f_val = X_test.iloc[i, f_idx]
            s_val = row_shap[f_idx]
            driver_phrases.append(human_feature_phrase(f_name, f_val, s_val))
            
        narrative = f"Predicted {pred_label} (win_prob={prob_win:.2f}, actual={actual_label}), driven by: " + "; ".join(driver_phrases) + "."
        
        explained_records.append({
            'tender_no': test_sub_df.loc[i, 'tender_no'],
            'organization': test_sub_df.loc[i, 'organization'],
            'publish_date': str(test_sub_df.loc[i, 'reference_date']),
            'actual_outcome': actual_label,
            'predicted_decision': pred_label,
            'win_probability': round(prob_win, 4),
            'driver_1': driver_phrases[0] if len(driver_phrases) > 0 else '',
            'driver_2': driver_phrases[1] if len(driver_phrases) > 1 else '',
            'driver_3': driver_phrases[2] if len(driver_phrases) > 2 else '',
            'full_narrative': narrative
        })
        
    explained_df = pd.DataFrame(explained_records)
    explained_df.to_csv("artifacts/test_predictions_explained.csv", index=False)
    
    logger.info("\n--- SAMPLE TEST PREDICTIONS WITH SHAP EXPLANATIONS ---")
    for idx, r in explained_df.head(6).iterrows():
        logger.info(f"\nTender: {r['tender_no']} | Org: {r['organization']}")
        logger.info(f"  {r['full_narrative']}")
        
    return explained_df

# =============================================================================
# MAIN EXECUTION
# =============================================================================
def main():
    profile = load_company_profile()
    confirm_backfill_status()
    df, feature_cols = load_and_engineer_features(profile)
    res = train_and_evaluate_classifier(df, feature_cols)
    generate_shap_explainability(
        res['model'], res['X_test'], df, res['idx_test'], feature_cols
    )
    logger.info("\n=================================================================")
    logger.info("PREDICTIVE ENGINE PIPELINE (WEEK 5) COMPLETED SUCCESSFULLY!")
    logger.info("=================================================================")

if __name__ == '__main__':
    main()
