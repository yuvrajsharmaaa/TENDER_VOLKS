"""
build_dapt_corpus.py
====================
Production-Grade Domain-Adaptive Pretraining (DAPT) Corpus Builder for Tender Documents.

Features:
1. Multi-tier Table Extraction:
   - Tier 1: pdfplumber table extraction for bordered tables.
   - Tier 2: Spatial 2D Bounding-Box Grid Reconstruction (reconstruct_grid) for borderless/complex tables.
2. Bilingual Hindi + English Support:
   - Full preservation of Devanagari Unicode (\u0900-\u097F), Indian currency (₹, Lakh, Crore).
   - High-contrast 300 DPI image enhancement + pytesseract (lang="eng+hin") fallback.
3. Font Corruption & Garbage Detection (is_text_scrambled_or_garbage):
   - Detects (cid:X) font mappings and corrupted glyphs.
4. Checkbox Symbol Normalization:
   - Wingdings \\uf050/\\uf0fe -> [X], \\uf04f -> [ ]
5. Clean Boilerplate & Pagination Stripping.
6. ~2,000-word Chunking (delivering complete tables without splitting).
7. Streaming Buffered Output & Immediate Resumability (Ctrl+C safe).
"""

import os
import sys
import re
import time
import signal
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF
from tqdm import tqdm

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    import io
    _ = pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except Exception:
    TESSERACT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging Setup
# ---------------------------------------------------------------------------
def setup_loggers(logs_dir: Path):
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dapt_corpus")
    logger.setLevel(logging.INFO)
    logger.handlers = []

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(ch)

    fh = logging.FileHandler(logs_dir / "build_corpus.log", encoding="utf-8", mode="a")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)

    return logger


def log_special_event(log_file: Path, message: str):
    with open(log_file, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}\n")


# ---------------------------------------------------------------------------
# Text Quality & Garbage Detection
# ---------------------------------------------------------------------------
def is_text_scrambled_or_garbage(text: str) -> bool:
    """Detects if native PDF text is scrambled, contains (cid:X) codes, or corrupted fonts."""
    if not text:
        return True
    if text.count("(cid:") > 3:
        return True
    cleaned = text.strip()
    if not cleaned:
        return True
    total_len = len(cleaned)
    # Count alphanumeric characters (ASCII + Devanagari) + whitespace
    valid_count = sum(1 for c in cleaned if c.isalnum() or c.isspace() or '\u0900' <= c <= '\u097F')
    if (valid_count / total_len) < 0.55:
        return True
    return False


# ---------------------------------------------------------------------------
# Checkbox & Symbol Normalization
# ---------------------------------------------------------------------------
def normalize_symbols_and_checkboxes(text: str) -> str:
    """Replaces Wingdings/Unicode checkbox glyphs with clear readable text."""
    if not text:
        return ""
    # Wingdings checked/unchecked
    text = text.replace("\uf050", " [X] ").replace("\uf0fe", " [X] ").replace("\u2611", " [X] ")
    text = text.replace("\uf04f", " [ ] ").replace("\u2610", " [ ] ")
    return text


# ---------------------------------------------------------------------------
# Cleaning Pipeline
# ---------------------------------------------------------------------------
RE_PAGINATION_1 = re.compile(r'(?i)\bPage\s+\d+\s+(?:of|/)\s+\d+\b')
RE_PAGINATION_2 = re.compile(r'(?i)\bPage\s*[-–—]?\s*\d+\s*[-–—]?\b')
RE_PAGINATION_3 = re.compile(r'(?i)\b(?:Pg|Page)\.?\s*\d+\b')

RE_GEM_BOILERPLATE_1 = re.compile(r'(?i)This Bid is also governed by the General Terms and Conditions\.?')
RE_GEM_BOILERPLATE_2 = re.compile(r'(?i)In terms of GeM GTC clause 26 regarding Restrictions on procurement[^\n]*')
RE_GEM_BOILERPLATE_3 = re.compile(r'---\s*Thank You\s*---', re.IGNORECASE)
RE_GEM_BOILERPLATE_4 = re.compile(r'(?i)Bidder must comply with the provisions specified in GeM GTC.*')

RE_CID_GLYPHS = re.compile(r'\(cid:\d+\)')

