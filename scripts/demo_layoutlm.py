import os
import sys
import shutil
import json
from pathlib import Path

# Add project root to sys.path to allow imports when running directly as a script
sys.path.append(str(Path(__file__).resolve().parent.parent))

from ocr.pipeline import process_pdf
from backend.app.core.constants import STORAGE_ROOT

def run_demo():
    print("==================================================")
    print("Starting OCR + LayoutLM Pipeline Demo...")
    print("==================================================")
    
    sample_dir = Path("sample_files")
    pdf_files = list(sample_dir.glob("*.pdf"))
    if not pdf_files:
        print("Error: No PDF files found in sample_files/")
        sys.exit(1)
        
    # Select the first PDF
    pdf_path = pdf_files[0]
    job_id = "demo_layoutlm_eval"
    job_dir = STORAGE_ROOT / "jobs" / job_id
    
    # Ensure a clean job directory
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy PDF to job directory to align with core pipeline expectation
    target_pdf_path = job_dir / pdf_path.name
    print(f"Copying {pdf_path.name} to {target_pdf_path}...")
    shutil.copy(pdf_path, target_pdf_path)
    
    print("\nRunning OCR + LayoutLM processing (this might take a few moments on the first run to initialize models)...")
    try:
        # Run pipeline with run_layoutlm=True
        page_results = process_pdf(job_id=job_id, pdf_path=target_pdf_path, run_layoutlm=True)
        
        print("\n==================================================")
        print("Execution Completed Successfully!")
        print("==================================================")
        
        # Load and display the aggregate output
        result_file = job_dir / "ocr_result.json"
        with open(result_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        print(f"\nOriginal Filename: {data['original_filename']}")
        print(f"Total Pages Processed: {data['page_count']}")
        print(f"Total Processing Time: {data['total_processing_time_seconds']:.2f}s")
        print(f"Total Text Blocks: {data['summary']['total_text_blocks']}")
        print(f"Total Layout Regions: {data['summary']['total_layout_regions']}")
        
        # Load the first page detail
        page_one_json_path = job_dir / "pages" / "page_0001.json"
        if page_one_json_path.exists():
            with open(page_one_json_path, "r", encoding="utf-8") as f:
                page_one = json.load(f)
                
            print("\nPage 1 LayoutLM Preview:")
            preview = page_one.get("layoutlm_results", {}).get("layoutlm_inputs_preview", {})
            print(f"- Extracted Words count: {len(preview.get('words', []))}")
            print(f"- Snapshot of words: {preview.get('words', [])[:10]}")
            print(f"- Snapshot of normalized coordinates [x0, y0, x1, y1]: {preview.get('boxes', [])[:10]}")
            
            entities = page_one.get("layoutlm_results", {}).get("entities", [])
            print(f"\nPage 1 Extracted Entities ({len(entities)} found):")
            for idx, ent in enumerate(entities):
                print(f"  [{idx+1}] Text: '{ent['text']}'")
                print(f"      Label: {ent['label']}")
                print(f"      Normalized Box: {ent['box']}")
                print(f"      Confidence score placeholder: {ent['score']}")
                
            print(f"\nFull page JSON results written to: {page_one_json_path}")
            
    except Exception as e:
        print(f"\nPipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_demo()
