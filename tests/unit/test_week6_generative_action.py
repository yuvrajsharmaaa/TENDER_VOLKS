import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from backend.app.services.tender_indexer import find_similar_tenders
from backend.app.services.structured_advisory_service import (
    StructuredAdvisoryService,
    MissingPredictiveFeaturesError
)
from backend.app.services.rfq_drafting_service import (
    RFQDraftingService,
    RFQDraftRequest,
    LineItemSpec,
    BlockedRFQSendError
)
from backend.app.services.payment_requisition_service import (
    PaymentRequisitionService,
    PaymentRequisitionInput,
    IncompleteRequisitionError
)

# ─────────────────────────────────────────────────────────────────────────────
# 1. Tender Vector Indexer Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_tender_indexer_similar_search():
    results = find_similar_tenders(
        query_target={
            "tender_name": "Supply and Installation of HT Transformers",
            "organization": "NTPC Limited",
            "tender_value": 5000000.0,
            "emd_amount": 100000.0
        },
        top_k=3
    )
    assert len(results) == 3
    for r in results:
        assert "tender_no" in r
        assert "similarity" in r
        assert 0.0 <= r["similarity"] <= 1.0
        assert r["outcome"] in ("Won", "Lost", "Do Not Bid", "Unknown")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Structured Advisory & Gate Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_structured_advisory_gate_enforcement():
    service = StructuredAdvisoryService()
    # Unprocessed fake tender must fail fast
    with pytest.raises(MissingPredictiveFeaturesError):
        service.generate_advisory("FAKE_UNPROCESSED_TENDER_999")


def test_structured_advisory_real_tender():
    service = StructuredAdvisoryService()
    advisory = service.generate_advisory("GEM/2026/B/7357339")
    assert advisory.tender_no == "GEM/2026/B/7357339"
    assert advisory.recommendation in ("bid", "no_bid", "review")
    assert 0.0 <= advisory.confidence <= 1.0
    assert 0.0 <= advisory.win_probability <= 1.0
    assert len(advisory.key_drivers) >= 1
    assert len(advisory.similar_tenders) >= 1
    assert len(advisory.strategic_rationale) > 20


# ─────────────────────────────────────────────────────────────────────────────
# 3. RFQ Drafting & Guardrail Send Blocker Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rfq_drafting_guardrail_injection_and_send_block():
    service = RFQDraftingService()
    req = RFQDraftRequest(
        tender_no="GEM/2026/B/TEST_BROKEN",
        organization="PGCIL",
        tender_title="Procurement of Control Panels",
        line_items=[
            LineItemSpec(
                item_name="Control Relay Panel",
                quantity="Not Found",  # missing
                delivery_location=None, # missing
                status="missing"
            )
        ]
    )
    draft = service.draft_rfq(req)
    assert draft.contains_missing_fields is True
    assert draft.is_ready_for_dispatch is False
    assert "[NEEDS REVIEW:" in draft.draft_body

    # Hard block on send
    with pytest.raises(BlockedRFQSendError):
        service.send_rfq(draft, destination_email="vendor@pgcil.in")


def test_rfq_drafting_clean_case():
    service = RFQDraftingService()
    req = RFQDraftRequest(
        tender_no="GEM/2026/B/TEST_CLEAN",
        organization="GAIL",
        tender_title="Battery Bank SITC",
        line_items=[
            LineItemSpec(
                item_name="2V 500Ah VRLA Cells",
                quantity=100,
                delivery_location="Visakhapatnam",
                technical_spec="IS 15549",
                required_by_date="2026-09-30",
                status="ok"
            )
        ],
        commercial_terms={
            "delivery_timeline": "60 days",
            "payment_terms": "100% against receipt and acceptance"
        }
    )
    draft = service.draft_rfq(req)
    assert draft.contains_missing_fields is False
    assert draft.is_ready_for_dispatch is True
    
    res = service.send_rfq(draft, destination_email="sales@vendor.com")
    assert res["status"] == "SENT"


