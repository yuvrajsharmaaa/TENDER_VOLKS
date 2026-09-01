import os
import sys
import json
import logging
from pathlib import Path
import numpy as np
import pandas as pd

# Setup paths and environment
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from backend.app.services.pqc_recommendation_service import PQCRecommendationService, DEFAULT_WEIGHTS
from backend.app.services.compliance.regulatory import VendorProfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_pqc")


def compute_ranking_metrics(df_ranked: pd.DataFrame, is_won_col: str = "is_won") -> dict:
    """
    Computes Precision@K and Recall@K metrics for a ranked DataFrame.
    """
    total_wins = int(df_ranked[is_won_col].sum())
    total_count = len(df_ranked)
    baseline_win_rate = total_wins / float(total_count) if total_count > 0 else 0.0

    k_values = [5, 10, 20, 50, 100]
    metrics = {
        "total_tenders": total_count,
        "total_wins": total_wins,
        "baseline_win_rate": baseline_win_rate,
        "precision_at_k": {},
        "recall_at_k": {},
        "wins_at_k": {}
    }

    for k in k_values:
        top_k = df_ranked.head(k)
        wins_in_k = int(top_k[is_won_col].sum())
        prec_k = wins_in_k / float(k)
        rec_k = wins_in_k / float(total_wins) if total_wins > 0 else 0.0
        
        metrics["precision_at_k"][f"P@{k}"] = prec_k
        metrics["recall_at_k"][f"R@{k}"] = rec_k
        metrics["wins_at_k"][f"Wins@{k}"] = wins_in_k

    return metrics