# Control characters (strip unprintable chars, keep \n, \t, \r, Hindi \u0900-\u097F, and symbols)
RE_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
RE_EXCESS_NEWLINES = re.compile(r'\n{3,}')
RE_EXCESS_SPACES = re.compile(r'[ \t]{2,}')


def clean_text_block(text: str) -> str:
    """Applies clean-up filters while preserving Hindi, currency, and markdown formatting."""
    if not text:
        return ""

    text = normalize_symbols_and_checkboxes(text)
    text = RE_CID_GLYPHS.sub('', text)
    text = RE_PAGINATION_1.sub('', text)
    text = RE_PAGINATION_2.sub('', text)
    text = RE_PAGINATION_3.sub('', text)

    text = RE_GEM_BOILERPLATE_1.sub('', text)
    text = RE_GEM_BOILERPLATE_2.sub('', text)
    text = RE_GEM_BOILERPLATE_3.sub('', text)
    text = RE_GEM_BOILERPLATE_4.sub('', text)

    text = RE_CONTROL_CHARS.sub('', text)

    lines = [RE_EXCESS_SPACES.sub(' ', line).strip() for line in text.splitlines()]
    text = '\n'.join(line for line in lines if line)
    text = RE_EXCESS_NEWLINES.sub('\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Spatial 2D Table Grid Parser (reconstruct_grid)
# ---------------------------------------------------------------------------
def reconstruct_spatial_grid(words: List[Tuple], x_tol: int = 25, y_tol: int = 8) -> str:
    """
    Reconstructs an explicit 2D grid matrix (Rows x Columns) from PyMuPDF word bounding boxes.
    words: (x0, y0, x1, y1, word, block_no, line_no, word_no)
    """
    if not words or len(words) < 6:
        return ""

    # Sort words vertically by y0, then horizontally by x0
    sorted_words = sorted(words, key=lambda w: (w[1], w[0]))

    # 1. Cluster words into horizontal row bands
    rows_raw = []
    for w in sorted_words:
        placed = False
        wy0 = w[1]
        for row in rows_raw:
            avg_y = sum(item[1] for item in row) / len(row)
            if abs(wy0 - avg_y) <= y_tol:
                row.append(w)
                placed = True
                break
        if not placed:
            rows_raw.append([w])

    if len(rows_raw) < 2:
        return ""

    # 2. Determine unique column centroid boundaries across the page
    all_x0s = sorted([w[0] for w in sorted_words])
    col_clusters = []
    for x in all_x0s:
        if not col_clusters or abs(x - sum(col_clusters[-1]) / len(col_clusters[-1])) > x_tol:
            col_clusters.append([x])
        else:
            col_clusters[-1].append(x)

    if len(col_clusters) < 2:
        # Not a multi-column table
        return ""

    col_centroids = [int(sum(c) / len(c)) for c in col_clusters]
    num_cols = len(col_centroids)

    # 3. Align row text into 2D grid cells
    grid_rows = []
    for row in rows_raw:
        grid_row = [""] * num_cols
        for w in sorted(row, key=lambda item: item[0]):
            wx0 = w[0]
            col_idx = min(range(num_cols), key=lambda idx: abs(wx0 - col_centroids[idx]))
            w_text = w[4].replace("|", "\\|")
            grid_row[col_idx] = (grid_row[col_idx] + " " + w_text).strip()
        
        if any(c.strip() for c in grid_row):
            grid_rows.append(grid_row)

    if len(grid_rows) < 2:
        return ""

    # Format as Markdown pipe table
    header = "| " + " | ".join(grid_rows[0]) + " |"
    divider = "| " + " | ".join(["---"] * num_cols) + " |"
    body = ["| " + " | ".join(r) + " |" for r in grid_rows[1:]]

    return "\n\n" + "\n".join([header, divider] + body) + "\n\n"


# ---------------------------------------------------------------------------
# Table to Markdown Formatter
# ---------------------------------------------------------------------------
def table_to_markdown(table: List[List[Optional[str]]]) -> str:
    if not table:
        return ""

    cleaned_rows = []
    for row in table:
        if not row:
            continue
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append("")
            else:
                c_str = str(cell).strip().replace("|", "\\|").replace("\r\n", " <br> ").replace("\n", " <br> ")
                c_str = normalize_symbols_and_checkboxes(c_str)
                c_str = RE_CID_GLYPHS.sub('', c_str)
                c_str = RE_CONTROL_CHARS.sub('', c_str)
                cleaned_row.append(c_str)
        if any(c.strip() for c in cleaned_row):
            cleaned_rows.append(cleaned_row)

    if not cleaned_rows:
        return ""

    num_cols = max(len(r) for r in cleaned_rows)
    if num_cols == 0:
        return ""

    padded = [r + [""] * (num_cols - len(r)) for r in cleaned_rows]
    header = "| " + " | ".join(padded[0]) + " |"
    divider = "| " + " | ".join(["---"] * num_cols) + " |"
    body = ["| " + " | ".join(r) + " |" for r in padded[1:]]

    return "\n\n" + "\n".join([header, divider] + body) + "\n\n"


# ---------------------------------------------------------------------------
# Image Preprocessing for High-Precision Bilingual OCR
# ---------------------------------------------------------------------------
def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """Grayscale + contrast enhancement + sharpening for crisp Hindi/English OCR."""
    gray = img.convert("L")
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.0)
    sharpened = enhanced.filter(ImageFilter.SHARPEN)
    return sharpened


