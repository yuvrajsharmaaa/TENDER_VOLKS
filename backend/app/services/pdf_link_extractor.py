import re
import os
from typing import List, Dict, Any, Tuple

def extract_links_and_mentions(pdf_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    import fitz
    """
    Hardened layer-based link extractor for tender PDFs.
    Layer 1: Standard machine-readable page links via page.get_links()
    Layer 2: PDF Embedded files (attachments) and link annotations check
    Layer 3: Regular expression textual file reference fallback
    Layer 4: Deduplication, confidence scoring, and mapping
    """
    import urllib.request
    from pathlib import Path
    
    parent_dir = Path(pdf_path).parent
    output_dir = parent_dir / "extracted_children"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    saved_paths = []
    embedded_count = 0
    annot_count = 0
    external_count = 0

    links = []
    mentions = []
    
    # Simple regex pattern to scan for referenced assets in prose
    mention_pattern = re.compile(
        r'\b(?:annexure|corrigendum|boq|volume|schedule|specification|addendum)[-_\s]*(?:[iIIVvXx]+|\d+)?(?:\.pdf|\.xlsx?|\.docx?|\b)',
        re.IGNORECASE
    )
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"Error opening PDF in link extractor: {e}")
        return [], []
        
    try:
        # Layer 2a: PDF Embedded Files check (global level attachments)
        emb_count = 0
        try:
            emb_count = doc.embfile_count()
        except Exception:
            pass
            
        for idx in range(emb_count):
            try:
                info = doc.embfile_info(idx)
                filename = info.get("filename", "")
                if filename:
                    file_bytes = doc.embfile_get(idx)
                    out_path = output_dir / filename
                    with open(out_path, "wb") as f:
                        f.write(file_bytes)
                    saved_paths.append(str(out_path))
                    embedded_count += 1
                    
                    # Treat embedded attachments as high-confidence linked sources
                    links.append({
                        "name": filename,
                        "url": f"embedded://{filename}",
                        "sourcePage": 1,
                        "anchorText": info.get("desc", "") or f"Embedded file attachment: {filename}",
                        "extractionConfidence": 98.0,
                        "local_path": str(out_path)
                    })
            except Exception as e:
                print(f"[DEBUG] PyMuPDF global embedded extraction failed at index {idx}: {e}")

        # Fallback using pypdf if PyMuPDF count is 0
        if emb_count == 0:
            try:
                from pypdf import PdfReader
                reader = PdfReader(pdf_path)
                if reader.attachments:
                    for name, content_list in reader.attachments.items():
                        for content in content_list:
                            out_path = output_dir / name
                            with open(out_path, "wb") as f:
                                f.write(content)
                            saved_paths.append(str(out_path))
                            embedded_count += 1
                            links.append({
                                "name": name,
                                "url": f"embedded://{name}",
                                "sourcePage": 1,
                                "anchorText": f"Embedded file attachment (pypdf fallback): {name}",
                                "extractionConfidence": 98.0,
                                "local_path": str(out_path)
                            })
            except ImportError:
                print("[WARNING] pypdf library is not installed, skipping fallback extraction.")
            except Exception as pe:
                print(f"[DEBUG] pypdf extraction failed: {pe}")

        # Iterate page by page
        for page_num in range(len(doc)):
            try:
                page = doc.load_page(page_num)
            except Exception:
                continue
                
            # Layer 1: page.get_links()
            try:
                page_links = page.get_links()
            except Exception:
                page_links = []
                
            for l in page_links:
                try:
                    # Check LINK_URI
                    if l.get("kind") == fitz.LINK_URI:
                        uri = l.get("uri", "")
                        if uri:
                            # Reconstruct anchor text by reading words in link bounding box
                            rect_coords = l.get("from")
                            anchor_text = ""
                            if rect_coords:
                                rect = fitz.Rect(rect_coords)
                                words = page.get_text("words")
                                anchor_words = [w[4] for w in words if fitz.Rect(w[:4]).intersects(rect)]
                                anchor_text = " ".join(anchor_words).strip()
                            
                            filename = uri.split("/")[-1].split("?")[0] or f"linked_file_p{page_num+1}.pdf"
                            if not filename.lower().endswith((".pdf", ".xlsx", ".xls", ".doc", ".docx", ".zip")):
                                filename = f"{filename}.pdf" # fallback suffix
                                
                            links.append({
                                "name": filename,
                                "url": uri,
                                "sourcePage": page_num + 1,
                                "anchorText": anchor_text or f"Clickable Hyperlink: {uri}",
                                "extractionConfidence": 95.0
                            })

                            # Save linked child PDF locally
                            if uri.startswith("http") and any(ext in uri.lower() for ext in [".pdf", ".xlsx", ".xls", ".doc", ".docx", ".zip"]):
                                try:
                                    import ssl
                                    unique_filename = f"page{page_num+1}_{filename}"
                                    req = urllib.request.Request(
                                        uri,
                                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                                    )
                                    context = ssl._create_unverified_context()
                                    with urllib.request.urlopen(req, context=context, timeout=3) as response:
                                        file_bytes = response.read()
                                    out_path = output_dir / unique_filename
                                    with open(out_path, "wb") as f:
                                        f.write(file_bytes)
                                    saved_paths.append(str(out_path))
                                    external_count += 1
                                    links[-1]["local_path"] = str(out_path)
                                except Exception as dl_err:
                                    print(f"[DEBUG] Failed to download/save external link {uri}: {dl_err}")

                    # Support GotoE (Embedded Document Links) or GoToR (Remote Document Links)
                    elif l.get("kind") in (fitz.LINK_GOTO, fitz.LINK_GOTOR, fitz.LINK_LAUNCH):
                        file_dest = l.get("file", "")
                        if file_dest:
                            filename = os.path.basename(file_dest)
                            links.append({
                                "name": filename,
                                "url": f"local://{file_dest}",
                                "sourcePage": page_num + 1,
                                "anchorText": f"External reference destination link on Page {page_num + 1}",
                                "extractionConfidence": 90.0
                            })
                except Exception:
                    pass
            
            # Layer 2b: Annotation-aware link harvesting
            try:
                annots = page.annots()
            except Exception:
                annots = None
                
            if annots:
                for annot in annots:
                    try:
                        # 1 represents Link annotation in fitz.PDF_ANNOT_LINK
                        if annot.type[0] == 1:
                            rect_coords = annot.rect
                            # Check if we already covered this rectangle in get_links
                            words = page.get_text("words")
                            anchor_words = [w[4] for w in words if fitz.Rect(w[:4]).intersects(rect_coords)]
                            anchor_text = " ".join(anchor_words).strip()
                            # If we can fetch URI metadata from the annot dictionary
                            info = annot.info
                            subject = info.get("subject", "") or info.get("title", "")
                            if subject and ("http" in subject or ".pdf" in subject):
                                links.append({
                                    "name": os.path.basename(subject),
                                    "url": subject,
                                    "sourcePage": page_num + 1,
                                    "anchorText": anchor_text or f"Annotation link: {subject}",
                                    "extractionConfidence": 92.0
                                })
                        # 16 represents FileAttachment annotation in fitz.PDF_ANNOT_FILEATTACHMENT
                        elif annot.type[0] == 16:
                            file_data = annot.get_file()
                            info = annot.file_info
                            filename = info.get("filename") or f"annot_attachment_p{page_num+1}.bin"
                            if file_data:
                                out_path = output_dir / filename
                                with open(out_path, "wb") as f:
                                    f.write(file_data)
                                saved_paths.append(str(out_path))
                                annot_count += 1
                                links.append({
                                    "name": filename,
                                    "url": f"embedded://{filename}",
                                    "sourcePage": page_num + 1,
                                    "anchorText": info.get("desc", "") or f"Annotation attachment on Page {page_num+1}",
                                    "extractionConfidence": 96.0,
                                    "local_path": str(out_path)
                                })
                    except Exception as ae:
                        print(f"[DEBUG] Failed to extract annotation file on page {page_num+1}: {ae}")

            # Layer 3: Textual file reference fallback scanning
            try:
                page_text = page.get_text()
            except Exception:
                page_text = ""
                
            for match in mention_pattern.finditer(page_text):
                mention_word = match.group(0).strip()
                if len(mention_word) > 3:
                    # Extract surrounding context sentence
                    sentences = re.split(r'(?<=[.!?])\s+', page_text)
                    context = ""
                    for s in sentences:
                        if mention_word in s:
                            context = s.strip().replace("\n", " ")
                            break
                    
                    # Construct realistic file suffixes
                    ext = ".xlsx" if "boq" in mention_word.lower() else ".pdf"
                    filename = mention_word if "." in mention_word else f"{mention_word}{ext}"
                    
                    # Check if already captured in high confidence links
                    already_linked = any(l["name"].lower() in filename.lower() or filename.lower() in l["name"].lower() for l in links)
                    already_mentioned = any(m["name"].lower() == filename.lower() for m in mentions)
                    
                    if not already_linked and not already_mentioned:
                        mentions.append({
                            "name": filename,
                            "mentionText": context or f"Document reference detected in text on Page {page_num + 1}.",
                            "sourcePage": page_num + 1,
                            "resolved": False
                        })
    except Exception as ex:
        print(f"Exception encountered in link extraction: {ex}")
    finally:
        try:
            doc.close()
        except Exception:
            pass

    # Print debug summary showing extraction stats
    print("\n" + "="*60)
    print("CHILD FILE EXTRACTION SUMMARY")
    print("="*60)
    print(f"Parent PDF: {pdf_path}")
    print(f"Embedded attachments extracted: {embedded_count}")
    print(f"Annotation attachments extracted: {annot_count}")
    print(f"External PDF/document links downloaded: {external_count}")
    print(f"Total files saved locally: {len(saved_paths)}")
    print("Saved file paths:")
    for path in saved_paths:
        print(f"  - {path}")
    print("="*60 + "\n")

    # Layer 4: Deduplicate and standardize items
    deduped_links = []
    seen_links = set()
    for l in links:
        key = (l["name"].lower(), l["url"].lower())
        if key not in seen_links:
            seen_links.add(key)
            deduped_links.append(l)

    return deduped_links, mentions
