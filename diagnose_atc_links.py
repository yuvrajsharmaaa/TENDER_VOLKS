"""
Standalone ATC link diagnostic.
Runs directly against a PDF, bypassing the whole TENDER_VOLKS pipeline,
to answer one question: does this PDF actually contain a link annotation
for the ATC document, and if so, on which page and with what URL?

Usage:
    python diagnose_atc_links.py "path/to/GAIL VRLA Jamnagar.pdf"
"""
import sys
import fitz  # PyMuPDF
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def diagnose(pdf_path: str):
    doc = fitz.open(pdf_path)
    print(f"Opened: {pdf_path}")
    print(f"Pages: {len(doc)}\n")

    total_uri_links = 0
    total_annots = 0
    pages_with_atc_text = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        page_text = page.get_text().lower()

        if "atc" in page_text or "buyer uploaded" in page_text:
            pages_with_atc_text.append(page_num + 1)

        # Raw link annotations (what page.get_links() sees)
        links = page.get_links()
        uri_links = [l for l in links if l.get("kind") == fitz.LINK_URI]
        if uri_links:
            total_uri_links += len(uri_links)
            print(f"--- Page {page_num + 1}: {len(uri_links)} URI link(s) found ---")
            for l in uri_links:
                rect = l.get("from")
                uri = l.get("uri", "")
                # what text sits inside the actual (unpadded) link box
                words = page.get_text("words")
                anchor = " ".join(
                    w[4] for w in words
                    if rect and fitz.Rect(w[:4]).intersects(fitz.Rect(rect))
                ).strip()
                print(f"  URL: {uri}")
                print(f"  Anchor text (raw, unpadded): '{anchor}'")
                print(f"  Rect: {rect}\n")

        # Separately: raw annotation objects (catches annotation types
        # get_links() sometimes misses, e.g. plain Link annots without
        # a populated URI action)
        try:
            annots = list(page.annots()) if page.annots() else []
        except Exception:
            annots = []
        if annots:
            total_annots += len(annots)

    print("=" * 60)
    print(f"Pages containing 'atc' / 'buyer uploaded' as plain text: {pages_with_atc_text}")
    print(f"Total URI link annotations found in whole PDF: {total_uri_links}")
    print(f"Total raw annotation objects (any type) in whole PDF: {total_annots}")
    print("=" * 60)

    if not pages_with_atc_text:
        print("\nDIAGNOSIS: The PDF's plain text never mentions ATC at all on any "
              "page. Either this specific tender has no ATC section, or the "
              "page is scanned/image-only and page.get_text() can't read it "
              "(check with a PDF viewer whether the page is a picture of text "
              "vs real text).")
    elif total_uri_links == 0:
        print("\nDIAGNOSIS: The words 'ATC' / 'buyer uploaded' appear as plain "
              "text, but PyMuPDF found ZERO clickable URI link annotations "
              "anywhere in the PDF. This means the document itself has no "
              "embedded hyperlink for the ATC document — the phrase is present "
              "but it is not a link. No amount of extraction-code fixing can "
              "recover a URL that isn't in the file. You'd need to get the URL "
              "from the GeM portal API/page directly instead of the PDF.")
    else:
        matched = [
            p for p in pages_with_atc_text
        ]
        print(f"\nDIAGNOSIS: Found {total_uri_links} real URI link(s) in the PDF, "
              f"and ATC text appears on page(s) {matched}. Check above whether "
              f"any of the printed URLs are on the same page number as the ATC "
              f"text — if yes, the link exists and the pipeline's matching "
              f"logic (not PyMuPDF extraction) is the problem. If the only "
              f"links found are on unrelated pages, this PDF may not have an "
              f"ATC-specific link at all.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python diagnose_atc_links.py <path_to_pdf>")
        sys.exit(1)
    diagnose(sys.argv[1])
