import pytest
from backend.app.services.email_service import send_email_with_attachments

def test_send_email_mock_fallback(caplog):
    import logging
    # Ensure SMTP env parameters are cleared so it falls back to log mocking
    import os
    orig_host = os.environ.get("SMTP_HOST")
    orig_user = os.environ.get("SMTP_USER")
    if "SMTP_HOST" in os.environ: del os.environ["SMTP_HOST"]
    if "SMTP_USER" in os.environ: del os.environ["SMTP_USER"]
    
    with caplog.at_level(logging.INFO):
        send_email_with_attachments("test@example.com", "Test Subject", "Test Body", ["nonexistent.csv"])
        
    assert "email_mock_dispatch" in caplog.text
    
    # Restore env
    if orig_host: os.environ["SMTP_HOST"] = orig_host
    if orig_user: os.environ["SMTP_USER"] = orig_user
