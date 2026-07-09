import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.pdf_link_extractor import extract_links_and_mentions

def run_extraction_test():
    # Find a sample file to run against
    sample_dir = PROJECT_ROOT / "sample_files"
    samples = list(sample_dir.glob("*.pdf"))
    
    if not samples:
        print("[ERROR] No sample PDF files found in sample_files/")
        return
        
    # Take the first sample file
    target_pdf = samples[0]
    print(f"[TEST] Running extraction on target PDF: {target_pdf.name}")
    
    # Run the extraction (this will print the child file extraction summary)
    links, mentions = extract_links_and_mentions(str(target_pdf))
    
    print("[TEST] Run completed. Check the output above for the debug summary.")

if __name__ == "__main__":
    run_extraction_test()
