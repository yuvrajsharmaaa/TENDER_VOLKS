import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from backend.app.db.qdrant_session import get_embedding_model, EMBEDDING_VECTOR_SIZE

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
TENDER_INDEX_COLLECTION = os.getenv("QDRANT_TENDER_INDEX", "tender_master_index")
LOCAL_STORAGE_DIR = ROOT_DIR / "data" / "qdrant_storage"

_qdrant_client_instance: Optional[QdrantClient] = None


def get_indexer_qdrant_client() -> QdrantClient:
    """
    Returns a Qdrant client connected to Qdrant server or persistent local disk storage.
    """
    global _qdrant_client_instance
    if _qdrant_client_instance is not None:
        return _qdrant_client_instance

    load_dotenv(ROOT_DIR / ".env.dev")
    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    url = os.getenv("QDRANT_URL", None)

    # Fast probe to see if remote port is actually open
    server_reachable = False
    if not url:
        import socket
        try:
            with socket.create_connection((host, port), timeout=0.1):
                server_reachable = True
        except (OSError, ConnectionRefusedError):
            server_reachable = False

    if url or server_reachable:
        try:
            client = QdrantClient(url=url) if url else QdrantClient(host=host, port=port, timeout=2.0)
            client.get_collections()
            logger.info("[TenderIndexer] Connected to Qdrant server at %s", url or f"{host}:{port}")
            _qdrant_client_instance = client
            return _qdrant_client_instance
        except Exception as e:
            logger.debug("[TenderIndexer] Qdrant server not accessible (%s). Using local storage.", e)

    # Fallback to local persistent disk storage
    LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("[TenderIndexer] Initializing local Qdrant storage at %s", LOCAL_STORAGE_DIR)
    _qdrant_client_instance = QdrantClient(path=str(LOCAL_STORAGE_DIR))
    return _qdrant_client_instance



def ensure_tender_index_collection(client: Optional[QdrantClient] = None, collection_name: str = TENDER_INDEX_COLLECTION) -> bool:
    if client is None:
        client = get_indexer_qdrant_client()

    collections = client.get_collections().collections
    exists = any(c.name == collection_name for c in collections)
    if not exists:
        logger.info("[TenderIndexer] Creating collection '%s' (dim=%d, distance=COSINE)...", collection_name, EMBEDDING_VECTOR_SIZE)
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_VECTOR_SIZE, distance=Distance.COSINE)
        )
    return True


def build_tender_composite_text(row: Dict[str, Any]) -> str:
    """
    Constructs a rich natural language summary of a tender for dense embedding.
    """
    t_no = str(row.get("tender_no") or "").strip()
    t_name = str(row.get("tender_name") or t_no).strip()
    org = str(row.get("organization") or row.get("client") or row.get("department") or "Unknown Organization").strip()
    cat = str(row.get("item_category") or row.get("category") or "General Procurement").strip()
    
    val = row.get("tender_value") or row.get("estimated_cost") or 0.0
    try:
        val_f = float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        val_f = 0.0

    emd = row.get("emd_amount") or 0.0
    try:
        emd_f = float(emd) if emd is not None else 0.0
    except (ValueError, TypeError):
        emd_f = 0.0

    delivery = row.get("delivery_time_supply_days") or row.get("delivery_time_supply") or "Standard"
    exp = row.get("technical_experience_years_req") or row.get("technical_eligibility_age") or 0
    pbg = row.get("pbg_percentage") or 0.0
    mse = row.get("mse_purchase_preference") or "No"
    outcome = str(row.get("outcome") or "Pending").strip()

    parts = [
        f"Tender: {t_name}",
        f"Bid Number: {t_no}",
        f"Procuring Organization: {org}",
        f"Category: {cat}",
        f"Estimated Value: INR {val_f:,.2f}" if val_f > 0 else "Estimated Value: Not Specified",
        f"EMD Amount: INR {emd_f:,.2f}" if emd_f > 0 else "EMD: Exempted/Zero",
        f"Delivery Timeline: {delivery} days",
        f"Experience Requirement: {exp} years" if exp else "Experience: Standard",
        f"PBG Percentage: {pbg}%" if pbg else "PBG: Standard",
        f"MSE Preference: {mse}",
        f"Historical Volks Outcome: {outcome}"
    ]
    return " | ".join(parts)


