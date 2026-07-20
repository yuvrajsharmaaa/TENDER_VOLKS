import re
from ocr.extractors.gem_field_extractor import GemFieldExtractor, group_blocks_into_rows
from backend.app.models.models import PageResult, TextBlock

blocks = [
    # Schedule 1 Heading
    TextBlock(block_id="1", text="Schedule 1 / अनुसूची 1", confidence=1.0, bounding_box={"x1": 100, "y1": 50, "x2": 300, "y2": 70}, language_hint="en"),
    # Consignees header
    TextBlock(block_id="2", text="Consignee Reporting/Officer / परेषिती", confidence=1.0, bounding_box={"x1": 100, "y1": 100, "x2": 300, "y2": 120}, language_hint="en"),
    TextBlock(block_id="3", text="Address / पता", confidence=1.0, bounding_box={"x1": 310, "y1": 100, "x2": 500, "y2": 120}, language_hint="en"),
    TextBlock(block_id="4", text="Quantity / मात्रा", confidence=1.0, bounding_box={"x1": 510, "y1": 100, "x2": 600, "y2": 120}, language_hint="en"),
    TextBlock(block_id="5", text="Delivery Days / वितरण के दिन", confidence=1.0, bounding_box={"x1": 610, "y1": 100, "x2": 700, "y2": 120}, language_hint="en"),
    # Consignee Row 1 (Schedule 1)
    TextBlock(block_id="6", text="John Doe", confidence=1.0, bounding_box={"x1": 100, "y1": 140, "x2": 300, "y2": 160}, language_hint="en"),
    TextBlock(block_id="7", text="123 Road, Ranchi", confidence=1.0, bounding_box={"x1": 310, "y1": 140, "x2": 500, "y2": 160}, language_hint="en"),
    TextBlock(block_id="8", text="445", confidence=1.0, bounding_box={"x1": 510, "y1": 140, "x2": 600, "y2": 160}, language_hint="en"),
    TextBlock(block_id="9", text="90", confidence=1.0, bounding_box={"x1": 610, "y1": 140, "x2": 700, "y2": 160}, language_hint="en"),
    # Technical specifications for Schedule 1
    TextBlock(block_id="10", text="Nominal Battery Voltage", confidence=1.0, bounding_box={"x1": 100, "y1": 200, "x2": 400, "y2": 220}, language_hint="en"),
    TextBlock(block_id="11", text="2 V", confidence=1.0, bounding_box={"x1": 500, "y1": 200, "x2": 600, "y2": 220}, language_hint="en"),
    TextBlock(block_id="12", text="Battery Capacity at 10-h Rate [C 10]", confidence=1.0, bounding_box={"x1": 100, "y1": 230, "x2": 400, "y2": 250}, language_hint="en"),
    TextBlock(block_id="13", text="65 Ah", confidence=1.0, bounding_box={"x1": 500, "y1": 230, "x2": 600, "y2": 250}, language_hint="en"),
    
    # Schedule 2 Heading
    TextBlock(block_id="14", text="Schedule 2 / अनुसूची 2", confidence=1.0, bounding_box={"x1": 100, "y1": 300, "x2": 300, "y2": 320}, language_hint="en"),
    # Consignees row (Schedule 2)
    TextBlock(block_id="15", text="Jane Smith", confidence=1.0, bounding_box={"x1": 100, "y1": 340, "x2": 300, "y2": 360}, language_hint="en"),
    TextBlock(block_id="16", text="456 Street, Visakhapatnam", confidence=1.0, bounding_box={"x1": 310, "y1": 340, "x2": 500, "y2": 360}, language_hint="en"),
    TextBlock(block_id="17", text="100", confidence=1.0, bounding_box={"x1": 510, "y1": 340, "x2": 600, "y2": 360}, language_hint="en"),
    TextBlock(block_id="18", text="90", confidence=1.0, bounding_box={"x1": 610, "y1": 340, "x2": 700, "y2": 360}, language_hint="en"),
    # Technical specifications for Schedule 2
    TextBlock(block_id="19", text="Nominal Battery Voltage", confidence=1.0, bounding_box={"x1": 100, "y1": 400, "x2": 400, "y2": 420}, language_hint="en"),
    TextBlock(block_id="20", text="2 V", confidence=1.0, bounding_box={"x1": 500, "y1": 400, "x2": 600, "y2": 420}, language_hint="en"),
    TextBlock(block_id="21", text="Battery Capacity at 10-h Rate [C 10]", confidence=1.0, bounding_box={"x1": 100, "y1": 430, "x2": 400, "y2": 450}, language_hint="en"),
    TextBlock(block_id="22", text="100 Ah", confidence=1.0, bounding_box={"x1": 500, "y1": 430, "x2": 600, "y2": 450}, language_hint="en")
]

