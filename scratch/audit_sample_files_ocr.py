import sys
from pathlib import Path

# Add backend to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid

def main():
    sample_dir = root_dir / "sample_files"
    if not sample_dir.exists():
        print(f"Sample directory not found: {sample_dir}")
        return

    pdf_files = list(sample_dir.glob("*.pdf")) + list(sample_dir.glob("**/*.pdf"))
    # Deduplicate paths
    pdf_files = list(dict.fromkeys(pdf_files))

    print(f"=== AUDITING {len(pdf_files)} PDF FILES IN sample_files/ ===\n")

    total_pages = 0
    native_pages = 0
    ocr_pages = 0

    per_file_results = []

    scratch_pages_dir = root_dir / "scratch" / "audit_ocr_pages"
    scratch_pages_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdf_files:
        try:
            results = extract_pdf_text_hybrid(str(pdf_path), scratch_pages_dir)
            pdf_native = sum(1 for p in results if p.get("source") == "native")
            pdf_ocr = sum(1 for p in results if p.get("source") != "native")
            pdf_total = len(results)

            total_pages += pdf_total
            native_pages += pdf_native
            ocr_pages += pdf_ocr

            per_file_results.append({
                "filename": pdf_path.name,
                "total": pdf_total,
                "native": pdf_native,
                "ocr": pdf_ocr,
                "ocr_ratio": f"{pdf_ocr / pdf_total * 100:.1f}%" if pdf_total > 0 else "0%"
            })
        except Exception as e:
            per_file_results.append({
                "filename": pdf_path.name,
                "total": 0,
                "native": 0,
                "ocr": 0,
                "error": str(e)
            })

    print(f"{'Filename':<45} | {'Total Pages':<12} | {'Native (Digital)':<16} | {'OCR (Scanned)':<14} | {'OCR %':<8}")
    print("-" * 100)
    for res in per_file_results:
        if "error" in res:
            print(f"{res['filename']:<45} | ERROR: {res['error']}")
        else:
            print(f"{res['filename']:<45} | {res['total']:<12} | {res['native']:<16} | {res['ocr']:<14} | {res['ocr_ratio']:<8}")

    print("\n" + "=" * 100)
    print("=== SUMMARY STATISTICS ===")
    print(f"Total PDFs Audited:     {len(pdf_files)}")
    print(f"Total Pages Audited:    {total_pages}")
    print(f"Native Digital Pages:   {native_pages} ({native_pages / total_pages * 100:.2f}% of all pages)" if total_pages > 0 else "")
    print(f"OCR / Scanned Pages:    {ocr_pages} ({ocr_pages / total_pages * 100:.2f}% of all pages)" if total_pages > 0 else "")
    print("=" * 100)

if __name__ == "__main__":
    main()
