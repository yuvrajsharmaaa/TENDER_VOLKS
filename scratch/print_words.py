import fitz
import sys
sys.stdout.reconfigure(encoding='utf-8')

doc = fitz.open('backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/GAIL VRLA Jamnagar.pdf')
page = doc.load_page(0)
words = page.get_text("words")
# Print words sorted by y then x
words_sorted = sorted(words, key=lambda w: (w[1], w[0]))

print("First 40 words:")
for w in words_sorted[:40]:
    print(f"  {w[4]:<30} | x0={w[0]:.1f}, y0={w[1]:.1f}, x1={w[2]:.1f}, y1={w[3]:.1f} | block_no={w[5]}, line_no={w[6]}")
