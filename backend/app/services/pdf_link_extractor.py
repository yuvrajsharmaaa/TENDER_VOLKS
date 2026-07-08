import fitz
import re
import os
from typing import List, Dict, Any, Tuple

def extract_links_and_mentions(pdf_path: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Hardened layer-based link extractor for tender PDFs.
    Layer 1: Standard machine-readable page links via page.get_links()
    Layer 2: PDF Embedded files (attachments) and link annotations check
    Layer 3: Regular expression textual file reference fallback
    Layer 4: Deduplication, confidence scoring, and mapping
    """
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
                    # Treat embedded attachments as high-confidence linked sources
                    links.append({
                        "name": filename,
                        "url": f"embedded://{filename}",
                        "sourcePage": 1,
                        "anchorText": info.get("desc", "") or f"Embedded file attachment: {filename}",
                        "extractionConfidence": 98.0
                    })
            except Exception:
                pass

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
                    except Exception:
                        pass

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

    # Layer 4: Deduplicate and standardize items
    deduped_links = []
    seen_links = set()
    for l in links:
        key = (l["name"].lower(), l["url"].lower())
        if key not in seen_links:
            seen_links.add(key)
            deduped_links.append(l)

    return deduped_links, mentions
