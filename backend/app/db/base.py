from __future__ import annotations

import enum
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.config import Settings

EnumType = enum.Enum

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(AsyncAttrs, DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        UUID: PGUUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


def pg_enum(enum_class: type[EnumType], name: str) -> Enum:
    return Enum(
        enum_class,
        name=name,
        native_enum=True,
        values_callable=lambda member: [item.value for item in member],
    )


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


class Engine:
    def __init__(self, settings: Settings) -> None:
        if is_sqlite(settings.database_url):
            kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
            if ":memory:" in settings.database_url:
                kwargs["poolclass"] = StaticPool
            self._engine: AsyncEngine = create_async_engine(
                settings.database_url,
                echo=settings.db_echo,
                **kwargs,
            )
        else:
            self._engine = create_async_engine(
                settings.database_url,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_pre_ping=True,
                pool_recycle=1800,
                echo=settings.db_echo,
            )
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def raw(self) -> AsyncEngine:
        return self._engine

    async def open_session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()


_engine: Engine | None = None


def init_engine(settings: Settings) -> Engine:
    global _engine
    _engine = Engine(settings)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    engine = get_engine()
    async for session in engine.open_session():
        yield session
