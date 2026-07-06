# Week 1 MVP Scope Definition

This document locks down the architecture and scope boundaries for the Week 1 and Week 2 implementation phases of the Tender OCR and Extraction pipeline.

---

## Included Now

The core pipeline is dedicated to robust, layout-aware document ingestion and metadata extraction:
- **Tender Project Creation:** Simple API/DB records grouping related tender files.
- **Document Upload:** Supporting PDFs (digital & scanned) and images (JPEG, PNG).
- **Object Storage:** Persistent storage for raw files and processed artifacts (using MinIO / private local directories).
- **Background Jobs:** Asynchronous queueing (using Redis + Celery) for compute-heavy OCR and layout analysis tasks.
- **PDF/Image Preprocessing:** Converting vector pages to high-resolution PNGs and image corrections (binarization, deskewing).
- **Optical Character Recognition (OCR):** Multi-lingual (English and Hindi) text detection and character recognition via PaddleOCR.
- **Layout and Table Parsing:** Structural element classification (headings, paragraphs) and HTML table cell extraction via PP-StructureV3.
- **Raw OCR & Layout Storage:** Saving structured page-level text, layout boxes, and tables in strict schema-validated JSONs.
- **Deterministic Field Extraction:** Keyword anchors (Hindi + English), nearest-neighbor proximity, and table row groupings.

---

## Excluded Now

These advanced systems are explicitly postponed to subsequent phases of development to maintain focus on core parsing reliability:
- **Retrieval-Augmented Generation (RAG):** Multi-document semantic search and QA over tender databases.
- **Vector Database:** Indexing text embeddings (e.g. Qdrant, PgVector).
- **Analytics Dashboards:** Aggregated metrics showing bid success rates, timelines, or auditor throughput.
- **Fine-Tuned Domain Model Training:** Custom weights training for LayoutLMv3 or specialized NER engines on tender bodies.
- **Production Single Sign-On (SSO):** Corporate integrations (e.g., SAML, Active Directory, Okta).
- **Advanced Approval Automation:** Automatic email dispatching or multi-stage signer verification chains.
