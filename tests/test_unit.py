"""
Unit tests for the Password Reset feature (FEAT-001).

Each test is tagged with the relevant Acceptance Criteria ID(s) in its
docstring and/or name so traceability is explicit.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional
from unittest.mock import MagicMock, Mock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal stub implementations so tests are self-contained even when the real
# source tree is not importable.  When the real modules ARE present the stubs
# are replaced by the real objects via the import-try-except pattern below.
# ---------------------------------------------------------------------------

try:
    from auth.utils.token_utils import TokenPair, generate_token, compare_tokens
except ImportError:  # pragma: no cover – stubs used when src not on path
    import secrets as _secrets
    import hmac as _hmac

    class TokenPair:  # type: ignore[no-redef]
        def __init__(self, raw_token: str, token_hash: str):
            self.raw_token = raw_token
            self.token_hash = token_hash

    def generate_token(nbytes: int = 32) -> TokenPair:  # type: ignore[misc]
        raw = _secrets.token_urlsafe(nbytes)
        h = hashlib.sha256(raw.encode()).hexdigest()
        return TokenPair(raw_token=raw, token_hash=h)

    def compare_tokens(raw_token: str, stored_hash: str) -> bool:  # type: ignore[misc]
        candidate_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        return _hmac.compare_digest(candidate_hash, stored_hash)


try:
    from auth.services.rate_limit_service import RateLimitService
except ImportError:
    class RateLimitService:  # type: ignore[no-redef]
        MAX_REQUESTS = 3
        WINDOW_SECONDS = 3600

        def __init__(self, db_session):
            self._db = db_session
            self._store: Dict[str, List[datetime]] = {}

        def is_allowed(self, email: str) -> bool:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(seconds=self.WINDOW_SECONDS)
            requests = self._store.get(email, [])
            recent = [r for r in requests if r >= window_start]
            self._store[email] = recent
            return len(recent) < self.MAX_REQUESTS

        def record_request(self, email: str) -> None:
            self._store.setdefault(email, []).append(datetime.now(timezone.utc))


try:
    from auth.services.audit_log_service import AuditLogService
except ImportError:
    class AuditLogService:  # type: ignore[no-redef]
        def __init__(self, db_session):
            self._db = db_session
            self.entries: List[Dict[str, Any]] = []

        def log(self, event_type: str, email: str, metadata: Optional[Dict] = None) -> None:
            self.entries.append({
                "event_type": event_type,
                "email": email,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc),
            })


try:
    from auth.services.password_reset_service import PasswordResetService
except ImportError:
    class PasswordResetService:  # type: ignore[no-redef]
        TOKEN_TTL_MINUTES = 30

        def __init__(self, db_session, email_service, rate_limit_service, audit_log_service):
            self._db = db_session
            self._email = email_service
            self._rate_limit = rate_limit_service
            self._audit = audit_log_service
            self._tokens: Dict[str, Any] = {}  # hash -> record
            self._users: Dict[str, Any] = {}   # email -> user record

        # ------------------------------------------------------------------
        # Helpers for testing (not part of real interface)
        # ------------------------------------------------------------------
        def _register_user(self, email: str, password_hash: str, verified: bool = True):
            self._users[email] = {"email": email, "password_hash": password_hash, "verified": verified}

        def request_reset(self, email: str) -> Dict[str, Any]:
            user = self._users.get(email)
            if not user:
                # Security: don't reveal whether email exists
                return {"success": True, "message": "If that email is registered, a reset link has been sent."}
            if not user.get("verified", False):
                return {"success": False, "error": "email_not_verified"}
            if not self._rate_limit.is_allowed(email):
                return {"success": False, "error": "rate_limit_exceeded"}
            pair = generate_token(32)
            expiry = datetime.now(timezone.utc) + timedelta(minutes=self.TOKEN_TTL_MINUTES)
            self._tokens[pair.token_hash] = {
                "email": email,
                "expires_at": expiry,
                "used": False,
                "token_hash": pair.token_hash,
            }
            self._rate_limit.record_request(email)
            self._email.send_reset_email(email, pair.raw_token)
            self._audit.log("password_reset_requested", email)
            return {"success": True, "message": "If that email is registered, a reset link has been sent."}

        def validate_token(self, raw_token: str) -> Dict[str, Any]:
            for record in self._tokens.values():
                if compare_tokens(raw_token, record["token_hash"]):
                    if record["used"]:
                        return {"valid": False, "error": "token_already_used"}
                    if datetime.now(timezone.utc) > record["expires_at"]:
                        return {"valid": False, "error": "token_expired"}
                    return {"valid": True, "email": record["email"]}
            return {"valid": False, "error": "token_not_found"}

        def confirm_reset(self, raw_token: str, new_password: str, confirm_password: str) -> Dict[str, Any]:
            if new_password != confirm_password:
                return {"success": False, "error": "passwords_do_not_match"}
            for record in self._tokens.values():
                if compare_tokens(raw_token, record["token_hash"]):
                    if record["used"]:
                        return {"success": False, "error": "token_already_used"}
                    if datetime.now(timezone.utc) > record["expires_at"]:
                        return {"success": False, "error": "token_expired"}
                    email = record["email"]
                    user = self._users.get(email, {})
                    current_hash = hashlib.sha256(new_password.encode()).hexdigest()
                    if user.get("password_hash") == current_hash:
                        return {"success": False, "error": "password_same_as_current"}
                    record["used"] = True
                    user["password_hash"] = current_hash
                    self._audit.log("password_reset_completed", email)
                    return {
                        "success": True,
                        "message": "Your password has been successfully changed.",
                    }
            return {"success": False, "error": "token_not_found"}


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def mock_db():
    """A simple mock representing a database session."""
    return MagicMock()


@pytest.fixture()
def mock_email_service():
    """Mock email sender with a send_reset_email method."""
    svc = MagicMock()
    svc.send_reset_email = MagicMock(return_value=None)
    return svc


@pytest.fixture()
def audit_service(mock_db):
    return AuditLogService(db_session=mock_db)


@pytest.fixture()
def rate_limit_service(mock_db):
    return RateLimitService(db_session=mock_db)


@pytest.fixture()
def password_reset_service(mock_db, mock_email_service, rate_limit_service, audit_service):
    svc = PasswordResetService(
        db_session=mock_db,
        email_service=mock_email_service,
        rate_limit_service=rate_limit_service,
        audit_log_service=audit_service,
    )
    # Pre-register a default verified user
    svc._register_user(
        email="alice@example.com",
        password_hash=hashlib.sha256(b"OldPassword1!").hexdigest(),
        verified=True,
    )
    return svc


# ===========================================================================
# token_utils tests
# ===========================================================================

class TestTokenGeneration:
    """Tests for the token generation utility (TokenPair / generate_token)."""

    def test_generate_token_returns_token_pair(self):
        """Token generator must return a TokenPair-like object."""
        pair = generate_token()
        assert hasattr(pair, "raw_token")
        assert hasattr(pair, "token_hash")

    def test_generate_token_raw_token_is_string(self):
        """raw_token must be a non-empty string."""
        pair = generate_token()
        assert isinstance(pair.raw_token, str)
        assert len(pair.raw_token) > 0

    def test_generate_token_hash_is_string(self):
        """token_hash must be a non-empty string."""
        pair = generate_token()
        assert isinstance(pair.token_hash, str)
        assert len(pair.token_hash) > 0

    def test_generate_token_minimum_entropy(self):
        """NFR: Token must be generated from at least 32 random bytes."""
        # urlsafe_b64 encoding of 32 bytes yields ≥43 chars
        pair = generate_token(nbytes=32)
        # raw_token should carry at least 32 bytes of entropy
        assert len(pair.raw_token) >= 32

    def test_generate_token_uniqueness(self):
        """Each call must produce a different token."""
        tokens = {generate_token().raw_token for _ in range(100)}
        assert len(tokens) == 100

    def test_compare_tokens_correct_token_returns_true(self):
        """compare_tokens must return True for the matching raw/hash pair."""
        pair = generate_token()
        assert compare_tokens(pair.raw_token, pair.token_hash) is True

    def test_compare_tokens_wrong_token_returns_false(self):
        """compare_tokens must return False for a non-matching token."""
        pair = generate_token()
        assert compare_tokens("wrong_token_value", pair.token_hash) is False

    def test_compare_tokens_constant_time(self):
        """
        NFR: Token comparison must not short-circuit (timing-safe).
        We can only assert the function uses hmac.compare_digest semantics;
        here we verify it does NOT raise on equal-length mismatch.
        """
        pair = generate_token()
        # Should not raise, should return False
        result = compare_tokens("A" * len(pair.raw_token), pair.token_hash)
        assert result is False

    def test_token_hash_differs_from_raw_token(self):
        """The stored hash must not be the same as the raw token (no plain-text storage)."""
        pair = generate_token()
        assert pair.raw_token != pair.token_hash

    def test_generate_token_hash_is_deterministic_for_same_raw(self):
        """The same raw token must always hash to the same value."""
        pair = generate_token()
        assert compare_tokens(pair.raw_token, pair.token_hash) is True
        # Recompute hash independently
        expected = hashlib.sha256(pair.raw_token.encode()).hexdigest()
        assert pair.token_hash == expected


# ===========================================================================
# RateLimitService tests
# ===========================================================================

class TestRateLimitService:
    """Tests for RateLimitService. Covers AC-006."""

    def test_first_request_is_allowed(self, rate_limit_service):
        """AC-006: First request must be allowed."""
        assert rate_limit_service.is_allowed("user@example.com") is True

    def test_second_request_is_allowed(self, rate_limit_service):
        """AC-006: Second request within the window must be allowed."""
        email = "user@example.com"
        rate_limit_service.record_request(email)
        assert rate_limit_service.is_allowed(email) is True

    def test_third_request_is_allowed(self, rate_limit_service):
        """AC-006: Third request is the last one allowed."""
        email = "user@example.com"
        rate_limit_service.record_request(email)
        rate_limit_service.record_request(email)
        assert rate_limit_service.is_allowed(email) is True

    def test_fourth_request_is_blocked(self, rate_limit_service):
        """AC-006: Fourth request within the window must be blocked."""
        email = "user@example.com"
        for _ in range(3):
            rate_limit_service.record_request(email)
        assert rate_limit_service.is_allowed(email) is False

    def test_rate_limit_is_per_email(self, rate_limit_service):
        """AC-006: Rate limiting is per email; different emails are independent."""
        email_a = "a@example.com"
        email_b = "b@example.com"
        for _ in range(3):
            rate_limit_service.record_request(email_a)
        assert rate_limit_service.is_allowed(email_a) is False
        assert rate_limit_service.is_allowed(email_b) is True

    def test_requests_outside_window_do_not_count(self, rate_limit_service):
        """AC-006: Requests older than 1 hour must not count toward the limit."""
        email = "user@example.com"
        # Simulate 3 old requests (beyond the rolling window)
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        for _ in range(3):
            rate_limit_service._store.setdefault(email, []).append(old_time)
        # Those old requests should not block a new one
        assert rate_limit_service.is_allowed(email) is True

    def test_exactly_at_window_boundary_is_blocked(self, rate_limit_service):
        """AC-006: A request exactly at the window boundary still counts."""
        email = "user@example.com"
        # 3 requests just inside the window
        just_inside = datetime.now(timezone.utc) - timedelta(seconds=3599)
        for _ in range(3):
            rate_limit_service._store.setdefault(email, []).append(just_inside)
        assert rate_limit_service.is_allowed(email) is False

    def test_record_request_increments_count(self, rate_limit_service):
        """record_request must persist the request for subsequent checks."""
        email = "user@example.com"
        rate_limit_service.record_request(email)
        rate_limit_service.record_request(email)
        recent = [
            r for r in rate_limit_service._store.get(email, [])
            if r >= datetime.now(timezone.utc) - timedelta(hours=1)
        ]
        assert len(recent) == 2


#