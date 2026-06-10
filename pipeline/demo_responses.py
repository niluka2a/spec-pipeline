"""
Pre-written demo responses for all AI stages.
Used when PIPELINE_DEMO_MODE=true — no API calls made.
"""

DEMO_PLAN = {
    "technical_design_summary": (
        "Implement a secure password reset flow using time-limited email tokens. "
        "The feature includes token generation, email dispatch, token validation, "
        "and password update logic with rate limiting."
    ),
    "implementation_tasks": [
        {"id": "T-001", "title": "Token generator", "description": "Generate cryptographically secure reset tokens", "estimated_effort": "small"},
        {"id": "T-002", "title": "Rate limiter", "description": "Block more than 3 requests/hour per email", "estimated_effort": "small"},
        {"id": "T-003", "title": "Token store", "description": "Store and validate tokens with expiry", "estimated_effort": "medium"},
        {"id": "T-004", "title": "Password updater", "description": "Validate and apply new password", "estimated_effort": "medium"},
        {"id": "T-005", "title": "Email dispatcher", "description": "Send reset email with token link", "estimated_effort": "medium"},
    ],
    "impacted_modules": [
        "sandbox/src/token_store.py",
        "sandbox/src/rate_limiter.py",
        "sandbox/src/password_reset.py",
        "sandbox/src/email_dispatcher.py",
    ],
    "risk_considerations": [
        "Tokens must use constant-time comparison to prevent timing attacks",
        "Rate limiting state must persist across requests",
        "Expired tokens must be cleaned up to prevent storage bloat",
    ],
    "test_strategy": (
        "Unit test each module independently with mocked dependencies. "
        "Integration test the full reset flow end-to-end. "
        "Each test maps to an acceptance criterion ID."
    ),
}

DEMO_IMPLEMENTATION = {
    "sandbox/src/token_store.py": '''\
"""Token store — manages reset tokens with expiry and single-use enforcement."""
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field


TOKEN_TTL_SECONDS = 1800  # 30 minutes


@dataclass
class TokenRecord:
    token_hash: str
    email: str
    created_at: float
    used: bool = False


class TokenStore:
    def __init__(self) -> None:
        self._store: dict[str, TokenRecord] = {}

    def create_token(self, email: str) -> str:
        """Generate a secure token, store its hash, return the raw token."""
        raw = secrets.token_hex(32)
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        self._store[token_hash] = TokenRecord(
            token_hash=token_hash,
            email=email,
            created_at=time.time(),
        )
        return raw

    def validate_token(self, raw: str) -> str | None:
        """Validate token. Returns email if valid, None otherwise. Invalidates on use."""
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        record = self._store.get(token_hash)
        if not record:
            return None
        if record.used:
            return None
        if time.time() - record.created_at > TOKEN_TTL_SECONDS:
            return None
        record.used = True
        return record.email

    def is_valid(self, raw: str) -> bool:
        return self.validate_token(raw) is not None
''',

    "sandbox/src/rate_limiter.py": '''\
"""Rate limiter — max 3 reset requests per hour per email."""
import time
from collections import defaultdict


MAX_REQUESTS = 3
WINDOW_SECONDS = 3600  # 1 hour


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, email: str) -> bool:
        """Return True if the email is within the rate limit."""
        now = time.time()
        cutoff = now - WINDOW_SECONDS
        self._requests[email] = [t for t in self._requests[email] if t > cutoff]
        if len(self._requests[email]) >= MAX_REQUESTS:
            return False
        self._requests[email].append(now)
        return True
''',

    "sandbox/src/email_dispatcher.py": '''\
"""Email dispatcher — sends password reset emails (stubbed for demo)."""
import re


EMAIL_PATTERN = re.compile(r"^[\\w.+-]+@[\\w-]+\\.[\\w.]+$")


class EmailDispatcher:
    def __init__(self) -> None:
        self.sent: list[dict] = []  # audit trail for testing

    def send_reset_email(self, email: str, token: str, base_url: str = "https://example.com") -> bool:
        """Send a reset email. Returns True on success."""
        if not EMAIL_PATTERN.match(email):
            return False
        reset_link = f"{base_url}/reset?token={token}"
        self.sent.append({"to": email, "link": reset_link})
        # In production: call an email provider (SES, SendGrid, etc.)
        print(f"[email] Reset link sent to {email}: {reset_link}")
        return True
''',

    "sandbox/src/password_reset.py": '''\
"""Password reset orchestrator — ties all components together."""
from sandbox.src.token_store import TokenStore
from sandbox.src.rate_limiter import RateLimiter
from sandbox.src.email_dispatcher import EmailDispatcher


class PasswordResetService:
    def __init__(self) -> None:
        self.tokens = TokenStore()
        self.limiter = RateLimiter()
        self.emailer = EmailDispatcher()

    def request_reset(self, email: str) -> dict:
        """AC-001, AC-002, AC-006: Initiate a password reset."""
        if not self.limiter.is_allowed(email):
            return {"success": False, "error": "rate_limited"}
        token = self.tokens.create_token(email)
        sent = self.emailer.send_reset_email(email, token)
        if not sent:
            return {"success": False, "error": "invalid_email"}
        return {"success": True, "token": token}

    def complete_reset(self, token: str, new_password: str, confirm_password: str) -> dict:
        """AC-003, AC-004, AC-005: Complete the password reset."""
        if new_password != confirm_password:
            return {"success": False, "error": "passwords_do_not_match"}
        if len(new_password) < 8:
            return {"success": False, "error": "password_too_short"}
        email = self.tokens.validate_token(token)
        if email is None:
            return {"success": False, "error": "invalid_or_expired_token"}
        # In production: hash and persist the new password
        return {"success": True, "email": email, "message": "Password updated successfully"}
''',
}

DEMO_TESTS = {
    "tests/test_unit.py": '''\
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
''',

    "tests/test_integration.py": '''\
"""Integration tests — full end-to-end reset flow."""
import pytest
from sandbox.src.password_reset import PasswordResetService


def test_full_reset_flow():
    """Happy path: request → receive token → complete reset."""
    svc = PasswordResetService()

    # Step 1: request reset
    request_result = svc.request_reset("alice@example.com")
    assert request_result["success"] is True
    token = request_result["token"]

    # Step 2: complete reset with valid token
    reset_result = svc.complete_reset(token, "supersecure99", "supersecure99")
    assert reset_result["success"] is True
    assert reset_result["email"] == "alice@example.com"


def test_token_cannot_be_reused_after_reset():
    svc = PasswordResetService()
    r = svc.request_reset("bob@example.com")
    svc.complete_reset(r["token"], "pass1234", "pass1234")
    # Try to reuse the same token
    result = svc.complete_reset(r["token"], "newpass99", "newpass99")
    assert result["success"] is False


def test_rate_limit_across_full_flow():
    svc = PasswordResetService()
    for _ in range(3):
        svc.request_reset("charlie@example.com")
    result = svc.request_reset("charlie@example.com")
    assert result["error"] == "rate_limited"


def test_different_users_independent_limits():
    svc = PasswordResetService()
    for _ in range(3):
        svc.request_reset("user1@example.com")
    # user2 should not be affected
    result = svc.request_reset("user2@example.com")
    assert result["success"] is True
''',
}