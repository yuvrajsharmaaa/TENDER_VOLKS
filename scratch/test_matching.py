import re
from rapidfuzz import fuzz

DEVANAGARI_RANGE = re.compile(r'[\u0900-\u097F]+')

def strip_devanagari(text: str) -> str:
    return DEVANAGARI_RANGE.sub(' ', text).strip()

label_text = "Bid Offer Validity (From End Date)/ बड पेशकश"
clean_label = strip_devanagari(label_text).lower()
print(f"clean_label: {repr(clean_label)}")

anchors = ["Bid Offer Validity", "Bid Offer Validity (From publish date)", "Bid Validity Period", "Bid Validity"]
for anchor in anchors:
    score = fuzz.partial_ratio(anchor.lower(), clean_label)
    print(f"Anchor: {anchor}, Score: {score}")
