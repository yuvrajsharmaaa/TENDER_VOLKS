import os
import uuid
import logging
from typing import List, Dict, Any, Optional, Union
from threading import Lock

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = Any  # type: ignore

logger = logging.getLogger(__name__)

# Default Configuration
DEFAULT_QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
DEFAULT_QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
DEFAULT_QDRANT_GRPC_PORT = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
DEFAULT_QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", None)

DEFAULT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "tender_clauses")
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_VECTOR_SIZE = 384  # Verified output dimension of all-MiniLM-L6-v2

# Singleton cache for SentenceTransformer model and QdrantClient
_model_instance: Optional[Any] = None
_model_lock = Lock()

_client_instance: Optional[QdrantClient] = None
_client_lock = Lock()


def get_embedding_model(model_name: str = EMBEDDING_MODEL_NAME):
    """
    Returns a thread-safe singleton instance of the SentenceTransformer embedding model.
    Note: On initial load, this requires internet access to download weights from HuggingFace
    unless weights are already cached locally in ~/.cache/huggingface/hub.
    """
    global _model_instance
    if _model_instance is None:
        with _model_lock:
            if _model_instance is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as err:
                    logger.debug(f"[QdrantSession] sentence_transformers is not installed: {err}")
                    raise RuntimeError("sentence-transformers is required for semantic embeddings.") from err
                logger.info(f"[QdrantSession] Loading sentence-transformer model: {model_name}")
                _model_instance = SentenceTransformer(model_name)
    return _model_instance


def get_qdrant_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 10.0
) -> QdrantClient:
    """
    Creates or returns a QdrantClient instance reading connection parameters
    from environment variables with localhost defaults.
    """
    target_url = url or os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL)
    target_api_key = api_key or os.getenv("QDRANT_API_KEY", DEFAULT_QDRANT_API_KEY)
    
    if target_url:
        return QdrantClient(url=target_url, api_key=target_api_key, timeout=timeout)
    
    target_host = host or os.getenv("QDRANT_HOST", DEFAULT_QDRANT_HOST)
    target_port = port or int(os.getenv("QDRANT_PORT", str(DEFAULT_QDRANT_PORT)))
    
    return QdrantClient(
        host=target_host,
        port=target_port,
        api_key=target_api_key,
        timeout=timeout
    )


def create_tender_clauses_collection(
    client: Optional[QdrantClient] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    vector_size: int = EMBEDDING_VECTOR_SIZE,
    distance: Distance = Distance.COSINE,
    recreate: bool = False
) -> bool:
    """
    Ensures the tender_clauses collection exists in Qdrant with the specified
    vector dimension (384 for all-MiniLM-L6-v2) and distance metric (Cosine).
    """
    if client is None:
        client = get_qdrant_client()
        
    exists = client.collection_exists(collection_name=collection_name)
    
    if exists and not recreate:
        logger.debug(f"[QdrantSession] Collection '{collection_name}' already exists.")
        return True

    if exists and recreate:
        logger.info(f"[QdrantSession] Recreating existing collection '{collection_name}'...")
        client.delete_collection(collection_name=collection_name)

    logger.info(f"[QdrantSession] Creating collection '{collection_name}' (vector_size={vector_size}, metric={distance.name})...")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=distance)
    )
    return True


