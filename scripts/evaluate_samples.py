import os
import sys
import time
import json
import shutil
from pathlib import Path

# Add project root to sys.path to allow imports when running directly as a script
sys.path.append(str(Path(__file__).resolve().parent.parent))

from ocr.pipeline import process_pdf
from shared.constants import STORAGE_ROOT

def evaluate():
    sample_dir = Path("sample_files")
    pdf_files = list(sample_dir.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found in sample_files")
        return
        
    print(f"Found {len(pdf_files)} PDF files.")
    
    results = []
    
    # Process first 3 PDFs to show performance/output quickly without freezing
    # We can process more if needed, but 3 is a good sample.
    for i, pdf_path in enumerate(pdf_files[:3]):
        job_id = f"eval_{i+1}_{int(time.time())}"
        print(f"\nProcessing {pdf_path.name} (Job: {job_id})...")
        start_time = time.time()
        
        try:
            # Copy PDF to job directory to match pipeline expectations
            job_dir = STORAGE_ROOT / "jobs" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            target_pdf_path = job_dir / pdf_path.name
            shutil.copy(pdf_path, target_pdf_path)
            
            pages = process_pdf(job_id, target_pdf_path)
            elapsed = time.time() - start_time
            
            # Read result JSON from the target directory
            result_path = job_dir / "ocr_result.json"
            
            with open(result_path, "r", encoding="utf-8") as f:
                res_data = json.load(f)
                
            results.append({
                "file_name": pdf_path.name,
                "status": "success",
                "pages": len(pages),
                "elapsed": elapsed,
                "text_blocks": res_data["summary"]["total_text_blocks"],
                "layout_regions": res_data["summary"]["total_layout_regions"],
                "job_id": job_id
            })
            print(f"Success! Processed {len(pages)} pages in {elapsed:.2f}s.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            elapsed = time.time() - start_time
            results.append({
                "file_name": pdf_path.name,
                "status": f"failed: {str(e)}",
                "pages": 0,
                "elapsed": elapsed,
                "text_blocks": 0,
                "layout_regions": 0,
                "job_id": job_id
            })
            print(f"Failed to process {pdf_path.name}: {e}")
            
    # Write evaluation report to artifacts
    report_path_str = os.environ.get(
        "EVAL_REPORT_PATH",
        "C:/Users/Asus/.gemini/antigravity-ide/brain/01495c95-c0e2-4238-af6d-b11bded049e0/evaluation_report.md"
    )
    report_path = Path(report_path_str)
    # Ensure directory exists
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Model Evaluation Report on Sample Tenders\n\n")
        f.write("| File Name | Status | Pages | Time (s) | Text Blocks | Layout Regions | Job ID |\n")
        f.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for r in results:
            f.write(f"| {r['file_name']} | {r['status']} | {r['pages']} | {r['elapsed']:.2f} | {r['text_blocks']} | {r['layout_regions']} | {r['job_id']} |\n")
            
    print("\nEvaluation completed. Report written to artifacts.")

if __name__ == "__main__":
    evaluate()

