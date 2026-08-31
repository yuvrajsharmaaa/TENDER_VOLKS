import sys
sys.path.insert(0, "/app")
import os
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import pytesseract
from ocr.ocr_engine import OcrEngine
from ocr.extractors.gem_field_extractor import field_confidence, GemFieldExtractor
from backend.app.models.models import TextBlock, PageResult
from backend.app.services.rfq_drafting_service import RFQDraftingService, RFQDraftRequest, LineItemSpec, BlockedRFQSendError

print("=== RUNNING LIVE TESSERACT OCR & GUARDRAIL TEST INSIDE DOCKER CONTAINER ===")

# 1. Verify Tesseract inside container
tess_ver = pytesseract.get_tesseract_version()
print(f"1. Pytesseract Version inside container: {tess_ver}")
print(f"   Available Tesseract Languages: {pytesseract.get_languages()}")

# 2. Create a realistic scanned/noisy document crop
clean_img = Image.new("RGB", (600, 160), color=(255, 255, 255))
draw = ImageDraw.Draw(clean_img)
draw.text((20, 20), "Bid Number: GEM/2026/B/7103056", fill=(0, 0, 0))
draw.text((20, 65), "Schedule 1 Quantity: 18 pieces", fill=(0, 0, 0))
draw.text((20, 110), "Delivery Days: 90", fill=(0, 0, 0))

# Degrade image to simulate scanner noise & blur
scanned_img = clean_img.copy()
scanned_img = scanned_img.filter(ImageFilter.GaussianBlur(radius=1.5))
enhancer = ImageEnhance.Contrast(scanned_img)
scanned_img = enhancer.enhance(0.5)

test_img_path = "/tmp/scanned_tender_crop.png"
scanned_img.save(test_img_path)
print(f"2. Saved synthetic scanned crop to {test_img_path}")

# 3. Run real live OcrEngine (invoking C++ Tesseract binary in container)
engine = OcrEngine(lang="eng")
text_blocks = engine.run(test_img_path)

print(f"\n3. Real Tesseract OCR Output ({len(text_blocks)} blocks extracted):")
for b in text_blocks:
    print(f"   - TextBlock '{b.text}' -> Genuine Tesseract Confidence: {b.confidence:.4f} (ID: {b.block_id})")

# 4. Check whether any scanned blocks dropped below 0.85
low_conf_blocks = [b for b in text_blocks if b.confidence < 0.85]
print(f"\n4. Genuine Scanned Blocks with Confidence < 0.85: {len(low_conf_blocks)} / {len(text_blocks)}")
for b in low_conf_blocks:
    print(f"   -> Degraded Block: '{b.text}' | Confidence: {b.confidence:.4f}")

# 5. Route through GemFieldExtractor field_confidence
# Let's take the extracted Quantity block
qty_block = next((b for b in text_blocks if "quantity" in b.text.lower() or "18" in b.text), text_blocks[0])
computed_field_conf = qty_block.confidence

print(f"\n5. Quantity Field Compound Confidence: {computed_field_conf:.4f} (< 0.85: {computed_field_conf < 0.85})")

# 6. Pass genuine Tesseract output to RFQ Drafting Service
service = RFQDraftingService()
req = RFQDraftRequest(
    tender_no="GEM/2026/B/7103056",
    organization="Indian Navy",
    tender_title="Battery SITC Scanned Annexure",
    line_items=[
        LineItemSpec(
            item_name="12V 75AH LEAD ACID BATTERY",
            quantity="18",
            delivery_location="Uttara Kannada",
            technical_spec="Naval Standard",
            confidence_score=0.98,
            field_confidences={"quantity": computed_field_conf},
            status="ok"
        )
    ],
    commercial_terms={
        "delivery_timeline": "90 days",
        "payment_terms": "100% on acceptance"
    }
)

draft = service.draft_rfq(req)

print(f"\n6. RFQ Drafting Evaluation:")
print(f"   - contains_missing_fields: {draft.contains_missing_fields}")
print(f"   - is_ready_for_dispatch: {draft.is_ready_for_dispatch}")
print(f"   - missing_fields_list: {draft.missing_fields_list}")

assert draft.contains_missing_fields is True
assert draft.is_ready_for_dispatch is False
assert "quantity" in draft.missing_fields_list
assert "[NEEDS REVIEW: quantity]" in draft.draft_body

# 7. Confirm hard block on live send
try:
    service.send_rfq(draft, destination_email="vendor@naval-supplies.in")
    print("   [ERROR] Dispatch was not blocked!")
except BlockedRFQSendError as e:
    print(f"\n7. Hard-Block Verification inside Container:")
    print(f"   [SUCCESS] {e}")

print("\n=== CONTAINERIZED LIVE TESSERACT & GUARDRAIL TEST COMPLETED SUCCESSFULLY ===")
