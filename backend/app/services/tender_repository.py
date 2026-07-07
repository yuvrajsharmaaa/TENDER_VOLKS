import logging
from typing import Dict, Any
from sqlalchemy import text

logger = logging.getLogger(__name__)

def save_tender_information(db_session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves a mapped tender_information payload into PostgreSQL.
    Tries to perform an upsert (INSERT ... ON CONFLICT (tender_id) DO UPDATE).
    
    db_session: SQLAlchemy Session or Connection object.
    payload: Mapped field dictionary.
    """
    allowed_columns = {
        "tender_id", "te_recommendation", "emd_required", "bid_validity_days", 
        "commercial_evaluation", "maf_required", "delivery_time_supply", 
        "delivery_time_installation_days", "pbg_percentage", "pbg_duration", 
        "sd_duration", "max_ld_percentage", "physical_docs_required", 
        "physical_docs_deadline", "te_rejection_reason", "te_rejection_remarks", 
        "tender_fee_amount", "tender_fee_mode", "emd_mode", 
        "reverse_auction_applicable", "payment_terms_supply", 
        "payment_terms_installation", "sd_percentage", "ld_percentage_per_week", 
        "technical_eligibility_age", "order_value_1", "order_value_2", 
        "order_value_3", "avg_annual_turnover_value", "working_capital_value", 
        "solvency_certificate_value", "net_worth_value", "avg_annual_turnover_type", 
        "processing_fee_amount", "processing_fee_mode", 
        "delivery_time_installation_inclusive", "pbg_required", "sd_required", 
        "working_capital_type", "solvency_certificate_type", "net_worth_type", 
        "courier_address", "te_final_remark", "processing_fee_required", 
        "tender_fee_required", "emd_amount", "pbg_mode", "sd_mode", 
        "ld_required", "work_value_type", "custom_eligibility_criteria", 
        "oem_experience", "tender_value", "physical_docs_type", 
        "te_rejection_proof", "physical_doc_type", "courier_pincode", 
        "courier_state", "courier_city", "courier_address_line_2", 
        "courier_address_line_1", "courier_phone", "courier_name", 
        "client_details_present", "customer_in_contact", "courier_details_present"
    }
    
    clean_payload = {k: v for k, v in payload.items() if k in allowed_columns}
    
    columns = list(clean_payload.keys())
    
    # Formulate raw SQL UPSERT statement using SQLAlchemy parameters syntax (:param)
    placeholders = [f":{col}" for col in columns]
    update_assignments = [f'"{col}" = EXCLUDED."{col}"' for col in columns if col != "tender_id"]
    
    query = text(f"""
        INSERT INTO "public"."tender_information" ({", ".join([f'"{c}"' for c in columns])})
        VALUES ({", ".join(placeholders)})
        ON CONFLICT ("tender_id")
        DO UPDATE SET
            {", ".join(update_assignments)},
            "updated_at" = NOW()
        RETURNING *;
    """)
        
    try:
        res = db_session.execute(query, clean_payload)
        row = res.fetchone()
        if row:
            # Map row to dictionary
            return dict(row._mapping)
        return {"message": "Success", "tender_id": clean_payload.get("tender_id")}
    except Exception as e:
        logger.error(f"SQLAlchemy raw SQL save failed: {e}", exc_info=True)
        raise e
