import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path to allow imports when running directly as a script
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.app.services.pdf_parent_ingest import ingest_parent_tender_pdf
from backend.app.core.constants import STORAGE_ROOT
from backend.app.services.tender_mapper import build_infosheet_data
from backend.app.services.info_sheet_generator import generate_info_sheet_csv


def run_gold_eval(
    tenders_dir: Optional[Path] = None,
    ground_truth_path: Optional[Path] = None,
    report_output_path: Optional[Path] = None
) -> Dict[str, Any]:
    if ground_truth_path is None:
        ground_truth_path = PROJECT_ROOT / "gold_standard" / "ground_truth.json"
    if report_output_path is None:
        report_output_path = PROJECT_ROOT / "gold_standard" / "last_eval_report.json"
    if tenders_dir is None:
        tenders_dir = PROJECT_ROOT / "gold_standard" / "tenders"

    if not ground_truth_path.exists():
        print(f"Error: Ground truth file not found at {ground_truth_path}")
        sys.exit(1)

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        ground_truth: Dict[str, Dict[str, Any]] = json.load(f)

    if not tenders_dir.exists() or not tenders_dir.is_dir():
        print(f"Error: Tenders directory not found at {tenders_dir}")
        sys.exit(1)

    pdf_files = list(tenders_dir.glob("*.pdf"))
    eval_results: List[Dict[str, Any]] = []

    match_count = 0
    total_fields_checked = 0

    print(f"\n[GOLD_EVAL] Starting evaluation against {len(ground_truth)} tenders in ground truth...")
    print(f"[GOLD_EVAL] Tenders directory: {tenders_dir}")

    for pdf_path in pdf_files:
        tender_id = pdf_path.stem
        if tender_id not in ground_truth:
            continue

        gt_fields = ground_truth[tender_id]
        if not gt_fields:
            continue

        print(f"\n--> Evaluating '{tender_id}' ({pdf_path.name})...")
        job_id = f"gold_{tender_id}_{int(time.time())}"
        job_dir = STORAGE_ROOT / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        target_pdf_path = job_dir / pdf_path.name
        shutil.copy(pdf_path, target_pdf_path)

        # 1. Run full production ingest pipeline (parent + ATC child discovery & resolution)
        result = ingest_parent_tender_pdf(
            job_id=job_id,
            pdf_path=target_pdf_path,
            original_filename=pdf_path.name
        )

        tender_detail_path = job_dir / "tender_detail.json"
        with open(tender_detail_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        sections = result.get("infoSheetSections", [])
        page_texts = result.get("rawTextPages", [])

        # 2. Run production build_infosheet_data with job_id for ATC child resolution
        infosheet_data = build_infosheet_data(sections, page_texts, job_id=job_id)

        # 3. Verify XLSX generation succeeds identically
        try:
            xlsx_path = job_dir / f"{job_id}_infosheet.xlsx"
            generate_info_sheet_csv(infosheet_data, xlsx_path)
        except Exception as e:
            print(f"    [ERROR] XLSX workbook generation failed: {e}")

        # 5. Evaluate extracted infosheet fields against ground truth
        for field_name, expected_val in gt_fields.items():
            total_fields_checked += 1
            if field_name not in infosheet_data:
                status = "MISSING"
                actual_val = None
            else:
                actual_val = infosheet_data[field_name]
                exp_str = str(expected_val).strip() if expected_val is not None else ""
                act_str = str(actual_val).strip() if actual_val is not None else ""
                if exp_str == act_str:
                    status = "MATCH"
                    match_count += 1
                else:
                    status = "MISMATCH"

            eval_results.append({
                "tender_id": tender_id,
                "field_name": field_name,
                "expected": expected_val,
                "actual": actual_val,
                "status": status,
            })

    accuracy_pct = (match_count / total_fields_checked * 100.0) if total_fields_checked > 0 else 0.0

    # Print summary table
    print("\n" + "=" * 115)
    print(f"{'TENDER ID':<28} | {'FIELD NAME':<32} | {'EXPECTED':<22} | {'ACTUAL':<22} | {'STATUS':<8}")
    print("=" * 115)
    for res in eval_results:
        exp_raw = str(res['expected']) if res['expected'] is not None else "None"
        act_raw = str(res['actual']) if res['actual'] is not None else "None"
        if len(exp_raw) > 20:
            exp_raw = exp_raw[:18] + ".."
        if len(act_raw) > 20:
            act_raw = act_raw[:18] + ".."
        exp_str = exp_raw.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
        act_str = act_raw.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
        print(f"{res['tender_id']:<28} | {res['field_name']:<32} | {exp_str:<22} | {act_str:<22} | {res['status']:<8}")
    print("=" * 115)
    print(f"Overall Accuracy: {accuracy_pct:.2f}% ({match_count}/{total_fields_checked} fields matched)\n")

    report_payload = {
        "summary": {
            "total_fields_checked": total_fields_checked,
            "match_count": match_count,
            "accuracy_percentage": accuracy_pct,
        },
        "results": eval_results,
    }

    report_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_output_path, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2, ensure_ascii=False)

    print(f"[GOLD_EVAL] Report saved to {report_output_path}")
    return report_payload


def main():
    parser = argparse.ArgumentParser(description="Evaluate extracted fields against ground truth.")
    parser.add_argument("--tenders-dir", type=Path, default=None, help="Directory containing tender PDF files")
    parser.add_argument("--ground-truth", type=Path, default=None, help="Path to ground_truth.json")
    args = parser.parse_args()

    run_gold_eval(tenders_dir=args.tenders_dir, ground_truth_path=args.ground_truth)


if __name__ == "__main__":
    main()