def upsert_paragraph(
    text: str,
    tender_id: Union[str, int],
    page_number: int,
    bounding_box: Optional[Union[Dict[str, Any], Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    point_id: Optional[str] = None,
    client: Optional[QdrantClient] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME
) -> str:
    """
    Embeds a single paragraph/clause text and upserts it into the Qdrant collection
    with provenance metadata (tender_id, page_number, bounding_box, extra metadata).
    
    Returns the point_id (UUID string) of the inserted record.
    """
    if client is None:
        client = get_qdrant_client()
        
    create_tender_clauses_collection(client=client, collection_name=collection_name)
    
    # Ensure point_id is a valid UUID string
    if point_id is None:
        point_uuid = str(uuid.uuid4())
    else:
        try:
            point_uuid = str(uuid.UUID(str(point_id)))
        except ValueError:
            point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(point_id)))

    # Format bounding box if object
    bbox_dict = None
    if bounding_box is not None:
        if hasattr(bounding_box, "model_dump"):
            bbox_dict = bounding_box.model_dump()
        elif isinstance(bounding_box, dict):
            bbox_dict = bounding_box
        else:
            bbox_dict = str(bounding_box)

    payload: Dict[str, Any] = {
        "text": text,
        "tender_id": str(tender_id),
        "page_number": int(page_number),
        "bounding_box": bbox_dict,
    }
    
    if metadata:
        for k, v in metadata.items():
            if k not in payload:
                payload[k] = v

    # Compute dense vector embedding
    model = get_embedding_model()
    vector = model.encode(text).tolist()

    point = PointStruct(
        id=point_uuid,
        vector=vector,
        payload=payload
    )

    client.upsert(
        collection_name=collection_name,
        points=[point]
    )
    logger.debug(f"[QdrantSession] Upserted point {point_uuid} into '{collection_name}' (tender_id={tender_id}, page={page_number})")
    return point_uuid


def upsert_paragraphs_batch(
    items: List[Dict[str, Any]],
    client: Optional[QdrantClient] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    batch_size: int = 64
) -> List[str]:
    """
    Embeds and upserts a list of paragraphs/clauses in batches.
    Each item in `items` should have keys:
      - 'text' (required): string text of the clause/paragraph
      - 'tender_id' (required): string or int
      - 'page_number' (required): int
      - 'bounding_box' (optional): dict
      - 'metadata' (optional): dict
      - 'point_id' (optional): str
    """
    if not items:
        return []
        
    if client is None:
        client = get_qdrant_client()
        
    create_tender_clauses_collection(client=client, collection_name=collection_name)
    model = get_embedding_model()
    
    point_ids: List[str] = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        texts = [item["text"] for item in batch]
        vectors = model.encode(texts).tolist()
        
        points: List[PointStruct] = []
        for item, vector in zip(batch, vectors):
            pid = item.get("point_id")
            if pid is None:
                point_uuid = str(uuid.uuid4())
            else:
                try:
                    point_uuid = str(uuid.UUID(str(pid)))
                except ValueError:
                    point_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(pid)))
            
            bbox_dict = None
            raw_bbox = item.get("bounding_box")
            if raw_bbox is not None:
                if hasattr(raw_bbox, "model_dump"):
                    bbox_dict = raw_bbox.model_dump()
                elif isinstance(raw_bbox, dict):
                    bbox_dict = raw_bbox
                else:
                    bbox_dict = str(raw_bbox)

            payload: Dict[str, Any] = {
                "text": item["text"],
                "tender_id": str(item["tender_id"]),
                "page_number": int(item["page_number"]),
                "bounding_box": bbox_dict,
            }
            if item.get("metadata"):
                for k, v in item["metadata"].items():
                    if k not in payload:
                        payload[k] = v
                        
            points.append(PointStruct(id=point_uuid, vector=vector, payload=payload))
            point_ids.append(point_uuid)
            
        client.upsert(collection_name=collection_name, points=points)
        
    return point_ids


def search_clauses(
    query: str,
    limit: int = 5,
    score_threshold: Optional[float] = None,
    tender_id: Optional[Union[str, int]] = None,
    client: Optional[QdrantClient] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME
) -> List[Dict[str, Any]]:
    """
    Takes a natural language query string, encodes it with all-MiniLM-L6-v2,
    and returns top-K most semantically similar clauses with their payloads and scores.
    """
    if client is None:
        client = get_qdrant_client()

    create_tender_clauses_collection(client=client, collection_name=collection_name)
    
    model = get_embedding_model()
    query_vector = model.encode(query).tolist()

    query_filter = None
    if tender_id is not None:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="tender_id",
                    match=MatchValue(value=str(tender_id))
                )
            ]
        )

    # Use query_points (or search)
    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=limit,
        score_threshold=score_threshold,
        query_filter=query_filter,
        with_payload=True
    )

    results = []
    for point in response.points:
        results.append({
            "id": str(point.id),
            "score": float(point.score),
            "payload": point.payload or {},
            "text": point.payload.get("text", "") if point.payload else ""
        })

    return results