def index_all_tenders(batch_size: int = 64, force_reindex: bool = False) -> Dict[str, Any]:
    """
    Loads all labeled (Won/Lost) and pending tenders from DB and CSV, embeds them,
    and indexes them in Qdrant collection `tender_master_index`.
    """
    load_dotenv(ROOT_DIR / ".env.dev")
    client = get_indexer_qdrant_client()
    
    if force_reindex:
        try:
            client.delete_collection(collection_name=TENDER_INDEX_COLLECTION)
        except Exception:
            pass
    
    ensure_tender_index_collection(client=client, collection_name=TENDER_INDEX_COLLECTION)
    model = get_embedding_model()

    # 1. Fetch data from DB
    db_url = os.getenv("DATABASE_URL")
    records: List[Dict[str, Any]] = []

    # Read classified-tenders.xlsx for canonical tender_names
    name_lookup = {}
    classified_xlsx = ROOT_DIR / "classified-tenders.xlsx"
    if classified_xlsx.exists():
        try:
            df_class = pd.read_excel(classified_xlsx, sheet_name="All Tenders")
            for _, r in df_class.iterrows():
                t_no = str(r.get("tender_no", "")).strip()
                t_name = str(r.get("tender_name", "")).strip()
                if t_no and t_name and t_name != "nan":
                    name_lookup[t_no] = t_name
        except Exception as e:
            logger.warning("[TenderIndexer] Could not read classified-tenders.xlsx: %s", e)

    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    o.tender_no,
                    o.tender_id,
                    o.outcome,
                    i.tender_name,
                    i.organization,
                    i.department,
                    i.client,
                    i.tender_value,
                    i.emd_amount,
                    i.emd_required,
                    i.pbg_percentage,
                    i.technical_eligibility_age AS technical_experience_years_req,
                    i.delivery_time_supply AS delivery_time_supply_days,
                    i.mse_purchase_preference,
                    i.reverse_auction_applicable
                FROM tender_outcomes o
                LEFT JOIN tender_information i ON o.tender_id = i.tender_id
                WHERE o.tender_no IS NOT NULL;
            """)
            db_rows = cur.fetchall()
            for r in db_rows:
                rec = dict(r)
                t_no = rec.get("tender_no")
                if t_no in name_lookup and (not rec.get("tender_name") or rec.get("tender_name") == t_no):
                    rec["tender_name"] = name_lookup[t_no]
                records.append(rec)
            conn.close()
            logger.info("[TenderIndexer] Loaded %d tender records from Postgres database.", len(records))
        except Exception as e:
            logger.warning("[TenderIndexer] Could not load from DB: %s", e)

    # If DB had no records or missing, fallback to training_set_win_loss.csv
    if not records:
        csv_path = ROOT_DIR / "artifacts" / "training_set_win_loss.csv"
        if csv_path.exists():
            df_csv = pd.read_csv(csv_path)
            for _, r in df_csv.iterrows():
                rec = r.to_dict()
                t_no = rec.get("tender_no")
                if t_no in name_lookup:
                    rec["tender_name"] = name_lookup[t_no]
                records.append(rec)
            logger.info("[TenderIndexer] Loaded %d tender records from training_set_win_loss.csv", len(records))

    if not records:
        raise RuntimeError("No tender records found to index in Qdrant.")

    # Deduplicate by tender_no
    unique_map = {}
    for r in records:
        t_no = str(r.get("tender_no", "")).strip()
        if t_no and t_no not in unique_map:
            unique_map[t_no] = r
    records = list(unique_map.values())

    logger.info("[TenderIndexer] Embedding and indexing %d unique tenders...", len(records))

    import uuid
    points: List[PointStruct] = []
    texts = [build_tender_composite_text(r) for r in records]
    vectors = model.encode(texts, batch_size=batch_size, show_progress_bar=False).tolist()

    for i, (rec, vec, txt) in enumerate(zip(records, vectors, texts)):
        t_no = str(rec.get("tender_no", f"TENDER_{i}"))
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, t_no))
        
        payload = {
            "tender_no": t_no,
            "tender_id": rec.get("tender_id"),
            "tender_name": rec.get("tender_name") or t_no,
            "organization": rec.get("organization") or rec.get("client") or "Unknown",
            "outcome": rec.get("outcome") or "Pending",
            "tender_value": float(rec.get("tender_value") or 0.0) if rec.get("tender_value") is not None else 0.0,
            "emd_amount": float(rec.get("emd_amount") or 0.0) if rec.get("emd_amount") is not None else 0.0,
            "delivery_time_supply_days": rec.get("delivery_time_supply_days") or 0,
            "technical_experience_years_req": rec.get("technical_experience_years_req") or 0,
            "pbg_percentage": float(rec.get("pbg_percentage") or 0.0) if rec.get("pbg_percentage") is not None else 0.0,
            "composite_text": txt
        }
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))

    # Upsert in chunks
    total_upserted = 0
    for chunk_start in range(0, len(points), batch_size):
        chunk = points[chunk_start:chunk_start + batch_size]
        client.upsert(collection_name=TENDER_INDEX_COLLECTION, points=chunk)
        total_upserted += len(chunk)

    logger.info("[TenderIndexer] Successfully indexed %d tenders in collection '%s'.", total_upserted, TENDER_INDEX_COLLECTION)
    return {
        "status": "success",
        "collection_name": TENDER_INDEX_COLLECTION,
        "indexed_count": total_upserted
    }


def find_similar_tenders(
    query_target: Union[str, Dict[str, Any]],
    top_k: int = 3,
    exclude_tender_no: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Finds the top-K semantically and commercially nearest historical tenders in Qdrant.
    
    Args:
        query_target: Tender number string, text description, or tender attribute dictionary.
        top_k: Number of nearest neighbors to return.
        exclude_tender_no: Tender number to exclude (prevent matching self).
    """
    client = get_indexer_qdrant_client()
    ensure_tender_index_collection(client=client, collection_name=TENDER_INDEX_COLLECTION)
    model = get_embedding_model()

    if isinstance(query_target, dict):
        query_text = build_tender_composite_text(query_target)
        if not exclude_tender_no and query_target.get("tender_no"):
            exclude_tender_no = str(query_target["tender_no"]).strip()
    elif isinstance(query_target, str):
        query_text = query_target
        if not exclude_tender_no and len(query_target) < 60 and not " " in query_target:
            exclude_tender_no = query_target.strip()
    else:
        query_text = str(query_target)

    query_vector = model.encode(query_text).tolist()

    # Search top_k + 2 to account for potential self-exclusion
    limit = top_k + 3 if exclude_tender_no else top_k
    response = client.query_points(
        collection_name=TENDER_INDEX_COLLECTION,
        query=query_vector,
        limit=limit,
        with_payload=True
    )

    results: List[Dict[str, Any]] = []
    for pt in response.points:
        payload = pt.payload or {}
        t_no = payload.get("tender_no", "")
        if exclude_tender_no and (t_no.lower() == exclude_tender_no.lower() or exclude_tender_no.lower() in t_no.lower()):
            continue

        similarity = float(pt.score)
        
        # Build key overlap explanation
        overlap_notes = []
        if payload.get("organization"):
            overlap_notes.append(f"Buyer: {payload['organization']}")
        if payload.get("tender_value"):
            overlap_notes.append(f"Value: ₹{payload['tender_value']:,.0f}")
        if payload.get("outcome"):
            overlap_notes.append(f"Outcome: {payload['outcome']}")

        results.append({
            "tender_no": t_no,
            "tender_name": payload.get("tender_name", t_no),
            "organization": payload.get("organization", "Unknown"),
            "outcome": payload.get("outcome", "Unknown"),
            "similarity": round(similarity, 4),
            "tender_value": payload.get("tender_value", 0.0),
            "emd_amount": payload.get("emd_amount", 0.0),
            "delivery_time_supply_days": payload.get("delivery_time_supply_days", 0),
            "key_overlap": "; ".join(overlap_notes),
            "composite_text": payload.get("composite_text", "")
        })

        if len(results) >= top_k:
            break

    return results
