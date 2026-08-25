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
    neo4j_password = password or os.getenv("NEO4J_PASSWORD", "")

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


# ─── Graph Precedence: OVERRIDES Creation & Traversal Resolution ─────────────

OVERRIDE_CATEGORY_RULES: Dict[str, Dict[str, Any]] = {
    "payment_terms": {
        "atc_header_regex": r"^\s*(?:\d{1,2}(?:\.0)?\s+)?(?:TERMS\s+OF\s+PAYMENT|PAYMENT\s+TERMS|MODE\s+OF\s+PAYMENT)\b",
        "atc_body_regex": r"\b(?:\d{1,2}%\s+payment|\d{1,2}%\s+(?:after|upon|on)\s+(?:receipt|delivery|supply|installation))\b",
        "main_header_regex": r"\b(?:payment\s+terms|terms\s+of\s+payment|भुगतान\s+की\s+शर्तें)\b",
        "main_exclusions": [r"\b(?:receipt\s+of\s+payment\s+by\s+the\s+buyer\s+for\s+old\s+items)\b"]
    },
    "price_reduction_ld": {
        "atc_header_regex": r"^\s*(?:\d{1,2}(?:\.0)?\s+)?(?:PRICE\s+REDUCTION\s+SCHEDULE|PRS(?:\s+FOR\s+DELAYED\s+DELIVERY)?|LIQUIDATED\s+DAMAGES)\b",
        "atc_body_regex": r"\b(?:0\.5%\s+per\s+week|maximum\s+5%\s+of|max(?:imum)?\s+prs)\b",
        "main_header_regex": r"\b(?:price\s+reduction\s+schedule|liquidated\s+damages|ld\s+percentage|max\s+ld\s+percentage|विलंब\s+के\s+लिए\s+मूल्य\s+कटौती)\b",
        "main_exclusions": [r"\bdisclaimer\b"]
    },
    "security_deposit": {
        "atc_header_regex": r"^\s*(?:\d{1,2}(?:\.0)?\s+)?(?:CONTRACT\s+PERFORMANCE\s+SECURITY\s*/\s*SECURITY\s+DEPOSIT|SECURITY\s+DEPOSIT(?:\s*\(SD\))?)\b",
        "atc_body_regex": r"\b(?:security\s+deposit|sd\s+percentage|sd\s+duration|sd\s+mode)\b",
        "main_header_regex": r"\b(?:security\s+deposit|सुरक्षा\s+जमा|sd\s+percentage|sd\s+duration|sd\s+mode)\b",
        "main_exclusions": [r"\b(?:epbg|pbg|performance\s+bank\s+guarantee|ईपीबीजी)\b", r"\bdisclaimer\b"]
    },
    "courier_address": {
        "atc_header_regex": r"\([G|H]\)\s+DEALING\s+GAIL[\'’]?S\s+OFFICE\s+ADDRESS|ADDRESS\s+FOR\s+SUBMISSION\s+OF\s+PHYSICAL\s+DOCUMENTS|BDS\s+22\.2",
        "atc_body_regex": r"\b(?:dealing\s+gail['’]?s\s+office\s+address|visakhapatnam\s*-\s*530012|cut-out\s+slip)\b",
        "main_header_regex": r"\b(?:530012|office\s+name\s*\n\s*visakhapatnam|consignees\s*/\s*reporting\s+officer)\b",
        "main_exclusions": [r"\bdisclaimer\b"]
    },
    "client_contacts": {
        "atc_header_regex": r"\([F|G]\)\s+CONTACT\s+DETAILS\s+OF\s+TENDER\s+DEALING\s+OFFICER|BDS\s+39\.[23]|CONTACT\s+DETAILS\s+OF\s+NODAL\s+OFFICER",
        "atc_body_regex": r"\b(?:nodal\s+officer|tender\s+dealing\s+officer|sh\.\s+narasinga\s+rao|narasingha\.rao@gail\.co\.in|s\.\s+patta)\b",
        "main_header_regex": r"\b(?:530012.*vishal\s+kumar|contact\s+officer|reporting\s+officer)\b",
        "main_exclusions": [r"\bdisclaimer\b"]
    },
    "delivery_time": {
        "atc_header_regex": r"^\s*(?:\d{1,2}(?:\.0)?\s+)?(?:DELIVERY\s+SCHEDULE|DELIVERY\s+PERIOD|SUPPLY\s+PERIOD)\b",
        "atc_body_regex": r"\b(?:days\s+from\s+(?:the\s+)?date\s+of\s+(?:purchase\s+order|po|loa|foa)|within\s+\d+\s+weeks)\b",
        "main_header_regex": r"\b(?:delivery\s+days|delivery\s+period|डिलिवरी\s+के\s+दिन|डिलीवरी\s+के\s+दिन)\b",
        "main_exclusions": [r"\bdisclaimer\b", r"\bbuyback\b"]
    }
}


