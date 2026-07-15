from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
from ocr.ocr_engine import OcrEngine
from typing import List, Dict, Any

def preprocess_image_for_ocr(img_path: Path) -> Path:
    """
    Performs lightweight image preprocessing for improved OCR accuracy:
    - Grayscale conversion
    - Contrast enhancement
    - Sharpening instead of blurring to keep character edges clean
    - Avoids global threshold binarization to let Tesseract do internal adaptive thresholding
    """
    try:
        with Image.open(img_path) as img:
            # 1. Convert to grayscale
            gray = img.convert("L")
            
            # 2. Contrast enhancement
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)
            
            # 3. Sharpening filter to make text borders crisp
            sharpened = enhanced.filter(ImageFilter.SHARPEN)
            
            # Save preprocessed image (as grayscale, letting Tesseract handle binarization)
            processed_path = img_path.parent / f"preprocessed_{img_path.name}"
            sharpened.save(processed_path)
            return processed_path
    except Exception as e:
        print(f"OCR preprocessing warning: {e}. Falling back to original image.")
        return img_path

def is_text_scrambled_or_garbage(text: str) -> bool:
    """
    Detects if native PDF text is scrambled or contains corrupted font mappings
    (e.g., (cid:X) codes or high non-alphanumeric ratio).
    """
    if not text:
        return True
    
    # Common PyMuPDF font corruption artifacts
    if text.count("(cid:") > 3:
        return True
        
    # Check alphanumeric ratio
    cleaned = text.strip()
    if not cleaned:
        return True
        
    total_len = len(cleaned)
    alnum_count = sum(1 for c in cleaned if c.isalnum() or c.isspace())
    if alnum_count / total_len < 0.6:
        return True
        
    return False

def cluster_words_into_cells(words, gap_threshold=15):
    if not words:
        return []
    words_sorted = sorted(words, key=lambda w: (w[1], w[0]))  # y, x
    cells, current = [], [words_sorted[0]]
    for w in words_sorted[1:]:
        prev = current[-1]
        same_line = abs(w[1] - prev[1]) < 5
        close_enough = (w[0] - prev[2]) < gap_threshold
        if same_line and close_enough:
            current.append(w)
        else:
            cells.append(current)
            current = [w]
    cells.append(current)
    return [
        {
            "text": " ".join(w[4] for w in cell),
            "confidence": 100.0,
            "bounding_box": {
                "x1": int(round(min(w[0] for w in cell))),
                "y1": int(round(min(w[1] for w in cell))),
                "x2": int(round(max(w[2] for w in cell))),
                "y2": int(round(max(w[3] for w in cell))),
            },
            "language_hint": "en",
        }
        for cell in cells
    ]

def extract_pdf_text_hybrid(pdf_path: str, pages_dir: Path) -> List[Dict[str, Any]]:
    import fitz
    """
    Hybrid PDF extraction.
    Determines if a page is a text-based digital PDF or a scanned image page.
    Applies image preprocessing before running Tesseract on scanned pages.
    """
    doc = fitz.open(pdf_path)
    ocr_engine = None
    results = []
    
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        native_text = page.get_text()
        
        # Advanced quality heuristics
        stripped = native_text.strip()
        words = stripped.split()
        word_count = len(words)
        
        is_digital = False
        if len(stripped) > 5 and word_count > 0:
            if word_count > 5:
                avg_word_len = len(stripped) / word_count
                if 3.0 <= avg_word_len <= 15.0 and not is_text_scrambled_or_garbage(native_text):
                    is_digital = True
            else:
                if not is_text_scrambled_or_garbage(native_text):
                    is_digital = True
                
        if is_digital:
            native_words = page.get_text("words")
            blocks = cluster_words_into_cells(native_words)
            results.append({
                "page": page_num + 1,
                "text": native_text,
                "source": "native",
                "confidence": 100.0,
                "blocks": blocks
            })
        else:
            # Scanned page detected -> render to image
            if not ocr_engine:
                ocr_engine = OcrEngine()
                
            zoom = 4.16  # ~300 DPI for high-precision character matching
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            pages_dir.mkdir(parents=True, exist_ok=True)
            img_path = pages_dir / f"page_{page_num + 1:04d}.png"
            pix.save(str(img_path))
            pix = None  # release memory
            
            # Preprocess image to enhance OCR accuracy
            preprocessed_path = preprocess_image_for_ocr(img_path)
            
            # Run OCR on preprocessed image
            blocks = ocr_engine.run(preprocessed_path)
            ocr_text = "\n".join([b.text for b in blocks])
            avg_conf = sum([b.confidence for b in blocks]) / len(blocks) if blocks else 0.0
            
            # Clean up temporary preprocessed image file
            if preprocessed_path != img_path:
                try:
                    preprocessed_path.unlink()
                except Exception:
                    pass
            
            results.append({
                "page": page_num + 1,
                "text": ocr_text,
                "source": "ocr",
                "confidence": round(avg_conf * 100, 2),
                "blocks": [
                    {
                        "block_id": b.block_id,
                        "text": b.text,
                        "confidence": b.confidence,
                        "bounding_box": b.bounding_box
                    } for b in blocks
                ]
            })
            
    doc.close()
    return results

