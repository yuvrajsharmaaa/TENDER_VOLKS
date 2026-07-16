import fitz

pdf_path = r"c:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\0a77f878-21d2-4024-86e7-e22b6fe720e3\GAIL VRLA Jamnagar.pdf"
doc = fitz.open(pdf_path)
page = doc.load_page(1) # Page 2

with open(r"c:\Users\Asus\Desktop\Tender_Volks\main\scratch\native_blocks_output.txt", "w", encoding="utf-8") as out:
    out.write("=== NATIVE BLOCKS ===\n")
    blocks = page.get_text("blocks")
    for idx, b in enumerate(blocks):
        x0, y0, x1, y1, text, block_no, block_type = b
        out.write(f"Block {idx}: bbox=({x0:.1f}, {y0:.1f}, {x1:.1f}, {y1:.1f}), text={repr(text.strip())}\n")
print("Done writing to scratch/native_blocks_output.txt")