def main():
    logger.info("=" * 80)
    logger.info("PQC RECOMMENDATION SYSTEM — DAY 1 OFFLINE DIAGNOSTIC EVALUATION")
    logger.info("=" * 80)

    # 1. Load 657 Labeled Training View Dataset
    csv_path = ROOT_DIR / "artifacts" / "training_set_win_loss.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Required dataset '{csv_path}' not found. Run scripts/train_predictive_engine.py first.")

    df = pd.read_csv(csv_path)
    total_rows = len(df)
    df["is_won"] = (df["outcome"] == "Won").astype(int)
    total_wins = df["is_won"].sum()
    baseline = total_wins / float(total_rows)

    logger.info(f"Loaded N={total_rows} labeled tenders (Wins: {total_wins}, Losses: {total_rows - total_wins}, Win Rate: {baseline:.2%})")

    # 2. Initialize PQC Recommendation Service
    service = PQCRecommendationService()
    logger.info(f"Active Weights: {service.weights}")

    # 3. Score all tenders across Signals 1, 2, 3 (Groq defaults to 0.50 offline)
    logger.info(f"Scoring all {total_rows} tenders offline...")
    scored_records = []
    
    for idx, row in df.iterrows():
        tender_dict = row.to_dict()
        # Compute org rolling win rate if available from pre-engineered features
        org_win_rate = float(row.get("authority_win_rate") or 0.0)
        incumbent_buyer = int(row.get("incumbent_buyer_status") or 0)
        
        scored = service.score_single_tender(
            tender_dict,
            include_groq=False,
            org_win_rate=org_win_rate,
            incumbent_buyer=incumbent_buyer
        )
        scored["is_won"] = int(row["is_won"])
        scored_records.append(scored)

    df_scored = pd.DataFrame([
        {
            "tender_no": s["tender_no"],
            "tender_name": s["tender_name"],
            "organization": s["organization"],
            "tender_value": s["tender_value"],
            "is_won": s["is_won"],
            "compliance_score": s["score_decomposition"]["compliance_score"],
            "compliance_status": s["score_decomposition"]["compliance_status"],
            "ml_win_prob": s["score_decomposition"]["ml_win_prob"],
            "similarity_score": s["score_decomposition"]["similarity_score"],
            "groq_fit_score": s["score_decomposition"]["groq_fit_score"],
            "composite_score": s["composite_score"],
        }
        for s in scored_records
    ])

    # 4. Rank by Composite Score
    df_composite_ranked = df_scored.sort_values(by="composite_score", ascending=False).reset_index(drop=True)
    comp_metrics = compute_ranking_metrics(df_composite_ranked)

    # 5. Component Ablation Comparison
    df_comp_only = df_scored.sort_values(by="compliance_score", ascending=False).reset_index(drop=True)
    comp_only_metrics = compute_ranking_metrics(df_comp_only)

    df_ml_only = df_scored.sort_values(by="ml_win_prob", ascending=False).reset_index(drop=True)
    ml_only_metrics = compute_ranking_metrics(df_ml_only)

    df_sim_only = df_scored.sort_values(by="similarity_score", ascending=False).reset_index(drop=True)
    sim_only_metrics = compute_ranking_metrics(df_sim_only)

    # 6. Display Diagnostic Comparison Table
    print("\n" + "=" * 95)
    print(f"{'RANKING STRATEGY':<30} | {'P@5':<8} | {'P@10':<8} | {'P@20':<8} | {'P@50':<8} | {'R@50':<8} | {'STATUS'}")
    print("-" * 95)
    print(f"{'Random Baseline (19.48%)':<30} | {baseline:>6.1%} | {baseline:>6.1%} | {baseline:>6.1%} | {baseline:>6.1%} | {50*baseline/total_wins:>6.1%} | Reference")
    print(f"{'Compliance Only (S1)':<30} | {comp_only_metrics['precision_at_k']['P@5']:>6.1%} | {comp_only_metrics['precision_at_k']['P@10']:>6.1%} | {comp_only_metrics['precision_at_k']['P@20']:>6.1%} | {comp_only_metrics['precision_at_k']['P@50']:>6.1%} | {comp_only_metrics['recall_at_k']['R@50']:>6.1%} | Ablation")
    print(f"{'ML Win Prob Only (S2)':<30} | {ml_only_metrics['precision_at_k']['P@5']:>6.1%} | {ml_only_metrics['precision_at_k']['P@10']:>6.1%} | {ml_only_metrics['precision_at_k']['P@20']:>6.1%} | {ml_only_metrics['precision_at_k']['P@50']:>6.1%} | {ml_only_metrics['recall_at_k']['R@50']:>6.1%} | Ablation")
    print(f"{'Qdrant Similarity Only (S3)':<30} | {sim_only_metrics['precision_at_k']['P@5']:>6.1%} | {sim_only_metrics['precision_at_k']['P@10']:>6.1%} | {sim_only_metrics['precision_at_k']['P@20']:>6.1%} | {sim_only_metrics['precision_at_k']['P@50']:>6.1%} | {sim_only_metrics['recall_at_k']['R@50']:>6.1%} | Ablation")
    print("-" * 95)
    
    p10 = comp_metrics['precision_at_k']['P@10']
    p20 = comp_metrics['precision_at_k']['P@20']
    gate_passed = (p10 >= 0.30) and (p20 >= 0.25)
    gate_str = "PASSED [GATE OK]" if gate_passed else "FAILED [FIX WEIGHTS]"

    print(f"{'* REVISED COMPOSITE (35/35/15/15)':<30} | {comp_metrics['precision_at_k']['P@5']:>6.1%} | {p10:>6.1%} | {p20:>6.1%} | {comp_metrics['precision_at_k']['P@50']:>6.1%} | {comp_metrics['recall_at_k']['R@50']:>6.1%} | {gate_str}")
    print("=" * 95 + "\n")

    # 7. Print Top-10 Recommended Tenders Preview
    print("Top 10 Ranked Tenders Preview:")
    print("-" * 110)
    print(f"{'Rank':<5} | {'Tender No':<28} | {'Buyer Org':<22} | {'Comp':<6} | {'Sim':<6} | {'ML':<6} | {'Composite':<10} | {'Outcome'}")
    print("-" * 110)
    for idx, row in df_composite_ranked.head(10).iterrows():
        outcome_str = "WON [OK]" if row['is_won'] == 1 else "LOST [x]"
        print(
            f"#{idx+1:<4} | {row['tender_no'][:28]:<28} | {row['organization'][:22]:<22} | "
            f"{row['compliance_score']:>4.2f} | {row['similarity_score']:>4.2f} | {row['ml_win_prob']:>4.2f} | "
            f"{row['composite_score']:>8.4f}   | {outcome_str}"
        )
    print("-" * 110)

    # 8. Save evaluation report
    eval_report = {
        "dataset_rows": total_rows,
        "dataset_wins": int(total_wins),
        "baseline_win_rate": float(baseline),
        "weights": service.weights,
        "composite_metrics": comp_metrics,
        "ablation_metrics": {
            "compliance_only": comp_only_metrics,
            "ml_only": ml_only_metrics,
            "similarity_only": sim_only_metrics
        },
        "day1_gate_passed": gate_passed,
        "p10_actual": float(p10),
        "p10_threshold": 0.30,
        "p20_actual": float(p20),
        "p20_threshold": 0.25
    }

    report_path = ROOT_DIR / "artifacts" / "pqc_evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2)
    logger.info(f"Saved evaluation report to '{report_path}'")

    if not gate_passed:
        logger.error(f"Day 1 Gate Failed: P@10={p10:.1%} (target >= 30.0%), P@20={p20:.1%} (target >= 25.0%)")
        sys.exit(1)
    else:
        logger.info(f"Day 1 Gate Passed! P@10={p10:.1%} >= 30%, P@20={p20:.1%} >= 25%. Ready for Day 2.")


if __name__ == "__main__":
    main()