sorted_blocks = sorted(blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
all_rows = group_blocks_into_rows(sorted_blocks)

current_schedule_num = 1
consignee_headers = None
schedules_data = {}

for row_idx, row in enumerate(all_rows):
    row_text = " ".join(b.text for b in row)

    m_sch = re.search(r"Schedule\s*(\d+)", row_text, re.IGNORECASE)
    if m_sch:
        current_schedule_num = int(m_sch.group(1))

    is_tech_spec = False
    if len(row) >= 2:
        c1_text = row[0].text.strip()
        c2_text = " ".join(b.text.strip() for b in row[1:])
        spec_keywords = [
            "battery capacity", "nominal battery voltage", "battery voltage",
            "capacity at 10-h", "voltage", "capacity", "specification", "oem"
        ]
        if any(kw in c1_text.lower() for kw in spec_keywords):
            if not any(k in c1_text.lower() for k in ["dated", "schedule", "consignee", "delivery"]):
                is_tech_spec = True

        if is_tech_spec:
            schedules_data.setdefault(current_schedule_num, {
                "schedule_number": current_schedule_num,
                "consignee_name": "Not Found",
                "consignee_address": "Not Found",
                "quantity": "Not Found",
                "delivery_days": "Not Found",
                "item_description": "Not Found",
                "technical_specs": {}
            })
            clean_param = re.sub(r"^[^a-zA-Z0-9\s]+", "", c1_text)
            clean_param = re.sub(r"^[/\\_.:\-]+\s*", "", clean_param).strip()
            schedules_data[current_schedule_num]["technical_specs"][clean_param] = c2_text.strip()
            continue

    row_texts_lower = [b.text.lower() for b in row]
    has_consignee = any("consignee" in txt or "reporting" in txt or "officer" in txt for txt in row_texts_lower)
    has_qty = any("quantity" in txt or "मात्रा" in txt for txt in row_texts_lower)
    has_days = any("delivery" in txt or "days" in txt for txt in row_texts_lower)

    if has_consignee and (has_qty or has_days):
        consignee_headers = {}
        for col_idx, block in enumerate(row):
            txt = block.text.lower()
            if "consignee" in txt or "reporting" in txt or "officer" in txt:
                consignee_headers["consignee_name"] = col_idx
            elif "address" in txt or "पता" in txt:
                consignee_headers["consignee_address"] = col_idx
            elif "quantity" in txt or "मात्रा" in txt:
                consignee_headers["quantity"] = col_idx
            elif "delivery" in txt or "days" in txt:
                consignee_headers["delivery_days"] = col_idx
        continue

    if consignee_headers and len(row) >= 2:
        if any("total" in b.text.lower() or "योग" in b.text.lower() or "schedule" in b.text.lower() for b in row):
            consignee_headers = None
            continue
        
        schedules_data.setdefault(current_schedule_num, {
            "schedule_number": current_schedule_num,
            "consignee_name": "Not Found",
            "consignee_address": "Not Found",
            "quantity": "Not Found",
            "delivery_days": "Not Found",
            "item_description": "Not Found",
            "technical_specs": {}
        })

        entry = schedules_data[current_schedule_num]
        print(f"Before extraction for Schedule {current_schedule_num}: {entry}")
        for field, col_idx in consignee_headers.items():
            if col_idx < len(row):
                val = row[col_idx].text.strip()
                if field in ("quantity", "delivery_days"):
                    clean_val = re.sub(r"\D", "", val)
                    if clean_val:
                        try:
                            entry[field] = int(clean_val)
                        except ValueError:
                            pass
                else:
                    entry[field] = val
        print(f"After extraction for Schedule {current_schedule_num}: {entry}")

for block in sorted_blocks:
    m_sch = re.search(r"Schedule\s*(\d+)", block.text, re.IGNORECASE)
    if m_sch:
        current_schedule_num = int(m_sch.group(1))
    if current_schedule_num in schedules_data:
        if "pieces" in block.text or "quantity" in block.text.lower() or "stationary" in block.text.lower():
            if not any(k in block.text.lower() for k in ["dated", "consignee", "address", "delivery", "schedule"]):
                schedules_data[current_schedule_num]["item_description"] = block.text.strip()

print("Final schedules_data:")
print(schedules_data)
