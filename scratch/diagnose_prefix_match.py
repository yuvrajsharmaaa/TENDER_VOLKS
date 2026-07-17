import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
from ocr.extractors.gem_field_extractor import strip_devanagari, FIELD_ANCHORS

# Simulate exactly what happens for the merged PBG block text
test_texts = [
    "ईपीबीजी 9ितशत (%)/ePBG Percentage(%) 3.00",
    "ईपीबीजी क आवOयक अविध (माह) /Duration of ePBG 62 required (Months).",
    "एडवाइजर बKक/Advisory Bank State Bank of India",
]

print("=== Testing prefix match logic ===\n")
for text in test_texts:
    clean_text = strip_devanagari(text).lower()
    print(f"Original: {repr(text)}")
    print(f"Stripped: {repr(clean_text)}")
    
    for field_name, spec in FIELD_ANCHORS.items():
        for anchor in spec["anchors"]:
            clean_anchor = anchor.lower()
            if clean_text.startswith(clean_anchor):
                idx = text.lower().find(anchor.lower())
                if idx != -1:
                    suffix = text[idx + len(anchor):].strip()
                    suffix = re.sub(r"^[:\-/\s\u0900-\u097F]+", "", suffix).strip()
                    print(f"  MATCH field={field_name}, anchor={repr(anchor)}, idx={idx}, suffix={repr(suffix)}")
                else:
                    print(f"  STARTSWITH but no find: anchor={repr(anchor)}")
    print()

# Now test: what if stripped text contains the anchor NOT at start?
# e.g. "/ePBG Percentage(%) 3.00" — stripped gives "/ePBG Percentage(%) 3.00", not starting with "ePBG"
print("=== Testing 'contains' variant ===\n")
for text in test_texts:
    clean_text = strip_devanagari(text).lower()
    for field_name, spec in FIELD_ANCHORS.items():
        for anchor in spec["anchors"]:
            clean_anchor = anchor.lower()
            # Does stripped text CONTAIN the anchor (not just start with it)?
            if clean_anchor in clean_text and not clean_text.startswith(clean_anchor):
                # Try finding anchor in original text
                idx = text.lower().find(anchor.lower())
                if idx != -1:
                    suffix = text[idx + len(anchor):].strip()
                    suffix = re.sub(r"^[:\-/\s\u0900-\u097F]+", "", suffix).strip()
                    if suffix and len(suffix) < 100:  # likely a value, not a paragraph
                        print(f"  CONTAINS field={field_name}, anchor={repr(anchor)}")
                        print(f"    original text: {repr(text)}")
                        print(f"    suffix: {repr(suffix)}")
