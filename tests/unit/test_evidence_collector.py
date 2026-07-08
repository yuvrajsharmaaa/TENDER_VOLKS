import pytest
from backend.app.services.evidence_collector import (
    score_occurrence,
    resolve_best_value,
    compile_evidence_log
)

def test_score_occurrence():
    # Timing parameter - prioritizes COVER
    occ_cover = {"page": 1, "confidence": 0.9}
    occ_body = {"page": 5, "confidence": 0.9}
    
    assert score_occurrence(occ_cover, "timing") == 3.0 * 0.9
    assert score_occurrence(occ_body, "timing") == 2.0 * 0.9
    
    # Guarantee parameter - prioritizes BODY
    assert score_occurrence(occ_cover, "guarantees") == 2.0 * 0.9
    assert score_occurrence(occ_body, "guarantees") == 3.0 * 0.9

def test_resolve_best_value():
    # Cover prioritizes
    occurrences = [
        {"field_name": "tender_value", "value_raw": "Rs 25 Lakh", "page": 1, "confidence": 0.8},
        {"field_name": "tender_value", "value_raw": "2500000", "page": 12, "confidence": 0.95}
    ]
    best = resolve_best_value(occurrences, "identity", total_pages=16)
    assert best["page"] == 1  # 3 * 0.8 = 2.4 > 1 * 0.95 = 0.95
    
    # Conflict resolution with low confidence -> returns None
    conflicting = [
        {"field_name": "emd_amount", "value_raw": "100000", "page": 1, "confidence": 0.5},
        {"field_name": "emd_amount", "value_raw": "200000", "page": 1, "confidence": 0.5}
    ]
    assert resolve_best_value(conflicting, "emd", total_pages=16) is None

def test_compile_evidence_log():
    occurrences = [
        {"field_name": "tender_value", "value_raw": "Rs 25 Lakh", "normalized_value": 2500000.0, "page": 1, "confidence": 0.8, "text_snippet": "Value Rs 25 Lakh"}
    ]
    log = compile_evidence_log(occurrences, tender_id=123)
    assert len(log) == 1
    assert log[0]["tender_id"] == 123
    assert log[0]["normalized_value"] == 2500000.0
    assert log[0]["page_number"] == 1
    assert "extraction_timestamp" in log[0]
