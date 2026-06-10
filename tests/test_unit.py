"""Unit tests — one test per acceptance criterion."""
import time
import pytest
from sandbox.src.token_store import TokenStore, TOKEN_TTL_SECONDS
from sandbox.src.rate_limiter import RateLimiter, MAX_REQUESTS
from sandbox.src.email_dispatcher import EmailDispatcher
from sandbox.src.password_reset import PasswordResetService


# AC-001: User can request a reset by submitting their registered email
def test_ac001_request_creates_token():
    svc = PasswordResetService()
    result = svc.request_reset("user@example.com")
    assert result["success"] is True
    assert "token" in result


# AC-002: System sends a reset email within 60 seconds
def test_ac002_email_sent_on_request():
    svc = PasswordResetService()
    svc.request_reset("user@example.com")
    assert len(svc.emailer.sent) == 1
    assert svc.emailer.sent[0]["to"] == "user@example.com"


# AC-003: Reset link expires after 30 minutes
def test_ac003_token_expires():
    store = TokenStore()
    token = store.create_token("user@example.com")
    # Manually backdate the token
    import hashlib
    h = hashlib.sha256(token.encode()).hexdigest()
    store._store[h].created_at = time.time() - TOKEN_TTL_SECONDS - 1
    assert store.validate_token(token) is None


# AC-004: Token is invalidated after successful use
def test_ac004_token_single_use():
    store = TokenStore()
    token = store.create_token("user@example.com")
    assert store.validate_token(token) == "user@example.com"
    assert store.validate_token(token) is None  # second use fails


# AC-005: User sees success confirmation after password is changed
def test_ac005_success_message_on_reset():
    svc = PasswordResetService()
    result = svc.request_reset("user@example.com")
    done = svc.complete_reset(result["token"], "newpass123", "newpass123")
    assert done["success"] is True
    assert "message" in done


# AC-006: Rate limiting blocks more than 3 requests per hour
def test_ac006_rate_limiting():
    limiter = RateLimiter()
    for _ in range(MAX_REQUESTS):
        assert limiter.is_allowed("user@example.com") is True
    assert limiter.is_allowed("user@example.com") is False


# Additional unit tests
def test_passwords_must_match():
    svc = PasswordResetService()
    r = svc.request_reset("user@example.com")
    result = svc.complete_reset(r["token"], "newpass123", "different")
    assert result["error"] == "passwords_do_not_match"


def test_invalid_token_rejected():
    svc = PasswordResetService()
    result = svc.complete_reset("not-a-real-token", "newpass123", "newpass123")
    assert result["error"] == "invalid_or_expired_token"


def test_invalid_email_rejected():
    dispatcher = EmailDispatcher()
    assert dispatcher.send_reset_email("not-an-email", "sometoken") is False