def create_override_relationships(
    tender_id: str,
    driver: Optional[Driver] = None
) -> int:
    """
    Evaluates ATC clauses vs MainDocument clauses within the same tender
    and idempotently creates [:OVERRIDES] relationships in Neo4j based on
    strict clause categorization rules.
    """
    import re
    drv = driver or get_neo4j_driver()
    relationships_created = 0

    with drv.session() as session:
        # 1. Fetch MainDocument and ATCDocument clauses for this tender
        main_clauses = session.run(
            """
            MATCH (m:MainDocument)-[:CONTAINS]->(c:Clause {tender_id: $tender_id})
            RETURN c.id AS id, c.text AS text, c.page_number AS page
            ORDER BY c.page_number, c.reading_order_index
            """,
            tender_id=tender_id
        ).data()

        atc_clauses = session.run(
            """
            MATCH (a:ATCDocument)-[:CONTAINS]->(c:Clause {tender_id: $tender_id})
            RETURN c.id AS id, c.text AS text, c.page_number AS page
            ORDER BY c.page_number, c.reading_order_index
            """,
            tender_id=tender_id
        ).data()

        if not main_clauses or not atc_clauses:
            logger.info(f"[NEO4J] No Main ({len(main_clauses)}) or ATC ({len(atc_clauses)}) clauses found for tender '{tender_id}' to create OVERRIDES.")
            return 0

        # Helper matching functions
        def match_atc(text: str, rule: Dict[str, Any]) -> bool:
            lines = text.strip().split("\n")
            top_lines = " ".join(lines[:2]).upper()
            if "PROCUREMENT OF SEALED LEAD ACID" in top_lines and len(lines) <= 3:
                return False
            first_4_lines = "\n".join(lines[:4])
            if re.search(rule["atc_header_regex"], first_4_lines, re.IGNORECASE):
                return True
            if re.search(rule["atc_header_regex"], text, re.IGNORECASE) and re.search(rule["atc_body_regex"], text, re.IGNORECASE):
                return True
            return False

        def match_main(text: str, rule: Dict[str, Any]) -> bool:
            t = text.strip()
            for ex in rule.get("main_exclusions", []):
                if re.search(ex, t, re.IGNORECASE):
                    return False
            return bool(re.search(rule["main_header_regex"], t, re.IGNORECASE))

        # 2. Evaluate candidate pairs per category and MERGE relationships
        for cat, rules in OVERRIDE_CATEGORY_RULES.items():
            matched_atc = [a for a in atc_clauses if match_atc(a["text"], rules)]
            matched_main = [m for m in main_clauses if match_main(m["text"], rules)]

            for atc_node in matched_atc:
                for main_node in matched_main:
                    session.run(
                        """
                        MATCH (c1:Clause {id: $atc_id})
                        MATCH (c2:Clause {id: $main_id})
                        MERGE (c1)-[r:OVERRIDES {category: $category}]->(c2)
                        ON CREATE SET r.created_at = timestamp()
                        ON MATCH SET r.updated_at = timestamp()
                        """,
                        atc_id=atc_node["id"],
                        main_id=main_node["id"],
                        category=cat
                    )
                    relationships_created += 1
                    logger.info(
                        f"[NEO4J_OVERRIDES] Created (:Clause '{atc_node['id']}')-[:OVERRIDES {{category: '{cat}'}}]->(:Clause '{main_node['id']}')"
                    )

    logger.info(f"[NEO4J] Total [:OVERRIDES] relationships created for tender '{tender_id}': {relationships_created}")
    return relationships_created


def resolve_overridden_main_clauses(
    tender_id: str,
    driver: Optional[Driver] = None
) -> Dict[str, Any]:
    """
    Executes graph traversal across [:OVERRIDES*1..5] paths to identify all MainDocument
    clause IDs that are overridden by authoritative ATCDocument clauses for the tender.
    
    Returns a dict with:
      - 'overridden_clause_ids': Set[str] of MainDocument clause IDs that should be dropped
      - 'override_details': List[Dict[str, Any]] containing audit metadata for each overridden path
    """
    drv = driver or get_neo4j_driver()
    overridden_ids = set()
    override_details = []

    with drv.session() as session:
        # Standard traversal query over transitive OVERRIDES paths
        result = session.run(
            """
            MATCH p = (c1:Clause {tender_id: $tender_id, document_source: 'atc'})-[:OVERRIDES*1..5]->(c2:Clause {tender_id: $tender_id, document_source: 'main_tender'})
            RETURN c1.id AS overriding_id,
                   c1.text AS overriding_text,
                   c2.id AS overridden_id,
                   c2.text AS overridden_text,
                   [r IN relationships(p) | r.category] AS categories,
                   length(p) AS path_length
            """,
            tender_id=tender_id
        ).data()

        for row in result:
            overridden_id = row["overridden_id"]
            overridden_ids.add(overridden_id)
            override_details.append({
                "overriding_id": row["overriding_id"],
                "overridden_id": overridden_id,
                "categories": row["categories"],
                "path_length": row["path_length"],
                "overriding_snippet": (row["overriding_text"] or "").strip()[:100],
                "overridden_snippet": (row["overridden_text"] or "").strip()[:100],
            })
            logger.info(
                f"[GRAPH_PRECEDENCE] Dropped Main Clause '{overridden_id}' overridden by "
                f"ATC Clause '{row['overriding_id']}' for category {row['categories']}"
            )

    return {
        "overridden_clause_ids": overridden_ids,
        "override_details": override_details
    }

