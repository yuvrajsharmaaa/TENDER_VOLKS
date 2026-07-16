import json
from pathlib import Path
from ocr.extractors.gem_field_extractor import pair_labels_to_values, TextBlock

job_id = "0a77f878-21d2-4024-86e7-e22b6fe720e3"
job_dir = Path(r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs") / job_id

detail_path = job_dir / "tender_detail.json"
if detail_path.exists():
    with open(detail_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Reconstruct TextBlocks for Page 1
    # Note: rawTextPages contains the page-level blocks inside it. Let's find it.
    raw_pages = data.get("rawTextPages", [])
    print(f"Total raw pages: {len(raw_pages)}")
    
    # Wait, the frontend gets rawTextPages. But does rawTextPages contain "blocks" inside each page dict?
    # Let's check keys of page dict.
    if raw_pages:
        page1 = raw_pages[0]
        print(f"Page 1 keys: {list(page1.keys())}")
        if "blocks" in page1:
            print(f"Page 1 has {len(page1['blocks'])} blocks")
            blocks = []
            for b in page1["blocks"]:
                blocks.append(TextBlock(
                    block_id=b.get("block_id", "0"),
                    text=b.get("text", ""),
                    confidence=b.get("confidence", 1.0),
                    language_hint="en",
                    bounding_box=b.get("bounding_box", {"x1": 0, "y1": 0, "x2": 0, "y2": 0})
                ))
            
            # Print first 20 blocks
            print("--- FIRST 20 BLOCKS OF PAGE 1 ---")
            for idx, b in enumerate(blocks[:20]):
                print(f"{idx}: text={repr(b.text)}, bbox={b.bounding_box}")
                
            # Run pair_labels_to_values
            pairs = pair_labels_to_values(blocks)
            print(f"\nTotal paired cells: {len(pairs)}")
            print("--- ALL PAIRED CELLS ---")
            for l_c, r_c in pairs:
                print(f"  LABEL: {repr(l_c['text'])} (bbox: {l_c['bbox']})")
                print(f"  VALUE: {repr(r_c['text'])} (bbox: {r_c['bbox']})")
                print("-" * 40)
        else:
            print("Page 1 has no 'blocks' key!")
else:
    print("tender_detail.json not found!")
