import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException

from backend.app.api.routes.notify import (
    router as notify_router,
    RateLimiter,
    validate_telegram_url,
    TELEGRAM_BOT_TOKEN_REGEX,
    TELEGRAM_CHAT_ID_REGEX,
)


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(notify_router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


# --------------------------------------------------------------------------
# 1. SSRF & Bot Token Validation Tests (CWE-918)
# --------------------------------------------------------------------------

def test_telegram_bot_token_regex():
    valid_token = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz_1234567"
    assert TELEGRAM_BOT_TOKEN_REGEX.match(valid_token) is not None

    # Invalid tokens (SSRF injection attempts, path traversals, bad chars)
    invalid_tokens = [
        "123:abc",  # too short bot id
        "1234567890:short",  # too short secret
        "1234567890:ABC/../../etc/passwd",  # path traversal
        "1234567890:ABC@evil.com/webhook",  # domain injection
        "http://evil.com/bot",
        "1234567890:ABC?param=1",
    ]
    for bad_token in invalid_tokens:
        assert TELEGRAM_BOT_TOKEN_REGEX.match(bad_token) is None


def test_telegram_chat_id_regex():
    assert TELEGRAM_CHAT_ID_REGEX.match("7118184288") is not None
    assert TELEGRAM_CHAT_ID_REGEX.match("-1001234567890") is not None
    assert TELEGRAM_CHAT_ID_REGEX.match("@my_channel") is not None

    # Invalid chat IDs
    assert TELEGRAM_CHAT_ID_REGEX.match("7118; rm -rf") is None
    assert TELEGRAM_CHAT_ID_REGEX.match("bad_chat_id!#$") is None


def test_validate_telegram_url_valid():
    valid_token = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz_1234567"
    url = validate_telegram_url(valid_token)
    assert url == f"https://api.telegram.org/bot{valid_token}/sendMessage"


def test_validate_telegram_url_invalid_raises_http_exception():
    with pytest.raises(HTTPException) as exc_info:
        validate_telegram_url("invalid_token_format")
    assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------
# 2. RateLimiter Tests (In-Memory and Redis Fallback)
# --------------------------------------------------------------------------

def test_in_memory_rate_limiter():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    # Ensure redis check returns None for this in-memory test
    limiter._get_redis = lambda: None

    client_ip = "192.168.1.100"
    
    # First 3 requests allowed
    assert limiter.is_allowed(client_ip)[0] is True
    assert limiter.is_allowed(client_ip)[0] is True
    assert limiter.is_allowed(client_ip)[0] is True

    # 4th request blocked
    allowed, retry_after = limiter.is_allowed(client_ip)
    assert allowed is False
    assert retry_after >= 1

    # Different client IP is still allowed
    assert limiter.is_allowed("192.168.1.101")[0] is True


def test_redis_rate_limiter_mock():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe
    
    # Mock Redis pipeline results: [zrem_count, zadd_count, [(b'ts', 1000.0)], count, expire_status]
    mock_pipe.execute.return_value = [0, 1, [(b"1000.0", 1000.0)], 1, True]
    limiter._redis_client = mock_redis

    # 1st request -> allowed
    allowed, _ = limiter.is_allowed("10.0.0.1")
    assert allowed is True

    # 3rd request (exceeds limit 2) -> blocked
    mock_pipe.execute.return_value = [0, 1, [(b"1000.0", 1000.0)], 3, True]
    allowed, retry_after = limiter.is_allowed("10.0.0.1")
    assert allowed is False
    assert retry_after >= 1


# --------------------------------------------------------------------------
# 3. API Endpoint Tests
# --------------------------------------------------------------------------

def test_notify_endpoint_missing_credentials(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    
    response = client.post("/api/notify", json={"message": "Test note", "sender": "Tester"})
    assert response.status_code == 400
    assert "credentials not configured" in response.json()["detail"]


def test_notify_endpoint_invalid_chat_id(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz_1234567")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "invalid-chat-id-with-$symbols")

    response = client.post("/api/notify", json={"message": "Test note"})
    assert response.status_code == 400
    assert "Invalid Telegram chat ID format" in response.json()["detail"]


def test_notify_endpoint_invalid_token(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "malicious_token_with_invalid_chars/../../")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    response = client.post("/api/notify", json={"message": "Test note"})
    assert response.status_code == 400
    assert "Invalid Telegram bot token format" in response.json()["detail"]


def test_notify_endpoint_success(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz_1234567")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "7118184288")

    # Mock urlopen to simulate successful Telegram response
    mock_response = MagicMock()
    mock_response.read.return_value = b'{"ok": true, "result": {"message_id": 123}}'
    mock_response.__enter__.return_value = mock_response

    with patch("backend.app.api.routes.notify.urlopen", return_value=mock_response):
        response = client.post("/api/notify", json={"message": "All clauses verified.", "sender": "Auditor"})
        assert response.status_code == 200
        assert response.json() == {"status": "sent"}
