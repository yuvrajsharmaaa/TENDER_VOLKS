import os
import logging
from typing import Dict, Any, List, Optional
from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)

_driver: Optional[Driver] = None


def get_neo4j_driver(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None
) -> Driver:
    """
    Returns a singleton Neo4j driver instance connected using environment variables or passed args.
    """
    global _driver
    if _driver is not None:
        return _driver

    neo4j_uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = user or os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = password or os.getenv("NEO4J_PASSWORD", "tenderpassword")

    _driver = GraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_password)
    )
    logger.info(f"[NEO4J] Connected to Neo4j instance at {neo4j_uri} as '{neo4j_user}'")
    return _driver


def close_neo4j_driver() -> None:
    """Closes the active Neo4j driver connection."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("[NEO4J] Driver connection closed.")


def init_neo4j_schema(driver: Optional[Driver] = None) -> None:
    """
    Initializes uniqueness constraints on all tender graph node types (Tender, MainDocument, ATCDocument, Clause).
    Safe for idempotent startup.
    """
    drv = driver or get_neo4j_driver()
    constraints = [
        "CREATE CONSTRAINT tender_id_unique IF NOT EXISTS FOR (t:Tender) REQUIRE t.id IS UNIQUE",
        "CREATE CONSTRAINT main_doc_id_unique IF NOT EXISTS FOR (d:MainDocument) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT atc_doc_id_unique IF NOT EXISTS FOR (d:ATCDocument) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT clause_id_unique IF NOT EXISTS FOR (c:Clause) REQUIRE c.id IS UNIQUE",
    ]

    with drv.session() as session:
        for q in constraints:
            try:
                session.run(q)
                logger.info(f"[NEO4J] Executed schema constraint: {q}")
            except Exception as e:
                logger.warning(f"[NEO4J] Failed or skipped constraint '{q}': {e}")


def sync_tender_graph(
    tender_id: str,
    tender_title: str,
    main_doc: Dict[str, Any],
    main_clauses: List[Dict[str, Any]],
    atc_docs: Optional[List[Dict[str, Any]]] = None,
    driver: Optional[Driver] = None
) -> Dict[str, int]:
    """
    Merges Tender, MainDocument, ATCDocument, and Clause nodes and relationships into the Neo4j graph.
    All write queries use MERGE to guarantee idempotent re-execution without duplicate nodes.
    
    Relationships created:
    - (Tender)-[:HAS_MAIN_DOCUMENT]->(MainDocument)
    - (MainDocument)-[:CONTAINS]->(Clause)
    - (ATCDocument)-[:ATTACHED_TO]->(MainDocument)
    - (Tender)-[:HAS_ATC_DOCUMENT]->(ATCDocument)
    - (ATCDocument)-[:CONTAINS]->(Clause)
    """
    drv = driver or get_neo4j_driver()
    atc_docs = atc_docs or []
    nodes_created = {"tender": 1, "main_doc": 1, "atc_docs": len(atc_docs), "clauses": len(main_clauses)}

    with drv.session() as session:
        # 1. Merge Tender and MainDocument
        main_doc_id = main_doc.get("id") or f"doc_{tender_id}_main"
        main_doc_name = main_doc.get("name", "Main Tender Document")
        main_doc_pages = main_doc.get("page_count", 0)

        session.run(
            """
            MERGE (t:Tender {id: $tender_id})
            ON CREATE SET t.title = $tender_title, t.created_at = timestamp()
            ON MATCH SET t.title = $tender_title, t.updated_at = timestamp()

            MERGE (m:MainDocument {id: $main_doc_id})
            ON CREATE SET m.name = $main_doc_name, m.page_count = $main_doc_pages, m.tender_id = $tender_id, m.created_at = timestamp()
            ON MATCH SET m.name = $main_doc_name, m.page_count = $main_doc_pages, m.updated_at = timestamp()

            MERGE (t)-[:HAS_MAIN_DOCUMENT]->(m)
            """,
            tender_id=tender_id,
            tender_title=tender_title,
            main_doc_id=main_doc_id,
            main_doc_name=main_doc_name,
            main_doc_pages=main_doc_pages
        )

        # 2. Merge MainDocument Clauses
        for clause in main_clauses:
            clause_id = clause.get("id") or f"{main_doc_id}_{clause.get('region_id', 'c0')}"
            clause_text = clause.get("text", "")
            clause_page = clause.get("page_number", 1)
            reading_order = clause.get("reading_order_index", 0)
            bbox = clause.get("bounding_box", {})
            confidence = clause.get("confidence", 1.0)
            clause_type = clause.get("clause_type", "clause")

            session.run(
                """
                MERGE (c:Clause {id: $clause_id})
                ON CREATE SET
                    c.text = $clause_text,
                    c.page_number = $clause_page,
                    c.reading_order_index = $reading_order,
                    c.confidence = $confidence,
                    c.clause_type = $clause_type,
                    c.document_source = 'main_tender',
                    c.tender_id = $tender_id,
                    c.bbox_x1 = $x1,
                    c.bbox_y1 = $y1,
                    c.bbox_x2 = $x2,
                    c.bbox_y2 = $y2,
                    c.created_at = timestamp()
                ON MATCH SET
                    c.text = $clause_text,
                    c.confidence = $confidence,
                    c.updated_at = timestamp()

                WITH c
                MATCH (m:MainDocument {id: $main_doc_id})
                MERGE (m)-[:CONTAINS]->(c)
                """,
                clause_id=clause_id,
                clause_text=clause_text,
                clause_page=clause_page,
                reading_order=reading_order,
                confidence=confidence,
                clause_type=clause_type,
                tender_id=tender_id,
                main_doc_id=main_doc_id,
                x1=bbox.get("x1", 0),
                y1=bbox.get("y1", 0),
                x2=bbox.get("x2", 0),
                y2=bbox.get("y2", 0)
            )

        # 3. Merge ATCDocuments and their Clauses
        for atc_entry in atc_docs:
            atc_info = atc_entry.get("doc", {})
            atc_doc_id = atc_info.get("id") or f"doc_{tender_id}_atc_{atc_info.get('name', 'child')}"
            atc_doc_name = atc_info.get("name", "ATC Document")
            atc_doc_pages = atc_info.get("page_count", 0)
            atc_url = atc_info.get("url", "")
            atc_local_path = str(atc_info.get("local_path", ""))

            session.run(
                """
                MERGE (atc:ATCDocument {id: $atc_doc_id})
                ON CREATE SET
                    atc.name = $atc_doc_name,
                    atc.page_count = $atc_doc_pages,
                    atc.url = $atc_url,
                    atc.local_path = $atc_local_path,
                    atc.tender_id = $tender_id,
                    atc.created_at = timestamp()
                ON MATCH SET
                    atc.name = $atc_doc_name,
                    atc.page_count = $atc_doc_pages,
                    atc.local_path = $atc_local_path,
                    atc.updated_at = timestamp()

                WITH atc
                MATCH (m:MainDocument {id: $main_doc_id})
                MERGE (atc)-[:ATTACHED_TO]->(m)

                WITH atc
                MATCH (t:Tender {id: $tender_id})
                MERGE (t)-[:HAS_ATC_DOCUMENT]->(atc)
                """,
                atc_doc_id=atc_doc_id,
                atc_doc_name=atc_doc_name,
                atc_doc_pages=atc_doc_pages,
                atc_url=atc_url,
                atc_local_path=atc_local_path,
                main_doc_id=main_doc_id,
                tender_id=tender_id
            )

            atc_clauses = atc_entry.get("clauses", [])
            nodes_created["clauses"] += len(atc_clauses)
            for clause in atc_clauses:
                clause_id = clause.get("id") or f"{atc_doc_id}_{clause.get('region_id', 'c0')}"
                clause_text = clause.get("text", "")
                clause_page = clause.get("page_number", 1)
                reading_order = clause.get("reading_order_index", 0)
                bbox = clause.get("bounding_box", {})
                confidence = clause.get("confidence", 1.0)
                clause_type = clause.get("clause_type", "clause")

                session.run(
                    """
                    MERGE (c:Clause {id: $clause_id})
                    ON CREATE SET
                        c.text = $clause_text,
                        c.page_number = $clause_page,
                        c.reading_order_index = $reading_order,
                        c.confidence = $confidence,
                        c.clause_type = $clause_type,
                        c.document_source = 'atc',
                        c.tender_id = $tender_id,
                        c.bbox_x1 = $x1,
                        c.bbox_y1 = $y1,
                        c.bbox_x2 = $x2,
                        c.bbox_y2 = $y2,
                        c.created_at = timestamp()
                    ON MATCH SET
                        c.text = $clause_text,
                        c.confidence = $confidence,
                        c.updated_at = timestamp()

                    WITH c
                    MATCH (atc:ATCDocument {id: $atc_doc_id})
                    MERGE (atc)-[:CONTAINS]->(c)
                    """,
                    clause_id=clause_id,
                    clause_text=clause_text,
                    clause_page=clause_page,
                    reading_order=reading_order,
                    confidence=confidence,
                    clause_type=clause_type,
                    tender_id=tender_id,
                    atc_doc_id=atc_doc_id,
                    x1=bbox.get("x1", 0),
                    y1=bbox.get("y1", 0),
                    x2=bbox.get("x2", 0),
                    y2=bbox.get("y2", 0)
                )

    logger.info(
        f"[NEO4J] Graph synchronized for tender '{tender_id}': "
        f"1 MainDocument, {len(atc_docs)} ATCDocument(s), {nodes_created['clauses']} Clause(s)"
    )
    return nodes_created
