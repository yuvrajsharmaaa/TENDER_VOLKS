import re
import math
import logging
from typing import List, Dict, Any, Optional, Tuple
from backend.app.models.models import PageResult, TextBlock, LayoutRegion
from backend.app.schemas.schemas import ExtractedFieldSchema, SourceBlockRef, BoundingBox
from backend.app.services.field_registry import merge_keywords

logger = logging.getLogger(__name__)

# Utility Spatial Containment checks
def get_intersection_area(boxA: Dict[str, int], boxB: Dict[str, int]) -> int:
    xA = max(boxA["x1"], boxB["x1"])
    yA = max(boxA["y1"], boxB["y1"])
    xB = min(boxA["x2"], boxB["x2"])
    yB = min(boxA["y2"], boxB["y2"])
    
    interWidth = max(0, xB - xA)
    interHeight = max(0, yB - yA)
    return interWidth * interHeight

def get_intersection_percentage(boxA: Dict[str, int], boxB: Dict[str, int]) -> float:
    interArea = get_intersection_area(boxA, boxB)
    if interArea == 0:
        return 0.0
    areaA = (boxA["x2"] - boxA["x1"]) * (boxA["y2"] - boxA["y1"])
    if areaA == 0:
        return 0.0
    return interArea / areaA

def is_contained(boxA: Dict[str, int], boxB: Dict[str, int], threshold: float = 0.5) -> bool:
    """Check if boxA is mostly contained within boxB."""
    # Check center point
    cx = (boxA["x1"] + boxA["x2"]) / 2
    cy = (boxA["y1"] + boxA["y2"]) / 2
    if (boxB["x1"] <= cx <= boxB["x2"]) and (boxB["y1"] <= cy <= boxB["y2"]):
        return True
    return get_intersection_percentage(boxA, boxB) >= threshold

# Table block row parsing utility
def group_blocks_into_rows(blocks: List[TextBlock], y_threshold: int = 15) -> List[List[TextBlock]]:
    if not blocks:
        return []
    
    # Sort blocks primarily by top y-coordinate
    sorted_blocks = sorted(blocks, key=lambda b: b.bounding_box["y1"])
    rows = []
    current_row = [sorted_blocks[0]]
    
    for block in sorted_blocks[1:]:
        # Compare current block y1 to the average y1 of the current row
        avg_y1 = sum(b.bounding_box["y1"] for b in current_row) / len(current_row)
        if abs(block.bounding_box["y1"] - avg_y1) <= y_threshold:
            current_row.append(block)
        else:
            rows.append(sorted(current_row, key=lambda b: b.bounding_box["x1"]))
            current_row = [block]
    rows.append(sorted(current_row, key=lambda b: b.bounding_box["x1"]))
    return rows

