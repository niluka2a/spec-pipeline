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
