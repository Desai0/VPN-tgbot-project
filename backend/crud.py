"""!
@file crud.py
@brief CRUD-операции для работы с пользователями и VPN-подписками.
@details Модуль содержит асинхронные функции доступа к данным поверх
SQLAlchemy AsyncSession. Здесь реализованы операции поиска и создания
пользователей, а также создания и получения активных подписок.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Subscription, User


async def get_user_by_tg_id(session: AsyncSession, telegram_id: int) -> User | None:
    """!
    @brief Возвращает пользователя по Telegram ID.
    @details Функция выполняет асинхронный запрос к таблице users и ищет
    пользователя по уникальному полю telegram_id.
    @param session Активная асинхронная сессия SQLAlchemy.
    @param telegram_id Уникальный идентификатор пользователя в Telegram.
    @return User | None ORM-объект пользователя или None, если запись не найдена.
    """

    statement: Select[tuple[User]] = select(User).where(User.telegram_id == telegram_id)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
) -> User:
    """!
    @brief Создает нового пользователя.
    @details Функция формирует ORM-объект пользователя, добавляет его в
    текущую сессию, фиксирует транзакцию и обновляет объект из базы данных.
    @param session Активная асинхронная сессия SQLAlchemy.
    @param telegram_id Уникальный идентификатор пользователя в Telegram.
    @param username Имя пользователя Telegram или None, если оно отсутствует.
    @return User ORM-объект созданного пользователя после сохранения в базе.
    """

    user: User = User(telegram_id=telegram_id, username=username)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_subscription(
    session: AsyncSession,
    user_id: int,
    hysteria_password: str,
    days: int,
) -> Subscription:
    """!
    @brief Создает VPN-подписку для пользователя.
    @details Функция вычисляет дату окончания подписки на основе текущего
    времени UTC и переданного количества дней, после чего сохраняет новую
    активную подписку в базе данных.
    @param session Активная асинхронная сессия SQLAlchemy.
    @param user_id Идентификатор пользователя в таблице users.
    @param hysteria_password Пароль или UUID для доступа к Hysteria 2.
    @param days Количество дней, на которое создается подписка.
    @return Subscription ORM-объект созданной подписки после сохранения в базе.
    """

    end_date: datetime = datetime.now(timezone.utc) + timedelta(days=days)
    subscription: Subscription = Subscription(
        user_id=user_id,
        hysteria_password=hysteria_password,
        end_date=end_date,
        is_active=True,
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)
    return subscription


async def get_active_subscription(
    session: AsyncSession,
    user_id: int,
) -> Subscription | None:
    """!
    @brief Возвращает активную подписку пользователя.
    @details Функция ищет подписку по user_id, которая помечена как активная
    и срок действия которой еще не истек на момент выполнения запроса.
    @param session Активная асинхронная сессия SQLAlchemy.
    @param user_id Идентификатор пользователя в таблице users.
    @return Subscription | None ORM-объект активной подписки или None, если
    подходящая запись отсутствует.
    """

    statement: Select[tuple[Subscription]] = (
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .where(Subscription.is_active.is_(True))
        .where(Subscription.end_date >= datetime.now(timezone.utc))
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def add_subscription_days(
    session: AsyncSession,
    user_id: int,
    days: int,
) -> Subscription:
    """!
    @brief Добавляет дни к активной подписке или создаёт новую.
    @details Если у пользователя есть неистёкшая активная подписка, срок
    продлевается на указанное число дней. Иначе создаётся новая подписка.
    @param session Активная асинхронная сессия SQLAlchemy.
    @param user_id Идентификатор пользователя в таблице users.
    @param days Количество дней для продления или новой подписки.
    @return Subscription Актуальная ORM-подписка после изменений.
    """

    existing: Subscription | None = await get_active_subscription(session, user_id)
    if existing is not None:
        existing.end_date = existing.end_date + timedelta(days=days)
        await session.commit()
        await session.refresh(existing)
        return existing

    password: str = str(uuid.uuid4())
    return await create_subscription(session, user_id, password, days)


async def get_active_subscription_by_password(
    session: AsyncSession,
    hysteria_password: str,
) -> Subscription | None:
    """!
    @brief Возвращает активную подписку по паролю Hysteria 2.
    @details Функция используется HTTP auth backend для Hysteria 2. Она ищет
    активную и неистекшую подписку по auth-значению клиента и заранее
    загружает связанного пользователя.
    @param session Активная асинхронная сессия SQLAlchemy.
    @param hysteria_password Пароль или UUID, присланный клиентом Hysteria 2.
    @return Subscription | None ORM-объект подписки или None, если запись не найдена.
    """

    statement: Select[tuple[Subscription]] = (
        select(Subscription)
        .options(selectinload(Subscription.user))
        .where(Subscription.hysteria_password == hysteria_password)
        .where(Subscription.is_active.is_(True))
        .where(Subscription.end_date >= datetime.now(timezone.utc))
        .order_by(Subscription.end_date.desc())
        .limit(1)
    )
    result = await session.execute(statement)
    return result.scalars().first()
