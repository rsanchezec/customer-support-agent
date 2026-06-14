"""User service — upserts a User row keyed by Entra OID."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.user import User


class UserService:
    """Provides user upsert operations keyed by Entra OID."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create_by_oid(
        self,
        *,
        oid: str,
        email: str | None,
    ) -> User:
        """Return an existing user row for *oid* or create one.

        If *email* is None or an empty string the user.email field is set to None.
        """
        async with self._session_factory() as session:
            stmt = select(User).where(User.entraid_oid == oid)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if user is not None:
                if email:
                    user.email = email
                await session.commit()
                await session.refresh(user)
                return user

            new_user = User(
                id=uuid.uuid4(),
                entraid_oid=oid,
                email=email or None,
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            return new_user
