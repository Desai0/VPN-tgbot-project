"""!
@file database.py
@brief Настройка асинхронного подключения к базе данных.
@details Модуль содержит создание асинхронного SQLAlchemy-движка, фабрики
сессий и базового декларативного класса. Также здесь определена функция
get_db() для внедрения зависимости в FastAPI-обработчики.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL: str = (
    os.getenv("DATABASE_URL") or os.getenv("DB_URL") or "sqlite+aiosqlite:///./vpn.db"
)

engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """!
    @brief Базовый декларативный класс SQLAlchemy.
    @details Класс используется как общий предок для всех ORM-моделей проекта
    и хранит общую метаинформацию SQLAlchemy.
    @param None Базовый класс не принимает параметров в собственном описании.
    @return DeclarativeBase Базовый класс для декларативных ORM-моделей.
    """


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """!
    @brief Возвращает асинхронную сессию базы данных.
    @details Функция предназначена для использования в Dependency Injection
    FastAPI. На время обработки запроса создается отдельная асинхронная сессия,
    которая автоматически закрывается после завершения работы.
    @param None Функция не принимает аргументов.
    @return AsyncGenerator[AsyncSession, None] Асинхронный генератор с одной
    сессией базы данных.
    """

    async with AsyncSessionLocal() as session:
        yield session
