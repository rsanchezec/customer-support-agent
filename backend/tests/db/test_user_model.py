"""Roundtrip tests for the User model."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import User


@pytest.mark.asyncio
async def test_user_create_and_fetch_by_id(session: AsyncSession) -> None:
    """A created user can be fetched back by their UUID primary key."""
    user = User(
        entraid_oid="abc123",
        email="alice@example.com",
        display_name="Alice",
    )
    session.add(user)
    await session.commit()

    fetched = await session.get(User, user.id)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.entraid_oid == "abc123"
    assert fetched.email == "alice@example.com"
    assert fetched.display_name == "Alice"
    assert fetched.created_at is not None


@pytest.mark.asyncio
async def test_user_fetch_by_entraid_oid(session: AsyncSession) -> None:
    """A user can be fetched by their Entra ID OID."""
    user = User(entraid_oid="oid-xyz", email="bob@example.com")
    session.add(user)
    await session.commit()

    result = await session.execute(
        pytest.importorskip("sqlalchemy").select(User).where(User.entraid_oid == "oid-xyz")
    )
    fetched = result.scalar_one_or_none()
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.entraid_oid == "oid-xyz"


@pytest.mark.asyncio
async def test_user_entraid_oid_unique(session: AsyncSession) -> None:
    """Two users cannot share the same entraid_oid."""
    user1 = User(entraid_oid="shared-oid")
    session.add(user1)
    await session.commit()

    session.add(User(entraid_oid="shared-oid"))
    with pytest.raises(Exception):
        await session.flush()
