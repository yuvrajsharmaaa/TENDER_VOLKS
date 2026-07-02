import fitz
from pathlib import Path

def generate_fixtures():
    fixtures_dir = Path("tests/fixtures")
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Digital PDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "TENDER NOTICE NO. RLY/2024/TN/0042")
    page.insert_text((100, 150), "Government of India - Ministry of Railways")
    doc.save(str(fixtures_dir / "sample_digital.pdf"))
    doc.close()
    print("Generated sample_digital.pdf")
    
    # 2. Bilingual PDF (Hindi + English)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "TENDER NOTICE NO. RLY/2024/TN/0042")
    # For bilingual, let's write some Devanagari text. 
    # fitz might need a font for true rendering of devanagari, but since this is just text extraction, let's write it.
    page.insert_text((100, 150), "रेल मंत्रालय / Ministry of Railways")
    doc.save(str(fixtures_dir / "sample_bilingual.pdf"))
    doc.close()
    print("Generated sample_bilingual.pdf")

    # 3. Scanned PDF (we can just copy sample_digital.pdf as a dummy)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "SCANNED TENDER DOCUMENT")
    page.insert_text((100, 150), "This behaves like a scanned document.")
    doc.save(str(fixtures_dir / "sample_scanned.pdf"))
    doc.close()
    print("Generated sample_scanned.pdf")

if __name__ == "__main__":
    generate_fixtures()