# ---------------------------------------------------------------------------
# Page Extraction (Hybrid Multi-Tier)
# ---------------------------------------------------------------------------
def extract_page_blocks(pdf_path: Path, page_num: int, fitz_doc: fitz.Document, plumber_doc: Optional[object]) -> List[str]:
    blocks = []
    fitz_page = fitz_doc[page_num]
    raw_native_text = fitz_page.get_text("text") or ""

    # Check for corrupted font mappings
    is_corrupted = is_text_scrambled_or_garbage(raw_native_text)

    # 1. Tier 1: Try pdfplumber table extraction if available and not corrupted
    has_plumber_tables = False
    if not is_corrupted and plumber_doc is not None and page_num < len(plumber_doc.pages):
        try:
            plumber_page = plumber_doc.pages[page_num]
            found_tables = plumber_page.find_tables()
            if found_tables:
                has_plumber_tables = True
                filtered_page = plumber_page
                for t in found_tables:
                    bbox = t.bbox
                    filtered_page = filtered_page.filter(
                        lambda obj: not (
                            bbox[0] <= obj.get("x0", -1) and obj.get("x1", -1) <= bbox[2]
                            and bbox[1] <= obj.get("top", -1) and obj.get("bottom", -1) <= bbox[3]
                        )
                    )
                
                outside_text = filtered_page.extract_text() or ""
                cleaned_outside = clean_text_block(outside_text)
                if cleaned_outside:
                    blocks.append(cleaned_outside)

                for t in found_tables:
                    extracted_table = t.extract()
                    md_table = table_to_markdown(extracted_table)
                    if md_table:
                        blocks.append(md_table.strip())
        except Exception:
            has_plumber_tables = False

    # 2. Tier 2: If no pdfplumber tables and text looks valid, check spatial grid or standard text
    if not has_plumber_tables and not is_corrupted:
        words = fitz_page.get_text("words")
        # Check if spatial clustering detects a multi-column table
        spatial_table_md = reconstruct_spatial_grid(words)
        if spatial_table_md:
            blocks.append(spatial_table_md.strip())
        else:
            cleaned = clean_text_block(raw_native_text)
            if cleaned:
                blocks.append(cleaned)

    # 3. Tier 3: Scanned or Corrupted Page OCR Fallback (eng+hin)
    if is_corrupted or not blocks:
        if TESSERACT_AVAILABLE:
            try:
                # Render page at 300 DPI (~4.16x zoom)
                mat = fitz.Matrix(3.0, 3.0)
                pix = fitz_page.get_pixmap(matrix=mat, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                preprocessed = preprocess_image_for_ocr(img)
                ocr_text = pytesseract.image_to_string(preprocessed, lang="eng+hin")
                cleaned_ocr = clean_text_block(ocr_text)
                if cleaned_ocr:
                    blocks.append(cleaned_ocr)
            except Exception:
                # If OCR fails, fallback to cleaned native text even if imperfect
                cleaned = clean_text_block(raw_native_text)
                if cleaned:
                    blocks.append(cleaned)
        else:
            cleaned = clean_text_block(raw_native_text)
            if cleaned:
                blocks.append(cleaned)

    return blocks


# ---------------------------------------------------------------------------
# PDF Document Processing & Chunking
# ---------------------------------------------------------------------------
def process_single_pdf(pdf_path: Path) -> List[str]:
    all_blocks = []
    try:
        fitz_doc = fitz.open(pdf_path)
    except Exception as e:
        raise RuntimeError(f"PyMuPDF could not open file: {e}")

    if fitz_doc.is_encrypted:
        fitz_doc.close()
        raise PermissionError("PDF is password-protected or encrypted")

    plumber_doc = None
    if pdfplumber is not None:
        try:
            plumber_doc = pdfplumber.open(pdf_path)
        except Exception:
            plumber_doc = None

    try:
        num_pages = len(fitz_doc)
        for page_num in range(num_pages):
            page_blocks = extract_page_blocks(pdf_path, page_num, fitz_doc, plumber_doc)
            all_blocks.extend(page_blocks)
    finally:
        fitz_doc.close()
        if plumber_doc is not None:
            try:
                plumber_doc.close()
            except Exception:
                pass

    return all_blocks


def build_chunks(blocks: List[str], max_words: int = 2000) -> List[str]:
    """Groups blocks into ~2,000-word chunks without cutting tables across boundaries."""
    chunks = []
    current_chunk = []
    current_words = 0

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        words = len(block.split())
        if current_words + words > max_words and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = [block]
            current_words = words
        else:
            current_chunk.append(block)
            current_words += words

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


CHUNK_DELIMITER = "\n\n---CHUNK_BOUNDARY---\n\n"


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Build DAPT Pretraining Corpus from Tender PDFs (Spatial & Bilingual)")
    parser.add_argument("--input-dir", type=str, default="tender-documents", help="Input directory containing raw PDFs")
    parser.add_argument("--output-file", type=str, default="data/processed/tender_corpus_unannotated.txt", help="Output corpus text file")
    parser.add_argument("--manifest", type=str, default="logs/processed_manifest.txt", help="Manifest of completed files for resume")
    parser.add_argument("--chunk-size", type=int, default=2000, help="Target word count per chunk")
    parser.add_argument("--force-reprocess", action="store_true", help="Ignore manifest and reprocess all files from scratch")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on number of files to process (for testing)")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    input_dir = (root_dir / args.input_dir).resolve()
    output_file = (root_dir / args.output_file).resolve()
    manifest_file = (root_dir / args.manifest).resolve()
    logs_dir = (root_dir / "logs").resolve()
    failed_log = logs_dir / "failed_files.log"
    skipped_log = logs_dir / "skipped_files.log"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_loggers(logs_dir)

    logger.info("=" * 68)
    logger.info("Starting High-Precision Bilingual DAPT Corpus Extraction")
    logger.info(f"Input Directory:       {input_dir}")
    logger.info(f"Output File:           {output_file}")
    logger.info(f"Manifest File:         {manifest_file}")
    logger.info(f"Chunk Target:          ~{args.chunk_size} words")
    logger.info(f"pdfplumber:            {'Available' if pdfplumber is not None else 'Not installed'}")
    logger.info(f"Spatial Grid Parser:   Active (reconstruct_grid enabled)")
    logger.info(f"Bilingual OCR:         {'Available (eng+hin)' if TESSERACT_AVAILABLE else 'Not found in PATH (will skip scanned fallback)'}")
    logger.info("=" * 68)

    if not input_dir.exists():
        logger.error(f"Input directory does not exist: {input_dir}")
        sys.exit(1)

    processed_set = set()
    if not args.force_reprocess and manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    processed_set.add(line_str)
        logger.info(f"Resuming run: Found {len(processed_set)} previously processed files in manifest.")
    elif args.force_reprocess:
        logger.info("Force reprocess specified: Clearing manifest and starting fresh.")
        if manifest_file.exists():
            try:
                open(manifest_file, "w", encoding="utf-8").close()
            except Exception:
                pass
        if output_file.exists():
            try:
                open(output_file, "w", encoding="utf-8").close()
            except Exception:
                pass

    all_files = []
    for r, dirs, files in os.walk(input_dir):
        if "excel" in dirs:
            dirs.remove("excel")
        for f in files:
            full_p = Path(r) / f
            rel_p = str(full_p.relative_to(root_dir)).replace("\\", "/")
            all_files.append((full_p, rel_p, f))

    if args.limit:
        all_files = all_files[:args.limit]
        logger.info(f"Limit applied: processing first {args.limit} files.")

    total_files = len(all_files)
    logger.info(f"Total files discovered: {total_files}")

    stats = {
        "pdfs_found": 0,
        "processed_success": 0,
        "skipped_previously_processed": 0,
        "skipped_password": 0,
        "skipped_non_pdf": 0,
        "failed_corrupt": 0,
        "total_chunks": 0,
        "total_words": 0,
    }

    manifest_fp = open(manifest_file, "a", encoding="utf-8", buffering=1)
    output_fp = open(output_file, "a", encoding="utf-8", buffering=1024 * 1024)

    def sigint_handler(signum, frame):
        logger.warning("\n[INTERRUPT] Received Ctrl+C / SIGINT! Flushing buffers and shutting down safely...")
        manifest_fp.flush()
        manifest_fp.close()
        output_fp.flush()
        output_fp.close()
        logger.info("Progress saved. You can safely resume this script anytime.")
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        pbar = tqdm(all_files, desc="Building Corpus", unit="file", dynamic_ncols=True)
        for full_path, rel_path, filename in pbar:
            ext = full_path.suffix.lower()

            if ext != ".pdf":
                stats["skipped_non_pdf"] += 1
                log_special_event(skipped_log, f"SKIPPED: non-pdf file ({ext}) | {rel_path}")
                continue

            stats["pdfs_found"] += 1

            if rel_path in processed_set:
                stats["skipped_previously_processed"] += 1
                continue

            try:
                blocks = process_single_pdf(full_path)
                chunks = build_chunks(blocks, max_words=args.chunk_size)

                if chunks:
                    for chunk in chunks:
                        output_fp.write(chunk + CHUNK_DELIMITER)
                        stats["total_chunks"] += 1
                        stats["total_words"] += len(chunk.split())

                manifest_fp.write(rel_path + "\n")
                manifest_fp.flush()
                processed_set.add(rel_path)
                stats["processed_success"] += 1

            except PermissionError:
                stats["skipped_password"] += 1
                log_special_event(skipped_log, f"SKIPPED: password-protected | {rel_path}")
                logger.debug(f"Skipped password-protected PDF: {rel_path}")

            except Exception as e:
                stats["failed_corrupt"] += 1
                log_special_event(failed_log, f"FAILED: {e} | {rel_path}")
                logger.warning(f"Error processing {rel_path}: {e}")

    finally:
        manifest_fp.close()
        output_fp.close()

    out_size_mb = 0.0
    if output_file.exists():
        out_size_mb = output_file.stat().st_size / (1024 * 1024)

    logger.info("=" * 68)
    logger.info("DAPT Corpus Extraction Finished!")
    logger.info(f"  - Total Files Discovered:             {total_files}")
    logger.info(f"  - Total PDFs Found:                   {stats['pdfs_found']}")
    logger.info(f"  - Successfully Processed (New):       {stats['processed_success']}")
    logger.info(f"  - Already Processed (Skipped):        {stats['skipped_previously_processed']}")
    logger.info(f"  - Skipped Non-PDFs:                   {stats['skipped_non_pdf']}")
    logger.info(f"  - Skipped Password-Protected:         {stats['skipped_password']}")
    logger.info(f"  - Failed (Corrupted/Errors):          {stats['failed_corrupt']}")
    logger.info(f"  - Total Chunks Written:               {stats['total_chunks']}")
    logger.info(f"  - Total Estimated Words:              {stats['total_words']:,}")
    logger.info(f"  - Output File Size:                   {out_size_mb:.2f} MB")
    logger.info(f"  - Output Location:                    {output_file}")
    logger.info(f"  - Manifest Location:                  {manifest_file}")
    logger.info("=" * 68)


if __name__ == "__main__":
    main()
