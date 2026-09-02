import pytest
from decimal import Decimal
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models.pqr_credential import PQRCredential
from backend.app.db.session import SessionLocal
from scripts.load_pqr_credentials import (
    parse_file_entries,
    resolve_local_document_path,
    to_date_or_none,
    to_numeric_or_none
)


def test_parse_file_entries():
    # JSON array strings
    assert parse_file_entries('["pqr-po/123.pdf"]') == ["pqr-po/123.pdf"]
    assert parse_file_entries('["pqr-po/1.pdf", "pqr-po/2.pdf"]') == ["pqr-po/1.pdf", "pqr-po/2.pdf"]
    # Empty / null variations
    assert parse_file_entries("[]") == []
    assert parse_file_entries(None) == []
    assert parse_file_entries("nan") == []
    # Comma separated
    assert parse_file_entries("pqr-po/1.pdf, pqr-po/2.pdf") == ["pqr-po/1.pdf", "pqr-po/2.pdf"]


def test_missing_files_resolve_to_none():
    # Known missing files
    resolved_missing_1 = resolve_local_document_path(
        '["pqr-performance-certificate/1745317635.pdf"]',
        "pqr-performance-certificate"
    )
    assert resolved_missing_1 is None

    resolved_missing_2 = resolve_local_document_path(
        '["pqr-performance-certificate/1749881568.pdf"]',
        "pqr-performance-certificate"
    )
    assert resolved_missing_2 is None


def test_existing_file_resolves_to_path():
    resolved = resolve_local_document_path(
        '["pqr-po/1738662324.pdf"]',
        "pqr-po"
    )
    assert resolved == "pqr-po/1738662324.pdf"


def test_pqr_credentials_db_contents():
    with SessionLocal() as session:
        # Total count
        total = session.query(PQRCredential).count()
        assert total == 165

        # Zero resolvable documents
        zero_doc_count = session.query(PQRCredential).filter(
            PQRCredential.po_document.is_(None),
            PQRCredential.sap_gem_po_document.is_(None),
            PQRCredential.completion_document.is_(None),
            PQRCredential.performance_certificate.is_(None)
        ).count()
        assert zero_doc_count == 0

        # Known missing files resolution
        rec_29 = session.query(PQRCredential).filter(PQRCredential.id == 29).first()
        assert rec_29 is not None
        assert rec_29.performance_certificate is None

        rec_53 = session.query(PQRCredential).filter(PQRCredential.id == 53).first()
        assert rec_53 is not None
        assert rec_53.performance_certificate is None

        # Implausible date row (Record 108)
        rec_108 = session.query(PQRCredential).filter(PQRCredential.id == 108).first()
        assert rec_108 is not None
        assert rec_108.completion_date_flagged is True
        assert rec_108.completion_date == date(5024, 5, 11)

        # Value typo fix (Record 136)
        rec_136 = session.query(PQRCredential).filter(PQRCredential.id == 136).first()
        assert rec_136 is not None
        assert rec_136.value == Decimal("21195842.66")
