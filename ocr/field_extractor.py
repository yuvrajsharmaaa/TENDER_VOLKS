import re
import math
from typing import List, Dict, Any, Optional, Tuple
from shared.models import PageResult, TextBlock, LayoutRegion
from shared.schemas import ExtractedFieldSchema, SourceBlockRef, BoundingBox

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
            "EMD": {
                "anchors": ["emd", "earnest money", "security deposit", "bid security"],
                "hindi": ["धरोहर राशि", "ईएमडी", "बोली सुरक्षा"],
                "type": "currency"
            },
            "Tender Fee": {
                "anchors": ["tender fee", "cost of document", "document fee", "tender document cost"],
                "hindi": ["निविदा शुल्क", "दस्तावेज़ शुल्क", "निविदा दस्तावेज मूल्य"],
                "type": "fee" # allows currency pattern or words like Nil/Exempted
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
                "anchors": ["tender value", "estimated cost", "estimated value", "tender cost", "work value", "amount of work"],
                "hindi": ["अनुमानित लागत", "निविदा मूल्य", "अनुमानित दर"],
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
            }
        }

    def _match_value_pattern(self, text: str, field_type: str) -> Optional[str]:
        """Verify if text matches the expected pattern for field_type and return matched string."""
        if field_type == "date":
            m = self.date_regex.search(text)
            return m.group(0) if m else None
        elif field_type == "currency":
            m = self.currency_regex.search(text)
            return m.group(0) if m else None
        elif field_type == "fee":
            if any(w in text.lower() for w in ["nil", "free", "exempted", "no fee", "निःशुल्क"]):
                return "Nil / Exempted"
            m = self.currency_regex.search(text)
            return m.group(0) if m else None
        elif field_type == "nit":
            m = self.nit_regex.search(text)
            if m:
                return m.group(1) if m.group(1) is not None else m.group(0)
            return None
        elif field_type == "validity":
            m = self.validity_regex.search(text)
            return m.group(0) if m else None
        elif field_type == "period":
            m = self.period_regex.search(text)
            return m.group(0) if m else None
        elif field_type == "org":
            # For orgs, return clean substring of words representing the name (usually excluding simple keywords)
            words = text.strip()
            if len(words) > 5 and len(words) < 100:
                return words
            return None
        return None

    def extract_fields(self, pages: List[PageResult]) -> List[ExtractedFieldSchema]:
        extracted = []
        
        for field_name, rule in self.rules.items():
            candidates: List[Dict[str, Any]] = []
            
            for page in pages:
                page_num = page.page_number
                blocks = page.text_blocks
                regions = page.layout_regions
                
                # Pre-process tables
                table_regions = [r for r in regions if r.region_type.lower() == "table"]
                for table in table_regions:
                    # Find all blocks spatially inside this table
                    table_blocks = [b for b in blocks if is_contained(b.bounding_box, table.bounding_box)]
                    if not table_blocks:
                        continue
                        
                    rows = group_blocks_into_rows(table_blocks)
                    for row in rows:
                        # Find if any cell/block in the row matches keywords
                        anchor_found = None
                        anchor_score = 0.0
                        
                        for block in row:
                            txt_lower = block.text.lower()
                            if any(k in txt_lower for k in rule["hindi"]):
                                anchor_found = block
                                anchor_score = 0.40 # Hindi match
                                break
                            elif any(k in txt_lower for k in rule["anchors"]):
                                anchor_found = block
                                anchor_score = 0.35 # Exact English match
                                break
                                
                        if anchor_found:
                            # Search other cells in this same row for a matching value pattern
                            for block in row:
                                if block == anchor_found:
                                    continue
                                val = self._match_value_pattern(block.text, rule["type"])
                                if val:
                                    conf = anchor_score + 0.35 + 0.20 + 0.05 # anchor + value + row alignment + table region
                                    conf = min(1.0, conf)
                                    candidates.append({
                                        "value": val,
                                        "confidence": round(conf, 2),
                                        "source_page": page_num,
                                        "evidence": f"Row match in table: '{anchor_found.text}' -> '{block.text}'",
                                        "source_blocks": [
                                            SourceBlockRef(
                                                page_number=page_num,
                                                block_id=anchor_found.block_id,
                                                region_id=table.region_id,
                                                text=anchor_found.text,
                                                bounding_box=BoundingBox(**anchor_found.bounding_box)
                                            ),
                                            SourceBlockRef(
                                                page_number=page_num,
                                                block_id=block.block_id,
                                                region_id=table.region_id,
                                                text=block.text,
                                                bounding_box=BoundingBox(**block.bounding_box)
                                            )
                                        ]
                                    })
                
                # Scan general blocks (if not matched or to find alternate options)
                for idx, block in enumerate(blocks):
                    txt_lower = block.text.lower()
                    anchor_score = 0.0
                    is_hindi = False
                    
                    if any(k in txt_lower for k in rule["hindi"]):
                        anchor_score = 0.40
                        is_hindi = True
                    elif any(k in txt_lower for k in rule["anchors"]):
                        anchor_score = 0.35
                    
                    if anchor_score > 0.0:
                        # 1. Check if value is in the SAME block
                        val = self._match_value_pattern(block.text, rule["type"])
                        if val and len(val) < len(block.text):
                            conf = anchor_score + 0.35 + 0.25 # anchor + pattern + same block
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
                        
                        # 2. Check the NEXT block in reading order
                        if idx + 1 < len(blocks):
                            next_block = blocks[idx+1]
                            val = self._match_value_pattern(next_block.text, rule["type"])
                            if val:
                                # Distance check: must be visually close
                                dist_y = abs(next_block.bounding_box["y1"] - block.bounding_box["y2"])
                                if dist_y < 50:
                                    conf = anchor_score + 0.35 + 0.15 # anchor + pattern + adjacent block
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
                                    
                        # 3. Spatial nearest-neighbor (horizontal to the right or vertical directly below)
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
                            
                            # Filter: only look at blocks to the right or below
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
                            conf = anchor_score + 0.35 + 0.15 # anchor + pattern + nearest neighbor
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
                            
            # Sort candidates by confidence score and select the best one
            if candidates:
                best_cand = sorted(candidates, key=lambda c: c["confidence"], reverse=True)[0]
                extracted.append(ExtractedFieldSchema(
                    field_name=field_name,
                    value=best_cand["value"],
                    confidence=best_cand["confidence"],
                    source_page=best_cand["source_page"],
                    evidence=best_cand["evidence"],
                    source_blocks=best_cand["source_blocks"]
                ))
            else:
                # Add default null schema if field is not found (allows robust structure representation)
                extracted.append(ExtractedFieldSchema(
                    field_name=field_name,
                    value="Not Found",
                    confidence=0.0,
                    source_page=1,
                    evidence="No matching anchors or value patterns found in document.",
                    source_blocks=[]
                ))
                
        return extracted