class FieldExtractor:
    def __init__(self):
        # Target regex patterns
        self.date_regex = re.compile(r'\b\d{2}[-/\.]\d{2}[-/\.]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b')
        self.currency_regex = re.compile(
            r'(?:Rs\.?|INR|₹|rupees)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)(?:\s*(?:Lakh|Crore|Lacs|Cr|/-))?\b|'
            r'\b(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?)\s*(?:Lakh|Crore|Lacs|Cr)\b',
            re.IGNORECASE
        )
        self.nit_regex = re.compile(
            r'\b(?:GEM/20\d{2}/[A-Z]/\d+|'
            r'[A-Za-z0-9]+/20\d{2}-\d{2}/[0-9]+|'
            r'[A-Za-z0-9\-]+/[A-Za-z0-9\-]+/20\d{2}/[0-9]+|'
            r'NIT[-/\s\.:]*(?:No)?[-/\s\.:]*\b([A-Za-z0-9\-#/\.]*\d[A-Za-z0-9\-#/\.]*)\b)\b',
            re.IGNORECASE
        )
        self.validity_regex = re.compile(r'\b(\d+)\s*(?:days|days\s+validity|दिन|दिवस|अवधि)\b', re.IGNORECASE)
        self.period_regex = re.compile(
            r'\b(\d+)\s*(?:months|days|weeks|year|years|महीने|दिन|वर्ष)\b|'
            r'\b(?:one|two|three|four|five|six|twelve)\s*(?:months|days|weeks|year|years)\b',
            re.IGNORECASE
        )
        
        # Mapping definition of fields with anchors, hindi translations, and type of regex used
        self.rules = {
            # Legacy Fields
            "EMD": {
                "anchors": ["emd", "earnest money", "security deposit", "bid security"],
                "hindi": ["धरोहर राशि", "ईएमडी", "बोली सुरक्षा"],
                "type": "currency"
            },
            "Tender Fee": {
                "anchors": ["tender fee", "cost of document", "document fee", "tender document cost"],
                "hindi": ["निविदा शुल्क", "दस्तावेज़ शुल्क", "निविदा दस्तावेज मूल्य"],
                "type": "fee"
            },
            "Bid Submission Start Date": {
                "anchors": ["submission start", "submission opening date", "online submission start", "bid submission date"],
                "hindi": ["बोली जमा करने की प्रारंभिक तिथि", "निविदा जमा करने की तिथि"],
                "type": "date"
            },
            "Bid Submission End Date": {
                "anchors": ["submission end", "submission last date", "submission closing", "last date of bid submission", "submission deadline"],
                "hindi": ["बोली जमा करने की अंतिम तिथि", "निविदा जमा करने की अंतिम तिथि", "जमा करने की अंतिम समय"],
                "type": "date"
            },
            "Bid Opening Date": {
                "anchors": ["opening date", "bid opening", "date of opening", "technical bid opening"],
                "hindi": ["बोली खोलने की तिथि", "तकनीकी बोली खोलने की तिथि"],
                "type": "date"
            },
            "NIT No": {
                "anchors": ["nit no", "nit number", "tender ref", "tender reference", "tender id", "tender number", "bid number"],
                "hindi": ["निविदा संख्या", "एनआईटी संख्या", "निविदा आमंत्रण सूचना संख्या", "संदर्भ संख्या"],
                "type": "nit"
            },
            "Tender Value": {
                "anchors": ["tender value", "estimated cost", "estimated value", "tender cost", "work value", "amount of work", "contract value", "total value", "bid value", "value of work", "work cost", "tender amount"],
                "hindi": ["अनुमानित लागत", "निविदा मूल्य", "अनुमानित दर", "अनुबंध मूल्य"],
                "type": "currency"
            },
            "Organisation": {
                "anchors": ["ministry", "department", "corporation", "office of", "authority", "division", "board"],
                "hindi": ["विभाग", "मंत्रालय", "निगम", "कार्यालय"],
                "type": "org"
            },
            "Pre-Bid Meeting Date": {
                "anchors": ["pre-bid meeting", "prebid meeting", "pre-bid date", "meeting date", "pre bid conference"],
                "hindi": ["प्री-बिड बैठक", "निविदा पूर्व बैठक"],
                "type": "date"
            },
            "Bid Validity Period": {
                "anchors": ["validity period", "bid validity", "validity of bid", "offer validity"],
                "hindi": ["बोली वैधता अवधि", "वैधता"],
                "type": "validity"
            },
            "Period of Work": {
                "anchors": ["period of work", "completion period", "contract period", "delivery period", "completion time"],
                "hindi": ["कार्य की अवधि", "समाप्ति अवधि", "कार्य अवधि"],
                "type": "period"
            },
            
            # New Target Fields
            "bid_number": {
                "anchors": ["bid number", "bid no", "gem bid number", "gem bid no", "tender number", "tender no", "bid ref", "tender ref", "boli number", "boli no"],
                "hindi": ["बोली क्रमांक", "बोली संख्या", "निविदा संख्या"],
                "type": "nit"
            },
            "tender_date": {
                "anchors": ["bid date", "tender date", "date of bid", "date of tender", "published date", "nit date", "gem bid date", "bid start date"],
                "hindi": ["बोली दिनांक", "निविदा दिनांक", "प्रकाशन तिथि", "आरंभ तिथि"],
                "type": "date"
            },
            "bid_end_datetime": {
                "anchors": ["bid end date/time", "bid submission end", "submission end", "closing date", "last date of submission", "bid end", "submission closing", "submission deadline", "bid end date"],
                "hindi": ["बोली समाप्ति", "बोली जमा करने की अंतिम तिथि", "समाप्ति दिनांक", "जमा करने का अंतिम समय"],
                "type": "datetime"
            },
            "bid_open_datetime": {
                "anchors": ["bid opening date/time", "bid opening date", "opening date", "technical bid opening", "date of opening", "bid opening", "opening time"],
                "hindi": ["बोली खोले जाने", "बोली खोलने की तिथि", "खोलने की तिथि"],
                "type": "datetime"
            },
            "ministry_name": {
                "anchors": ["ministry name", "ministry of", "ministry:"],
                "hindi": ["मंत्रालय का नाम", "मंत्रालय"],
                "type": "org"
            },
            "department_name": {
                "anchors": ["department name", "department of", "department:"],
                "hindi": ["विभाग का नाम", "विभाग"],
                "type": "org"
            },
            "organisation_name": {
                "anchors": ["organisation name", "organization name", "organisation of", "organization of", "organisation:", "organization:", "authority"],
                "hindi": ["संगठन का नाम", "संगठन", "संस्था"],
                "type": "org"
            },
            "office_name": {
                "anchors": ["office name", "office:", "office of"],
                "hindi": ["कार्यालय का नाम", "कार्यालय"],
                "type": "org"
            },
            "buyer_email": {
                "anchors": ["buyer email", "email id", "email address", "email:", "consignee email", "contact email"],
                "hindi": ["ईमेल", "खरीदार का ईमेल"],
                "type": "email"
            },
            "item_category": {
                "anchors": ["item category", "category:", "product category", "primary product category", "major category", "service category"],
                "hindi": ["मद श्रेणी", "सामग्री श्रेणी", "उत्पाद श्रेणी"],
                "type": "text"
            },
            "similar_category": {
                "anchors": ["similar category", "similar product category", "equivalent category", "similar item category"],
                "hindi": ["समान श्रेणी", "समान उत्पाद श्रेणी"],
                "type": "text"
            },
            "contract_period": {
                "anchors": ["contract period", "period of work", "completion period", "delivery period", "duration of contract", "period of contract"],
                "hindi": ["कार्य की अवधि", "समाप्ति अवधि", "अनुबंध अवधि"],
                "type": "period"
            },
            "minimum_average_annual_turnover": {
                "anchors": ["minimum average annual turnover", "average annual turnover", "turnover of the bidder", "bidder turnover", "annual turnover"],
                "hindi": ["न्यूनतम औसत वार्षिक टर्नओवर", "वार्षिक टर्नओवर"],
                "type": "currency"
            },
            "years_of_past_experience": {
                "anchors": ["years of past experience", "past experience", "experience criteria", "bidder experience", "years of experience"],
                "hindi": ["अनुभव", "पूर्व अनुभव"],
                "type": "experience"
            },
            "past_experience_required": {
                "anchors": ["past experience required", "past performance", "experience required", "performance required", "past experience required?"],
                "hindi": ["पूर्व प्रदर्शन", "पूर्व अनुभव आवश्यक"],
                "type": "yes_no"
            }
        }

        # Widen (never narrow) specific rules' anchors with any synonyms the
        # shared field registry knows about but this rule doesn't yet. This
        # is how keyword fixes made for the other (plain-text) extraction
        # engine also reach this engine, without touching this engine's own
        # matching/confidence logic. Rules that already show anchor-overlap
        # precision issues (e.g. "ministry_name" matching inside its own
        # value) are intentionally left out of this merge to avoid making
        # that pre-existing issue worse.
        _REGISTRY_MERGE_MAP = {
            "NIT No": "reference_id",
            "bid_number": "reference_id",
            "EMD": "emd_amount",
            "Tender Fee": "tender_fee",
            "Bid Submission End Date": "bid_submission_deadline",
            "bid_end_datetime": "bid_submission_deadline",
            "Bid Opening Date": "bid_opening_date",
            "bid_open_datetime": "bid_opening_date",
            "Tender Value": "tender_value",
            "Pre-Bid Meeting Date": "prebid_meeting",
            "minimum_average_annual_turnover": "turnover_requirement",
            "years_of_past_experience": "experience_requirement",
            "item_category": "title",
            "buyer_email": "contact_officer",
        }
        for rule_key, canonical_key in _REGISTRY_MERGE_MAP.items():
            if rule_key in self.rules:
                self.rules[rule_key]["anchors"] = merge_keywords(self.rules[rule_key]["anchors"], canonical_key)

    def _normalize_for_match(self, text: str) -> str:
        """Replace common separators with spaces and collapse whitespace for
        fuzzy anchor matching. This lets "ministry/state name" match the
        anchor "ministry name" without collapsing numbers/words into false
        substring matches (e.g. "06-06-2025" stays "06 06 2025")."""
        return re.sub(r"\s+", " ", re.sub(r"[/\\_.:\-]", " ", text.lower())).strip()

    def _anchor_matches(self, anchor: str, text: str) -> bool:
        """Check if the anchor words appear in order inside the text words,
        allowing small gaps. This is stricter than raw substring (so it
        avoids "value" matching inside "devalued") but more forgiving than
        exact phrase matching (so "ministry name" matches
        "ministry / state name")."""
        anchor_words = self._normalize_for_match(anchor).split()
        text_words = self._normalize_for_match(text).split()
        if not anchor_words:
            return False
        i = 0
        for aw in anchor_words:
            while i < len(text_words) and text_words[i] != aw:
                i += 1
            if i >= len(text_words):
                return False
            i += 1
        return True

    def _anchor_at_start_or_short(self, anchor: str, text: str) -> bool:
        """True if the anchor is at the very start of the text or the text is
        a short label. Used in the general block scan to avoid matching broad
        anchors inside paragraphs (e.g. "office of" inside a long clause)."""
        if not self._anchor_matches(anchor, text):
            return False
        if len(text.strip()) < 50:
            return True
        text_norm = self._normalize_for_match(text)
        anchor_norm = self._normalize_for_match(anchor)
        return text_norm.startswith(anchor_norm)

    def _strip_noise_words(self, text: str) -> str:
        """Remove leading OCR/Hindi noise tokens from a merged label/value suffix.
        Keeps all-uppercase acronyms and words that contain a lowercase vowel."""
        words = text.split()
        for i, word in enumerate(words):
            if len(word) >= 2 and word.isupper():
                return " ".join(words[i:])
            if any(v in word for v in "aeiouy"):
                return " ".join(words[i:])
        return ""

    def _extract_suffix_after_anchor(self, text: str, anchors: List[str]) -> Optional[str]:
        """When an anchor and its value live in the same text block (common in
        GeM tables where OCR merges a label and value), return the text that
        follows the matched anchor, stripping trailing Hindi/gibberish."""
        best_suffix = None
        best_pos = -1
        for anchor in anchors:
            if not self._anchor_matches(anchor, text):
                continue
            anchor_words = self._normalize_for_match(anchor).split()
            if not anchor_words:
                continue
            # Match the anchor words in the original text, allowing flexible
            # separators (slashes, spaces, Hindi characters) between them.
            parts = [re.escape(w) for w in anchor_words]
            pattern = re.compile(r"(?:\W|\s)*".join(parts), re.IGNORECASE)
            m = pattern.search(text)
            if m and m.end() > best_pos:
                best_pos = m.end()
                best_suffix = text[m.end():]
        if best_suffix:
            # Strip leading label noise (hindi words, slashes, colons, short mixed-case tokens)
            best_suffix = re.sub(r"^[^a-zA-Z0-9\s]+", "", best_suffix)          # leading non-alphanumeric
            best_suffix = re.sub(r"^(\b\w{1,3}\b\s*)+", "", best_suffix)      # leading very short words
            # mixed-case transliterations starting with uppercase (FeadY, Avft)
            best_suffix = re.sub(r"^(\b[A-Z][a-zA-Z]*[A-Z][a-zA-Z]*\b\s*)+", "", best_suffix)
            best_suffix = self._strip_noise_words(best_suffix)
            best_suffix = re.sub(r"^[/\\_.:\-]+\s*", "", best_suffix)
            best_suffix = best_suffix.strip()
        return best_suffix if best_suffix else None

    def _match_value_pattern(self, text: str, field_type: str) -> Optional[str]:
        """Verify if text matches the expected pattern for field_type and return matched string."""
        text_clean = text.strip()
        if not text_clean:
            return None
            
        if field_type == "date":
            m = self.date_regex.search(text_clean)
            return m.group(0) if m else None
        elif field_type == "datetime":
            m = re.search(r'\b\d{2}[-/\.]\d{2}[-/\.]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?\b', text_clean)
            return m.group(0) if m else None
        elif field_type == "email":
            m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text_clean)
            return m.group(0) if m else None
        elif field_type == "currency":
            m = self.currency_regex.search(text_clean)
            if m:
                return m.group(0)
            m = re.search(r'\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:Lakh|Crore|Lacs|Cr|/-)?\b', text_clean, re.IGNORECASE)
            return m.group(0) if m else None
        elif field_type == "fee":
            if any(w in text_clean.lower() for w in ["nil", "free", "exempted", "no fee", "निःशुल्क"]):
                return "Nil / Exempted"
            m = self.currency_regex.search(text_clean)
            return m.group(0) if m else None
        elif field_type == "nit":
            m = self.nit_regex.search(text_clean)
            if m:
                return m.group(1) if m.group(1) is not None else m.group(0)
            return None
        elif field_type == "validity":
            m = self.validity_regex.search(text_clean)
            return m.group(0) if m else None
        elif field_type == "period":
            m = self.period_regex.search(text_clean)
            return m.group(0) if m else None
        elif field_type == "experience":
            m = re.search(r'\b\d+\s*(?:year|years|yr|yrs|साल|वर्ष)\b', text_clean, re.IGNORECASE)
            return m.group(0) if m else None
        elif field_type == "yes_no":
            m = re.search(r'\b(?:yes|no|required|not required|हाँ|नहीं)\b', text_clean, re.IGNORECASE)
            return m.group(0) if m else None
        elif field_type == "org":
            words = text_clean.strip()
            if len(words) > 3 and len(words) < 150:
                if not words.lower().startswith(("bid document", "bid details", "boli vivran")):
                    return words
            return None
        elif field_type == "text":
            cleaned = text_clean.strip()
            if len(cleaned) > 2 and len(cleaned) < 150:
                if not cleaned.lower().startswith(("bid document", "bid details", "boli vivran")):
                    return cleaned
            return None
        return None

    def extract_products(self, pages: List[PageResult]) -> List[Dict[str, Any]]:
        """
        Heuristic product / service line-item extraction for Indian tender docs.
        Scans OCR text for keywords aligned to Volks Energie's typical scope
        (batteries, ACs, UPS/inverters, electrical accessories, cables, panels,
        solar, HVAC, installation / maintenance). Returns structured product
        candidates with quantity, unit, and page evidence where detectable.
        """
        category_keywords = {
            "battery": ["battery", "batteries", "battery pack", "battery set", "battery unit"],
            "air_conditioner": ["air conditioner", "air conditioning", "split ac", "window ac", "cassette ac", "air cooled"],
            "ups": ["ups", "uninterruptible power supply", "online ups", "line interactive ups"],
            "inverter": ["inverter", "solar inverter", "grid tie inverter", "off-grid inverter"],
            "solar": ["solar panel", "solar module", "pv module", "solar cell", "solar power", "solar system"],
            "cable": ["cable", "cables", "wire", "wires", "power cable", "control cable", "lt cable"],
            "panel": ["distribution panel", "db panel", "switchgear panel", "control panel", "mcc panel", "panel board"],
            "transformer": ["transformer", "distribution transformer", "power transformer"],
            "stabilizer": ["stabilizer", "voltage stabilizer", "avr", "automatic voltage regulator"],
            "hvac": ["hvac", "ventilation", "duct", "air handling unit", "ahu", "cooling"],
            "electrical_accessory": ["switch", "socket", "mcb", "mccb", "rccb", "contactor", "relay", "fuse", "breaker", "distribution board", "db"],
            "maintenance_service": ["amc", "annual maintenance", "maintenance contract", "preventive maintenance", "maintenance service"],
            "installation_service": ["installation", "commissioning", "erection", "supply and installation", "supply & installation"],
            "civil_work": ["civil work", "civil works", "construction", "foundation", "shed", "room"],
        }

        products: List[Dict[str, Any]] = []
        seen: set = set()

        for page in pages:
            page_num = page.page_number
            for block in page.text_blocks:
                text = block.text
                text_lower = text.lower()
                if len(text.strip()) < 4:
                    continue
                for category, keywords in category_keywords.items():
                    # Use word-boundary-aware matching so short substrings like
                    # "duct" inside "production" don't trigger false positives.
                    if not any(re.search(rf'(?<!\w){re.escape(kw)}(?!\w)', text_lower) for kw in keywords):
                        continue
                    # Try to pull a quantity + unit from the same line.
                    qty = None
                    unit = None
                    qty_match = re.search(
                        r'\b(\d+(?:\.\d+)?)\s*(?:nos|no|units|unit|sets|set|pcs|pieces|pairs|kg|m|mtr|meter|meters|sqm|each|lot|ea)\b',
                        text, re.IGNORECASE
                    )
                    if qty_match:
                        qty = qty_match.group(1)
                        tail = text[qty_match.end():].strip()[:20].lower()
                        unit_match = re.search(r'\b(?:nos|no|units|unit|sets|set|pcs|pieces|pairs|kg|m|mtr|meter|meters|sqm|each|lot|ea)\b', tail)
                        if unit_match:
                            unit = unit_match.group(0)

                    brand_match = re.search(r'\b(?:oem|make|brand|mfg|manufacturer)[:\s]+([A-Za-z][A-Za-z0-9\s&\-]{2,30})', text, re.IGNORECASE)
                    brand = brand_match.group(1).strip() if brand_match else None

                    key = (category, text[:80].strip().lower())
                    if key in seen:
                        continue
                    seen.add(key)

                    products.append({
                        "product_name": category.replace("_", " ").title(),
                        "normalized_category": category,
                        "raw_text": text,
                        "quantity": qty,
                        "unit": unit,
                        "technical_specification": text,
                        "brand_or_oem_if_present": brand,
                        "page_number": page_num,
                        "confidence": round(0.6 + min(0.35, len([k for k in keywords if re.search(rf'(?<!\w){re.escape(k)}(?!\w)', text_lower)]) * 0.05), 2),
                        "evidence_text": text,
                    })
                    break

        return products

    def extract_fields(self, pages: List[PageResult]) -> List[ExtractedFieldSchema]:
        extracted = []
        print(f"\n[FIELD_EXTRACTOR_DEBUG] Starting field extraction on {len(pages)} page(s).", flush=True)
        
        for field_name, rule in self.rules.items():
            candidates: List[Dict[str, Any]] = []
            print(f"[FIELD_EXTRACTOR_DEBUG] Processing rule '{field_name}' (expected type: '{rule['type']}')", flush=True)
            
            for page in pages:
                page_num = page.page_number
                blocks = page.text_blocks
                regions = page.layout_regions
                
                # Pre-process tables
                table_regions = [r for r in regions if r.region_type.lower() == "table"]
                for table in table_regions:
                    table_blocks = [b for b in blocks if is_contained(b.bounding_box, table.bounding_box)]
                    if not table_blocks:
                        continue

                    rows = group_blocks_into_rows(table_blocks)
                    for row in rows:
                        # Find all anchor candidates in the row, then prefer the leftmost
                        # label cell. This prevents value cells that happen to contain
                        # anchor keywords (e.g., "Ministry Of Defence") from being picked
                        # as the anchor for "ministry_name".
                        anchor_candidates = []
                        for block in row:
                            score = 0.0
                            if any(self._anchor_matches(k, block.text) for k in rule["hindi"]):
                                score = 0.40
                            elif any(self._anchor_matches(k, block.text) for k in rule["anchors"]):
                                score = 0.35
                            if score > 0.0:
                                anchor_candidates.append((score, block))

                        if not anchor_candidates:
                            continue

                        anchor_candidates.sort(key=lambda sb: sb[1].bounding_box["x1"])
                        anchor_score, anchor_found = anchor_candidates[0]

                        print(f"  [FIELD_EXTRACTOR_DEBUG] Table row anchor matched: '{anchor_found.text}'", flush=True)
                        # Concatenate all non-anchor cells in reading order. This handles
                        # the normal GeM table layout where the label and value are in
                        # different cells.
                        value_blocks = [b for b in row if b != anchor_found]
                        value_blocks.sort(key=lambda b: b.bounding_box["x1"])
                        cell_text = " ".join(b.text.strip() for b in value_blocks)
                        val = self._match_value_pattern(cell_text, rule["type"])
                        print(f"    [FIELD_EXTRACTOR_DEBUG] Table cell value test (concatenated): '{cell_text}' -> matched val: '{val}'", flush=True)
                        if val:
                            conf = anchor_score + 0.35 + 0.20 + 0.05
                            conf = min(1.0, conf)
                            candidates.append({
                                "value": val,
                                "confidence": round(conf, 2),
                                "source_page": page_num,
                                "evidence": f"Row match in table: '{anchor_found.text}' -> '{cell_text}'",
                                "source_blocks": [
                                    SourceBlockRef(
                                        page_number=page_num,
                                        block_id=anchor_found.block_id,
                                        region_id=table.region_id,
                                        text=anchor_found.text,
                                        bounding_box=BoundingBox(**anchor_found.bounding_box)
                                    )
                                ] + [
                                    SourceBlockRef(
                                        page_number=page_num,
                                        block_id=b.block_id,
                                        region_id=table.region_id,
                                        text=b.text,
                                        bounding_box=BoundingBox(**b.bounding_box)
                                    ) for b in value_blocks
                                ]
                            })
                        elif rule["type"] in ("text", "org"):
                            # Fallback: the anchor block itself may have merged the label
                            # and value (common in GeM OCR). Extract the value suffix.
                            suffix = self._extract_suffix_after_anchor(anchor_found.text, rule["anchors"] + rule["hindi"])
                            if suffix:
                                suffix_val = self._match_value_pattern(suffix, rule["type"])
                                print(f"    [FIELD_EXTRACTOR_DEBUG] Table anchor suffix value: '{suffix}' -> matched val: '{suffix_val}'", flush=True)
                                if suffix_val:
                                    candidates.append({
                                        "value": suffix_val,
                                        "confidence": round(anchor_score + 0.35 + 0.20 + 0.05, 2),
                                        "source_page": page_num,
                                        "evidence": f"Row match in table: '{anchor_found.text}' -> '{suffix_val}'",
                                        "source_blocks": [
                                            SourceBlockRef(
                                                page_number=page_num,
                                                block_id=anchor_found.block_id,
                                                region_id=table.region_id,
                                                text=anchor_found.text,
                                                bounding_box=BoundingBox(**anchor_found.bounding_box)
                                            )
                                        ]
                                    })

                # Scan general blocks
                # In the general block scan, avoid single-word broad anchors like
                # "authority", "office", or "category" from matching paragraph text.
                # Table rows have their own structural disambiguation, so they still
                # use the full anchor set. Short uppercase acronyms (e.g. "EMD") are
                # allowed here because they are specific.
                general_anchors = [
                    k for k in rule["anchors"]
                    if len(k.split()) >= 2 or (len(k) <= 5 and k.isupper())
                ]

                for idx, block in enumerate(blocks):
                    anchor_score = 0.0

                    if any(self._anchor_at_start_or_short(k, block.text) for k in rule["hindi"]):
                        anchor_score = 0.40
                    elif any(self._anchor_at_start_or_short(k, block.text) for k in general_anchors):
                        anchor_score = 0.35

                    if anchor_score > 0.0:
                        # 1. Check same block. If the whole block was returned, try
                        # to extract the value that appears after the anchor; this
                        # handles GeM cells where OCR merges the label and value
                        # (e.g. "Item Category/Implementation of UPS...").
                        val = self._match_value_pattern(block.text, rule["type"])
                        if val and val == block.text.strip() and rule["type"] in ("text", "org"):
                            suffix = self._extract_suffix_after_anchor(block.text, rule["anchors"] + rule["hindi"])
                            if suffix:
                                val = self._match_value_pattern(suffix, rule["type"])
                        if val and val != block.text.strip():
                            print(f"  [FIELD_EXTRACTOR_DEBUG] Same-block match: '{block.text}' -> '{val}'", flush=True)
                            conf = anchor_score + 0.35 + 0.25
                            conf = min(1.0, conf)
                            candidates.append({
                                "value": val,
                                "confidence": round(conf, 2),
                                "source_page": page_num,
                                "evidence": block.text,
                                "source_blocks": [
                                    SourceBlockRef(
                                        page_number=page_num,
                                        block_id=block.block_id,
                                        text=block.text,
                                        bounding_box=BoundingBox(**block.bounding_box)
                                    )
                                ]
                            })
                            continue
                        
                        # 2. Check next block
                        if idx + 1 < len(blocks):
                            next_block = blocks[idx+1]
                            val = self._match_value_pattern(next_block.text, rule["type"])
                            if val:
                                dist_y = abs(next_block.bounding_box["y1"] - block.bounding_box["y2"])
                                if dist_y < 50:
                                    print(f"  [FIELD_EXTRACTOR_DEBUG] Next-block match: '{block.text}' | '{next_block.text}' -> '{val}'", flush=True)
                                    conf = anchor_score + 0.35 + 0.15
                                    conf = min(1.0, conf)
                                    candidates.append({
                                        "value": val,
                                        "confidence": round(conf, 2),
                                        "source_page": page_num,
                                        "evidence": f"{block.text} | {next_block.text}",
                                        "source_blocks": [
                                            SourceBlockRef(
                                                page_number=page_num,
                                                block_id=block.block_id,
                                                text=block.text,
                                                bounding_box=BoundingBox(**block.bounding_box)
                                            ),
                                            SourceBlockRef(
                                                page_number=page_num,
                                                block_id=next_block.block_id,
                                                text=next_block.text,
                                                bounding_box=BoundingBox(**next_block.bounding_box)
                                            )
                                        ]
                                    })
                                    continue
                                    
                        # 3. Nearest-neighbor
                        cx_a = (block.bounding_box["x1"] + block.bounding_box["x2"]) / 2
                        cy_a = (block.bounding_box["y1"] + block.bounding_box["y2"]) / 2
                        
                        best_neighbor = None
                        best_neighbor_val = None
                        min_dist = float('inf')
                        
                        for other_block in blocks:
                            if other_block == block:
                                continue
                            
                            cx_o = (other_block.bounding_box["x1"] + other_block.bounding_box["x2"]) / 2
                            cy_o = (other_block.bounding_box["y1"] + other_block.bounding_box["y2"]) / 2
                            
                            is_right = other_block.bounding_box["x1"] >= block.bounding_box["x1"] and abs(cy_o - cy_a) < 30
                            is_below = other_block.bounding_box["y1"] >= block.bounding_box["y2"] and abs(cx_o - cx_a) < 150
                            
                            if is_right or is_below:
                                dist = math.sqrt((cx_o - cx_a)**2 + (cy_o - cy_a)**2)
                                if dist < 150 and dist < min_dist:
                                    val = self._match_value_pattern(other_block.text, rule["type"])
                                    if val:
                                        min_dist = dist
                                        best_neighbor = other_block
                                        best_neighbor_val = val
                                        
                        if best_neighbor:
                            print(f"  [FIELD_EXTRACTOR_DEBUG] Spatial neighbor match: '{block.text}' -> '{best_neighbor.text}' -> '{best_neighbor_val}'", flush=True)
                            conf = anchor_score + 0.35 + 0.15
                            conf = min(1.0, conf)
                            candidates.append({
                                "value": best_neighbor_val,
                                "confidence": round(conf, 2),
                                "source_page": page_num,
                                "evidence": f"{block.text} -> {best_neighbor.text}",
                                "source_blocks": [
                                    SourceBlockRef(
                                        page_number=page_num,
                                        block_id=block.block_id,
                                        text=block.text,
                                        bounding_box=BoundingBox(**block.bounding_box)
                                    ),
                                    SourceBlockRef(
                                        page_number=page_num,
                                        block_id=best_neighbor.block_id,
                                        text=best_neighbor.text,
                                        bounding_box=BoundingBox(**best_neighbor.bounding_box)
                                    )
                                ]
                            })
                            
            if candidates:
                # Drop value candidates that are clearly paragraphs/sentences rather
                # than discrete field values (e.g., an org value that continues as
                # "Ministry. If the bidder wants..."). This improves table extraction
                # quality on noisy GeM PDFs without adding per-layout special cases.
                def _looks_like_paragraph(value: str) -> bool:
                    if len(value) > 100:
                        return True
                    return bool(re.search(
                        r'\.\s+(if|the|and|or|shall|for|of|to|in|with|this|that|these|those|is|are|was|were|has|have|had|be|been|being|it|they|there)\b',
                        value, re.IGNORECASE
                    ))

                candidates = [c for c in candidates if not _looks_like_paragraph(c["value"])]

                if candidates:
                    best_cand = sorted(candidates, key=lambda c: c["confidence"], reverse=True)[0]
                    print(f"[FIELD_EXTRACTOR_DEBUG] Extracted value for '{field_name}': '{best_cand['value']}' (conf: {best_cand['confidence']})", flush=True)
                else:
                    print(f"[FIELD_EXTRACTOR_DEBUG] Extracted value for '{field_name}': Not Found (all candidates looked like paragraphs)", flush=True)
                    extracted.append(ExtractedFieldSchema(
                        field_name=field_name,
                        value="Not Found",
                        confidence=0.0,
                        source_page=1,
                        evidence="No matching anchors or value patterns found in document.",
                        source_blocks=[]
                    ))
                    continue
                extracted.append(ExtractedFieldSchema(
                    field_name=field_name,
                    value=best_cand["value"],
                    confidence=best_cand["confidence"],
                    source_page=best_cand["source_page"],
                    evidence=best_cand["evidence"],
                    source_blocks=best_cand["source_blocks"]
                ))
            else:
                print(f"[FIELD_EXTRACTOR_DEBUG] Extracted value for '{field_name}': Not Found", flush=True)
                extracted.append(ExtractedFieldSchema(
                    field_name=field_name,
                    value="Not Found",
                    confidence=0.0,
                    source_page=1,
                    evidence="No matching anchors or value patterns found in document.",
                    source_blocks=[]
                ))
                
        print(f"[FIELD_EXTRACTOR_DEBUG] Finished extraction. Total extracted fields count: {len(extracted)}\n", flush=True)
        return extracted
