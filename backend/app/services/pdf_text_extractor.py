import fitz
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
    - Denoise filtering
    - Grayscale binarization thresholding
    """
    try:
        with Image.open(img_path) as img:
            # 1. Convert to grayscale
            gray = img.convert("L")
            
            # 2. Contrast enhancement
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(2.0)
            
            # 3. Simple denoise filter
            denoised = enhanced.filter(ImageFilter.SMOOTH)
            
            # 4. Adaptive thresholding via numpy
            arr = np.array(denoised)
            # Use mean thresholding
            threshold = int(arr.mean()) if arr.size > 0 else 127
            binarized = np.where(arr > threshold, 255, 0).astype(np.uint8)
            
            # Save preprocessed image
            processed_img = Image.fromarray(binarized)
            processed_path = img_path.parent / f"preprocessed_{img_path.name}"
            processed_img.save(processed_path)
            return processed_path
    except Exception as e:
        print(f"OCR preprocessing warning: {e}. Falling back to original image.")
        return img_path

def extract_pdf_text_hybrid(pdf_path: str, pages_dir: Path) -> List[Dict[str, Any]]:
    """
    Hybrid PDF extraction.
    Determines if a page is a text-based digital PDF or a scanned image page.
    Applies image preprocessing before running PaddleOCR on scanned pages.
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
                if 3.0 <= avg_word_len <= 15.0:
                    is_digital = True
            else:
                is_digital = True
                
        if is_digital:
            results.append({
                "page": page_num + 1,
                "text": native_text,
                "source": "native",
                "confidence": 100.0,
                "blocks": []
            })
        else:
            # Scanned page detected -> render to image
            if not ocr_engine:
                ocr_engine = OcrEngine()
                
            zoom = 2.77  # ~200 DPI
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
