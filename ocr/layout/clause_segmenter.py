import re
from typing import List, Dict, Any
from backend.app.models.models import TextBlock, LayoutRegion
from backend.app.services.gail_clause_aliases import ATC_CLAUSE_ALIASES

# Compile regex for numbered clauses and headings
NUMBERED_CLAUSE_RE = re.compile(
    r'^(?:(?:Clause\s+)?(\d{1,2}(?:\.\d{1,2})*)\.?|\(([a-zA-Z0-9]{1,3})\))\s+([A-Za-z0-9\(\)/\-,\. ]{2,})',
    re.IGNORECASE
)

STANDARD_HEADINGS = [
    "DISCLAIMER",
    "BUYER ADDED BID SPECIFIC ATC",
    "SPECIAL CONDITIONS OF CONTRACT",
    "BID EVALUATION CRITERIA",
    "TECHNICAL SPECIFICATION",
    "TERMS OF PAYMENT",
    "PAYMENT TERMS",
    "PRICE REDUCTION SCHEDULE",
    "CONTRACT PERFORMANCE SECURITY",
    "SECURITY DEPOSIT",
    "EARNEST MONEY DEPOSIT",
    "EMD DETAIL",
    "EPBG DETAIL",
    "SPLITTING",
    "MII PURCHASE PREFERENCE",
    "MSE PURCHASE PREFERENCE",
    "ALL GEM SELLERS/SERVICE PROVIDERS",
    "IN TERMS OF GEM GTC CLAUSE",
    "FURTHER, IF ANY SELLER HAS ANY OBJECTION",
    "NOTE: THIS CLAUSE OF ATC",
    "BUYER UPLOADED ATC DOCUMENT",
]

def is_clause_header(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    t_upper = t.upper()
    
    # Check standard heading keywords
    for h in STANDARD_HEADINGS:
        if t_upper.startswith(h):
            return True
            
    # Check numbered clause pattern (e.g. "1. ", "13.0 PAYMENT TERMS:", "2. Seeking EMD...")
    m = NUMBERED_CLAUSE_RE.match(t)
    if m:
        return True
        
    return False

def segment_text_blocks_into_clauses(
    text_blocks: List[TextBlock],
    page_number: int,
    vertical_gap_threshold: float = 35.0
) -> List[LayoutRegion]:
    """
    Groups line-level TextBlocks into coherent clause/paragraph LayoutRegions
    using clause-header heuristics and spatial vertical gap separation.
    Computes exact enclosing bounding boxes from the contained blocks.
    """
    if not text_blocks:
        return []

    # Sort blocks by reading order (primarily y1, then x1)
    sorted_blocks = sorted(text_blocks, key=lambda b: (b.bounding_box["y1"], b.bounding_box["x1"]))
    
    clause_groups: List[List[TextBlock]] = []
    current_group: List[TextBlock] = []
    
    for idx, block in enumerate(sorted_blocks):
        txt = block.text.strip()
        if not txt:
            continue
            
        if not current_group:
            current_group.append(block)
            continue
            
        prev_block = current_group[-1]
        v_gap = block.bounding_box["y1"] - prev_block.bounding_box["y2"]
        
        is_header = is_clause_header(txt)
        is_large_gap = v_gap > vertical_gap_threshold
        
        # If it's a clause header or there's a significant vertical gap, start a new clause region
        if is_header or (is_large_gap and len(current_group) > 0):
            clause_groups.append(current_group)
            current_group = [block]
        else:
            current_group.append(block)
            
    if current_group:
        clause_groups.append(current_group)
        
    regions: List[LayoutRegion] = []
    for c_idx, group in enumerate(clause_groups):
        min_x = min(b.bounding_box["x1"] for b in group)
        min_y = min(b.bounding_box["y1"] for b in group)
        max_x = max(b.bounding_box["x2"] for b in group)
        max_y = max(b.bounding_box["y2"] for b in group)
        
        combined_text = "\n".join(b.text.strip() for b in group if b.text.strip())
        avg_conf = sum(b.confidence for b in group) / len(group) if group else 1.0
        
        regions.append(LayoutRegion(
            region_id=f"reg_p{page_number:02d}_{c_idx+1:03d}",
            region_type="paragraph",
            bounding_box={
                "x1": int(min_x),
                "y1": int(min_y),
                "x2": int(max_x),
                "y2": int(max_y)
            },
            contained_block_ids=[b.block_id for b in group],
            text_content=combined_text,
            reading_order_index=c_idx + 1,
            confidence=round(avg_conf, 4)
        ))
        
    return regions
