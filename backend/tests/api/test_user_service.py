"""Tests for UserService."""

from __future__ import annotations

import uuid

import pytest

from app.services.user_service import UserService


@pytest.mark.asyncio
async def test_get_or_create_creates_new(session_factory):
    """First call with a new OID inserts a row."""
    service = UserService(session_factory=session_factory)

    user = await service.get_or_create_by_oid(oid="new-oid-001", email="user@example.com")

    assert user.entraid_oid == "new-oid-001"
    assert user.email == "user@example.com"
    assert isinstance(user.id, uuid.UUID)


@pytest.mark.asyncio
async def test_get_or_create_returns_existing(session_factory):
    """Second call with the same OID returns the existing row."""
    service = UserService(session_factory=session_factory)

    user1 = await service.get_or_create_by_oid(oid="existing-oid-001", email="user@example.com")
    user2 = await service.get_or_create_by_oid(
        oid="existing-oid-001", email="new-email@example.com"
    )

    assert user1.id == user2.id
    assert user1.email == "user@example.com"


@pytest.mark.asyncio
async def test_get_or_create_with_empty_email(session_factory):
    """Empty string email is stored as None."""
    service = UserService(session_factory=session_factory)

    user = await service.get_or_create_by_oid(oid="oid-no-email", email="")

    assert user.entraid_oid == "oid-no-email"
    assert user.email is None


@pytest.mark.asyncio
async def test_get_or_create_with_none_email(session_factory):
    """None email is stored as None."""
    service = UserService(session_factory=session_factory)

    user = await service.get_or_create_by_oid(oid="oid-none-email", email=None)

    assert user.entraid_oid == "oid-none-email"
    assert user.email is None
