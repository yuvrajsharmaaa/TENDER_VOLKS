import sys
import json
import fitz
from pathlib import Path

# Add backend to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


from backend.app.services.pdf_text_extractor import extract_pdf_text_hybrid
from ocr.ocr_engine import OcrEngine

def main():
    pdf_path = r"C:\Users\Asus\Desktop\Tender_Volks\main\sample_files\GAIL INDIA JAIPUR NIDC.pdf"
    doc = fitz.open(pdf_path)
    print(f"=== PDF INFO: {pdf_path} ===")
    print(f"Total Page Count: {len(doc)}\n")

    pages_dir = root_dir / "scratch" / "gail_jaipur_pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    extracted_pages = extract_pdf_text_hybrid(pdf_path, pages_dir)

    print(f"=== EXTRACTED TEXT OUTPUT ({len(extracted_pages)} pages) ===\n")
    for p in extracted_pages:
        page_num = p['page']
        source = p['source']
        confidence = p['confidence']
        text = p['text'].strip()
        blocks = p['blocks']

        print(f"==================================================")
        print(f" PAGE {page_num} | Source: {source.upper()} | OCR/Confidence: {confidence}% | Total Blocks: {len(blocks)}")
        print(f"==================================================")
        print(text)
        print("\n" + "-"*50 + "\n")

    # Save full output text file to scratch
    full_output_txt = root_dir / "scratch" / "GAIL_INDIA_JAIPUR_NIDC_extracted_output.txt"
    with open(full_output_txt, "w", encoding="utf-8") as f:
        for p in extracted_pages:
            f.write(f"--- PAGE {p['page']} (Source: {p['source']}, Confidence: {p['confidence']}%) ---\n")
            f.write(p['text'] + "\n\n")

    print(f"Full text saved to: {full_output_txt}")

if __name__ == "__main__":
    main()
