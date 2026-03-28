"""!
@file models.py
@brief ORM-модели приложения VPN-сервиса.
@details Модуль описывает таблицы пользователей и VPN-подписок на базе
SQLAlchemy 2.0 с использованием декларативного подхода, типизированных полей
Mapped и связей relationship.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class User(Base):
    """!
    @brief ORM-модель пользователя Telegram.
    @details Класс описывает таблицу users, в которой хранятся уникальный
    Telegram ID пользователя, его username, дата регистрации и связанные
    VPN-подписки.
    @param None Создание экземпляра происходит через ORM SQLAlchemy.
    @return User ORM-объект пользователя системы.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    subscriptions: Mapped[list[Subscription]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Subscription(Base):
    """!
    @brief ORM-модель VPN-подписки пользователя.
    @details Класс описывает таблицу subscriptions, в которой хранится связь
    с пользователем, пароль для Hysteria 2, срок действия подписки и флаг
    активности.
    @param None Создание экземпляра происходит через ORM SQLAlchemy.
    @return Subscription ORM-объект подписки пользователя.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    hysteria_password: Mapped[str] = mapped_column(String, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="subscriptions")