def test_rfq_drafting_regression_low_confidence_and_leakage():
    """
    REGRESSION TEST:
    Verifies that fields affected by cross-tender value leakage (e.g. placeholder literal 'PLACEHOLDER'
    or 'TBD') or low-confidence OCR extraction (< 0.85) are deterministically routed to '[NEEDS REVIEW: <field>]'
    and strictly block RFQ dispatch.
    """
    service = RFQDraftingService()
    req = RFQDraftRequest(
        tender_no="GEM/2026/B/TEST_LEAKAGE_AND_LOW_CONF",
        organization="PGCIL",
        tender_title="Substation Battery Replacement",
        line_items=[
            # Item 1: Placeholder literal from cross-tender leakage / stubbing
            LineItemSpec(
                item_name="PLACEHOLDER",
                quantity=50,
                delivery_location="Boisar",
                technical_spec="IS 15549",
                confidence_score=0.98,
                status="ok"
            ),
            # Item 2: Low-confidence OCR extraction (e.g. scrambled numeric quantity 0.60 confidence)
            LineItemSpec(
                item_name="Lead Acid Battery Bank",
                quantity=120,
                delivery_location="Palghar",
                technical_spec="IS 16242",
                confidence_score=0.62,
                field_confidences={"quantity": 0.60, "delivery_location": 0.95},
                status="ok"
            )
        ],
        commercial_terms={
            "delivery_timeline": "90 days",
            "payment_terms": "80% supply / 20% SITC"
        },
        terms_confidences={
            "delivery_timeline": 0.95,
            "payment_terms": 0.50  # Low confidence payment terms
        }
    )

    draft = service.draft_rfq(req)

    # 1. Verify guardrails fired for the low-confidence and placeholder fields
    assert draft.contains_missing_fields is True
    assert draft.is_ready_for_dispatch is False
    assert "item_name" in draft.missing_fields_list
    assert "quantity" in draft.missing_fields_list
    assert "payment_terms" in draft.missing_fields_list

    # 2. Verify verbatim [NEEDS REVIEW: ...] tags in draft body
    assert "[NEEDS REVIEW: item_name]" in draft.draft_body
    assert "[NEEDS REVIEW: quantity]" in draft.draft_body
    assert "[NEEDS REVIEW: payment_terms]" in draft.draft_body

    # 3. Verify transmission is strictly blocked
    with pytest.raises(BlockedRFQSendError) as exc_info:
        service.send_rfq(draft, destination_email="vendor@pgcil.in")
    assert "[GUARDRAIL VIOLATION]" in str(exc_info.value)



# ─────────────────────────────────────────────────────────────────────────────
# 4. Payment Requisition Tests (xhtml2pdf / reportlab)
# ─────────────────────────────────────────────────────────────────────────────

def test_payment_requisition_pdf_clean(tmp_path):
    service = PaymentRequisitionService()
    req_input = PaymentRequisitionInput(
        tender_no="GEM/2026/B/7357339",
        organization="GAIL (India) Limited",
        tender_title="Battery Bank Supply",
        requisition_amount=150000.0,
        submission_deadline="15-Sep-2026 15:00 IST",
        beneficiary_name="GAIL (India) Limited",
        recommendation="bid"
    )
    out_pdf = tmp_path / "req_clean.pdf"
    pdf_bytes = service.generate_requisition_pdf(req_input, output_filepath=out_pdf, strict=True)
    assert out_pdf.exists()
    assert len(pdf_bytes) > 1000


def test_payment_requisition_pdf_missing_strict():
    service = PaymentRequisitionService()
    req_input = PaymentRequisitionInput(
        tender_no="GEM/2026/B/MISSING_STRICT",
        organization="BHEL",
        tender_title="Auxiliary Panels",
        requisition_amount="Not Found",
        submission_deadline=None
    )
    with pytest.raises(IncompleteRequisitionError):
        service.generate_requisition_pdf(req_input, strict=True)


def test_payment_requisition_pdf_missing_non_strict(tmp_path):
    service = PaymentRequisitionService()
    req_input = PaymentRequisitionInput(
        tender_no="GEM/2026/B/MISSING_NON_STRICT",
        organization="BHEL",
        tender_title="Auxiliary Panels",
        requisition_amount=None,
        submission_deadline="Not Found"
    )
    out_pdf = tmp_path / "req_missing.pdf"
    pdf_bytes = service.generate_requisition_pdf(req_input, output_filepath=out_pdf, strict=False)
    assert out_pdf.exists()
    assert len(pdf_bytes) > 1000
