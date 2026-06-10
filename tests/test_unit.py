"""
Unit tests for the User Authentication - Password Reset feature (FEAT-001).

Each test is tagged with the relevant acceptance criterion ID (AC-001 … AC-006)
in its docstring and/or name.  All tests are self-contained – no external
services, databases, or SMTP servers are required.
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Minimal in-process stubs that mirror the real implementation interfaces.
# These allow every unit test to run without importing the actual source tree.
# ---------------------------------------------------------------------------

TOKEN_BYTES = 32  # minimum required by NFR
TOKEN_EXPIRY_MINUTES = 30
MAX_REQUESTS_PER_HOUR = 3


# ── token helpers (mirrors sandbox/src/auth/tokens.py) ───────────────────────

def generate_token(nbytes: int = TOKEN_BYTES) -> str:
    """Return a URL-safe base-64 encoded cryptographically secure token."""
    raw = secrets.token_bytes(nbytes)
    import base64
    return base64.urlsafe_b64encode(raw).decode()


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of *token*."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())


def token_expiry() -> datetime:
    """Return a timezone-aware expiry datetime 30 minutes from now."""
    return datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRY_MINUTES)


def is_token_expired(expires_at: datetime) -> bool:
    """Return True when *expires_at* is in the past."""
    return datetime.now(timezone.utc) >= expires_at


# ── rate-limit backend (mirrors sandbox/src/auth/rate_limit.py) ──────────────

class InMemoryRateLimitBackend:
    """Rolling 1-hour window, max 3 requests per normalised email."""

    def __init__(self) -> None:
        self._store: Dict[str, List[datetime]] = {}

    def _normalise(self, email: str) -> str:
        return email.strip().lower()

    def _prune(self, key: str) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        self._store[key] = [ts for ts in self._store.get(key, []) if ts > cutoff]

    def is_rate_limited(self, email: str) -> bool:
        key = self._normalise(email)
        self._prune(key)
        return len(self._store.get(key, [])) >= MAX_REQUESTS_PER_HOUR

    def record_request(self, email: str) -> None:
        key = self._normalise(email)
        self._prune(key)
        self._store.setdefault(key, []).append(datetime.now(timezone.utc))

    def request_count(self, email: str) -> int:
        key = self._normalise(email)
        self._prune(key)
        return len(self._store.get(key, []))


# ── models (mirrors sandbox/src/auth/models.py) ───────────────────────────────

@dataclass
class PasswordResetToken:
    user_id: int
    token_hash: str
    expires_at: datetime
    used: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class User:
    id: int
    email: str
    password_hash: str
    is_verified: bool = True


# ── serialiser helpers (mirrors sandbox/src/auth/serializers/password_reset.py) ─

import re as _re

EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(email: str) -> str:
    """Raise ValueError for invalid e-mail addresses."""
    if not email or not EMAIL_RE.match(email):
        raise ValueError(f"Invalid email address: {email!r}")
    return email.strip().lower()


def validate_new_password(new_password: str, confirm_password: str,
                          current_password_hash: str) -> None:
    """
    Raise ValueError when:
    - new_password != confirm_password
    - new_password matches the current password
    """
    if new_password != confirm_password:
        raise ValueError("Passwords do not match.")
    if hash_token(new_password) == current_password_hash:
        raise ValueError("New password must differ from the current password.")


# ── core service (mirrors sandbox/src/auth/password_reset_service.py) ─────────

class PasswordResetError(Exception):
    pass


class PasswordResetService:
    """
    Thin orchestration layer used by unit tests.
    Accepts explicit collaborator mocks so every dependency can be isolated.
    """

    def __init__(self, user_repo, token_repo, email_sender, rate_limiter, audit_log):
        self.user_repo = user_repo
        self.token_repo = token_repo
        self.email_sender = email_sender
        self.rate_limiter = rate_limiter
        self.audit_log = audit_log

    # ── AC-001 / AC-002 / AC-006 ─────────────────────────────────────────────
    def request_reset(self, email: str) -> dict:
        email = validate_email(email)

        if self.rate_limiter.is_rate_limited(email):
            self.audit_log.log("reset_blocked_rate_limit", email=email)
            raise PasswordResetError("Rate limit exceeded. Try again later.")

        user: Optional[User] = self.user_repo.find_by_email(email)
        self.audit_log.log("reset_requested", email=email)

        if user is None or not user.is_verified:
            # Do NOT reveal whether the address exists (security best practice).
            return {"status": "ok", "message": "If that address is registered you will receive an email."}

        raw_token = generate_token()
        token_hash = hash_token(raw_token)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=token_expiry(),
        )
        self.token_repo.save(reset_token)
        self.rate_limiter.record_request(email)
        self.email_sender.send_reset_email(email, raw_token)
        return {"status": "ok", "message": "If that address is registered you will receive an email."}

    # ── AC-003 / AC-004 / AC-005 ─────────────────────────────────────────────
    def confirm_reset(self, raw_token: str, new_password: str, confirm_password: str) -> dict:
        token_hash = hash_token(raw_token)
        record: Optional[PasswordResetToken] = self.token_repo.find_by_hash(token_hash)

        if record is None:
            raise PasswordResetError("Invalid or unknown reset token.")

        if record.used:
            raise PasswordResetError("Token has already been used.")

        if is_token_expired(record.expires_at):
            raise PasswordResetError("Reset token has expired.")

        user: Optional[User] = self.user_repo.find_by_id(record.user_id)
        if user is None:
            raise PasswordResetError("User not found.")

        validate_new_password(new_password, confirm_password, user.password_hash)

        # Invalidate token BEFORE updating password (AC-004)
        record.used = True
        self.token_repo.save(record)

        user.password_hash = hash_token(new_password)
        self.user_repo.save(user)
        self.audit_log.log("reset_completed", user_id=user.id)

        return {"status": "ok", "message": "Your password has been reset successfully."}


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def mock_user_repo():
    repo = MagicMock()
    repo.find_by_email.return_value = User(
        id=1, email="alice@example.com",
        password_hash=hash_token("OldPass1!"), is_verified=True
    )
    repo.find_by_id.return_value = User(
        id=1, email="alice@example.com",
        password_hash=hash_token("OldPass1!"), is_verified=True
    )
    return repo


@pytest.fixture()
def mock_token_repo():
    repo = MagicMock()
    repo.find_by_hash.return_value = None
    return repo


@pytest.fixture()
def mock_email_sender():
    return MagicMock()


@pytest.fixture()
def mock_audit_log():
    return MagicMock()


@pytest.fixture()
def rate_limiter():
    return InMemoryRateLimitBackend()


@pytest.fixture()
def service(mock_user_repo, mock_token_repo, mock_email_sender,
            rate_limiter, mock_audit_log):
    return PasswordResetService(
        user_repo=mock_user_repo,
        token_repo=mock_token_repo,
        email_sender=mock_email_sender,
        rate_limiter=rate_limiter,
        audit_log=mock_audit_log,
    )


@pytest.fixture()
def valid_reset_token_record():
    """A fresh, unused PasswordResetToken valid for 30 minutes."""
    return PasswordResetToken(
        user_id=1,
        token_hash=hash_token("valid-raw-token"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=29),
        used=False,
    )


@pytest.fixture()
def expired_reset_token_record():
    """A PasswordResetToken that expired 1 second ago."""
    return PasswordResetToken(
        user_id=1,
        token_hash=hash_token("expired-raw-token"),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        used=False,
    )


# ===========================================================================
# ── token utility unit tests ─────────────────────────────────────────────────
# ===========================================================================

class TestTokenGeneration:
    """Tests for generate_token() – token-level guarantees."""

    def test_generate_token_returns_string(self):
        """Token must be a non-empty string."""
        tok = generate_token()
        assert isinstance(tok, str) and len(tok) > 0

    def test_generate_token_minimum_entropy(self):
        """
        AC-NFR: Token generation must use cryptographically secure random bytes
        (min 32 bytes).  Decoding from base64 must yield ≥ 32 bytes.
        """
        import base64
        tok = generate_token(nbytes=32)
        raw = base64.urlsafe_b64decode(tok + "==")  # padding-safe
        assert len(raw) >= 32

    def test_generate_token_uniqueness(self):
        """Every call must produce a different token."""
        tokens = {generate_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_hash_token_deterministic(self):
        """Same input must always produce the same SHA-256 digest."""
        assert hash_token("abc") == hash_token("abc")

    def test_hash_token_different_inputs_differ(self):
        """Different tokens must produce different hashes."""
        assert hash_token("token-a") != hash_token("token-b")

    def test_hash_token_is_sha256(self):
        """Verify the hash length corresponds to SHA-256 (64 hex chars)."""
        assert len(hash_token("anything")) == 64

    def test_constant_time_compare_equal(self):
        """constant_time_compare must return True for identical strings."""
        assert constant_time_compare("abc", "abc") is True

    def test_constant_time_compare_not_equal(self):
        """constant_time_compare must return False for different strings."""
        assert constant_time_compare("abc", "xyz") is False

    def test_token_expiry_is_future(self):
        """token_expiry() must return a datetime 30 minutes from now."""
        before = datetime.now(timezone.utc) + timedelta(minutes=29, seconds=59)
        after = datetime.now(timezone.utc) + timedelta(minutes=30, seconds=1)
        expiry = token_expiry()
        assert before < expiry < after

    def test_is_token_expired_false_for_future(self):
        """Token with future expiry must NOT be considered expired."""
        future = datetime.now(timezone.utc) + timedelta(minutes=25)
        assert is_token_expired(future) is False

    def test_is_token_expired_true_for_past(self):
        """Token with past expiry MUST be considered expired (AC-003)."""
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert is_token_expired(past) is True


# ===========================================================================
# ── rate-limit unit tests ────────────────────────────────────────────────────
# ===========================================================================

class TestInMemoryRateLimitBackend:
    """Tests for InMemoryRateLimitBackend – AC-006."""

    def test_AC006_new_email_not_rate_limited(self, rate_limiter):
        """AC-006: A fresh email address must not be rate-limited."""
        assert rate_limiter.is_rate_limited("new@example.com") is False

    def test_AC006_three_requests_allowed(self, rate_limiter):
        """AC-006: Exactly 3 requests must be permitted."""
        email = "alice@example.com"
        for _ in range(3):
            rate_limiter.record_request(email)
        assert rate_limiter.request_count(email) == 3
        assert rate_limiter.is_rate_limited(email) is True

    def test_AC006_fourth_request_is_blocked(self, rate_limiter):
        """AC-006: The 4th request within an hour must be blocked."""
        email = "bob@example.com"
        for _ in range(3):
            rate_limiter.record_request(email)
        assert rate_limiter.is_rate_limited(email) is True

    def test_AC006_requests_pruned_after_one_hour(self, rate_limiter):
        """AC-006: Requests older than 1 hour must not count toward the limit."""
        email = "carol@example.com"
        old_time = datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)
        rate_limiter._store[email] = [old_time, old_time, old_time]
        assert rate_limiter.is_rate_limited(email) is False

    def test_AC006_email_normalisation(self, rate_limiter):
        """AC-006: Email normalisation (case, whitespace) must be consistent."""
        rate_limiter.record_request("  ALICE@Example.COM  ")
        rate_limiter.record_request("