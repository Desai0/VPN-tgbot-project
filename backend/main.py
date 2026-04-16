"""!
@file main.py
@brief Главный модуль VPN API.
@details Этот файл содержит инициализацию FastAPI приложения и основные эндпоинты
для управления пользователями, HTTP auth backend Hysteria 2 и чтения статистики
из Traffic Stats API.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.crud import (
    create_subscription,
    create_user,
    get_active_subscription,
    get_active_subscription_by_password,
    get_user_by_tg_id,
)
from backend.database import Base, engine, get_db
from backend.hysteria_client import (
    HysteriaApiClient,
    HysteriaApiError,
    HysteriaUserStatus,
    build_hysteria_client_id,
    load_hysteria_settings,
)

hysteria_client: HysteriaApiClient = HysteriaApiClient(load_hysteria_settings())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """!
    @brief Выполняет действия жизненного цикла FastAPI-приложения.
    @details При старте приложения функция создает таблицы базы данных,
    необходимые для работы backend, а затем передает управление приложению.
    @param app Экземпляр FastAPI-приложения.
    @return AsyncIterator[None] Асинхронный контекст жизненного цикла приложения.
    """

    _ = app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


def calculate_days_left(end_date: datetime) -> int:
    """!
    @brief Вычисляет количество оставшихся дней подписки.
    @details Функция нормализует дату окончания подписки к UTC, вычисляет
    разницу с текущим временем и возвращает количество оставшихся календарных
    дней с округлением вверх. Если срок уже истек, возвращается 0.
    @param end_date Дата и время окончания подписки.
    @return int Количество оставшихся дней подписки.
    """

    normalized_end_date: datetime = (
        end_date
        if end_date.tzinfo is not None
        else end_date.replace(tzinfo=timezone.utc)
    )
    remaining_seconds: float = (
        normalized_end_date - datetime.now(timezone.utc)
    ).total_seconds()
    if remaining_seconds <= 0:
        return 0
    return math.ceil(remaining_seconds / 86400)


class UserCreateSchema(BaseModel):
    """!
    @brief Модель запроса на создание пользователя.
    @details Модель используется для регистрации пользователя Telegram в локальной
    базе данных backend перед созданием подписки или выдачей VPN-конфигурации.
    @param telegram_id Уникальный идентификатор пользователя в Telegram.
    @param username Имя пользователя Telegram или None.
    @return UserCreateSchema Pydantic-модель запроса на регистрацию.
    """

    telegram_id: int
    username: str | None = None


class VpnConfigResponse(BaseModel):
    """!
    @brief Модель ответа с конфигурацией Hysteria 2.
    @details Модель возвращает клиентский URI Hysteria 2 и количество
    оставшихся дней по активной подписке пользователя.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param config_url Ссылка-конфигурация для клиента Hysteria 2.
    @param days_left Количество оставшихся дней подписки.
    @return VpnConfigResponse Pydantic-модель ответа с VPN-конфигурацией.
    """

    telegram_id: int
    config_url: str
    days_left: int


class HysteriaAuthRequest(BaseModel):
    """!
    @brief Запрос HTTP auth backend от Hysteria 2.
    @details Модель описывает тело POST-запроса, который Hysteria 2 отправляет
    в backend при попытке подключения клиента через режим HTTP authentication.
    @param addr IP-адрес и порт клиента.
    @param auth Значение auth, отправленное клиентом Hysteria 2.
    @param tx Скорость передачи данных с точки зрения сервера в байтах/сек.
    @return HysteriaAuthRequest Pydantic-модель запроса аутентификации.
    """

    addr: str
    auth: str
    tx: int


class HysteriaAuthResponse(BaseModel):
    """!
    @brief Ответ backend для HTTP auth backend Hysteria 2.
    @details Модель соответствует контракту Hysteria 2: backend возвращает
    признак допуска клиента и его стабильный client_id для логов и статистики.
    @param ok Флаг разрешения подключения.
    @param id Уникальный client_id пользователя или None при отказе.
    @return HysteriaAuthResponse Pydantic-модель ответа аутентификации.
    """

    ok: bool
    id: str | None = None


class UserTrafficStatsResponse(BaseModel):
    """!
    @brief Сводная статистика пользователя в Hysteria 2.
    @details Модель объединяет данные подписки и Traffic Stats API, чтобы бот
    или админская панель могли получить трафик, online-статус и остаток дней.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param client_id Уникальный идентификатор клиента Hysteria 2.
    @param subscription_active Флаг активности подписки.
    @param days_left Количество оставшихся дней подписки.
    @param tx_bytes Количество переданных байт.
    @param rx_bytes Количество полученных байт.
    @param online_connections Число активных клиентских подключений.
    @return UserTrafficStatsResponse Pydantic-модель статистики пользователя.
    """

    telegram_id: int
    client_id: str
    subscription_active: bool
    days_left: int
    tx_bytes: int
    rx_bytes: int
    online_connections: int


class KickUserResponse(BaseModel):
    """!
    @brief Результат отключения пользователя в Hysteria 2.
    @details Модель возвращается после вызова Traffic Stats API `/kick` и
    отражает, для какого client_id была отправлена команда отключения.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param client_id Уникальный идентификатор клиента Hysteria 2.
    @param kicked Флаг успешной отправки команды kick.
    @return KickUserResponse Pydantic-модель результата отключения.
    """

    telegram_id: int
    client_id: str
    kicked: bool


def build_stats_response(
    telegram_id: int,
    client_status: HysteriaUserStatus,
    subscription_active: bool,
    days_left: int,
) -> UserTrafficStatsResponse:
    """!
    @brief Формирует ответ со статистикой пользователя.
    @details Функция собирает данные из Hysteria 2 и локальной подписки в одну
    типизированную response-модель для FastAPI-эндпоинта статистики.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param client_status Сводное состояние клиента Hysteria 2.
    @param subscription_active Флаг активности подписки.
    @param days_left Количество оставшихся дней подписки.
    @return UserTrafficStatsResponse Готовая response-модель статистики.
    """

    return UserTrafficStatsResponse(
        telegram_id=telegram_id,
        client_id=client_status.client_id,
        subscription_active=subscription_active,
        days_left=days_left,
        tx_bytes=client_status.tx_bytes,
        rx_bytes=client_status.rx_bytes,
        online_connections=client_status.online_connections,
    )


app = FastAPI(
    title="VPN Service API",
    description="API для управления пользователями и сервером Hysteria 2",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/users/", tags=["Users"])
async def register_user(
    user: UserCreateSchema,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """!
    @brief Регистрирует нового пользователя в системе.
    @details Создает запись о пользователе в базе данных. Если пользователь
    уже существует, функция возвращает успешный ответ без повторного создания.
    @param user Объект UserCreateSchema с данными пользователя.
    @param db Сессия базы данных, внедренная через FastAPI.
    @return dict[str, str] Словарь со статусом выполнения и сообщением.
    """

    existing_user = await get_user_by_tg_id(db, user.telegram_id)
    if existing_user is not None:
        return {
            "status": "success",
            "message": f"Пользователь {user.telegram_id} уже зарегистрирован.",
        }

    try:
        new_user = await create_user(db, user.telegram_id, user.username)
    except IntegrityError:
        await db.rollback()
        return {
            "status": "success",
            "message": f"Пользователь {user.telegram_id} уже зарегистрирован.",
        }

    return {
        "status": "success",
        "message": f"Пользователь {new_user.telegram_id} успешно создан.",
    }


@app.post("/vpn/generate/{telegram_id}", response_model=VpnConfigResponse, tags=["VPN"])
async def generate_vpn_config(
    telegram_id: int,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
) -> VpnConfigResponse:
    """!
    @brief Генерирует VPN-конфигурацию для пользователя.
    @details Создает или переиспользует активную подписку в БД и формирует
    клиентский URI Hysteria 2. Фактическая проверка auth-значения будет
    происходить через HTTP auth backend самого Hysteria 2.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param days Количество дней подписки при первом создании.
    @param db Сессия базы данных, внедренная через FastAPI.
    @return VpnConfigResponse Объект с готовой ссылкой `hysteria2://...`.
    """

    user = await get_user_by_tg_id(db, telegram_id)
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден. Сначала зарегистрируйтесь.",
        )

    active_subscription = await get_active_subscription(db, user.id)
    if active_subscription is not None:
        password: str = active_subscription.hysteria_password
        days_left: int = calculate_days_left(active_subscription.end_date)
    else:
        password = str(uuid.uuid4())
        new_subscription = await create_subscription(db, user.id, password, days)
        days_left = calculate_days_left(new_subscription.end_date)

    config_url: str = hysteria_client.build_client_uri(password)
    return VpnConfigResponse(
        telegram_id=telegram_id,
        config_url=config_url,
        days_left=days_left,
    )


@app.post("/hysteria/auth", response_model=HysteriaAuthResponse, tags=["Hysteria"])
async def authenticate_hysteria_client(
    payload: HysteriaAuthRequest,
    db: AsyncSession = Depends(get_db),
) -> HysteriaAuthResponse:
    """!
    @brief Выполняет HTTP-аутентификацию клиента для Hysteria 2.
    @details Эндпоинт предназначен для конфигурации `auth.type: http` на стороне
    Hysteria 2. Он проверяет, соответствует ли переданное auth-значение активной
    подписке, и возвращает стабильный client_id, используемый в статистике.
    @param payload Тело запроса от Hysteria 2 с addr, auth и tx.
    @param db Сессия базы данных, внедренная через FastAPI.
    @return HysteriaAuthResponse Разрешение подключения и client_id.
    """

    subscription = await get_active_subscription_by_password(db, payload.auth)
    if subscription is None or subscription.user is None:
        return HysteriaAuthResponse(ok=False)

    client_id: str = build_hysteria_client_id(subscription.user.telegram_id)
    return HysteriaAuthResponse(ok=True, id=client_id)


@app.get(
    "/users/{telegram_id}/stats",
    response_model=UserTrafficStatsResponse,
    tags=["Users", "Hysteria"],
)
async def get_user_stats(
    telegram_id: int,
    clear_traffic: bool = False,
    db: AsyncSession = Depends(get_db),
) -> UserTrafficStatsResponse:
    """!
    @brief Возвращает статистику пользователя из Hysteria 2 и БД.
    @details Эндпоинт использует Traffic Stats API Hysteria 2 для чтения
    накопленного трафика и числа активных подключений, а также локальную БД
    для определения активности подписки и количества оставшихся дней.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param clear_traffic Флаг очистки счетчиков трафика после чтения.
    @param db Сессия базы данных, внедренная через FastAPI.
    @return UserTrafficStatsResponse Сводная статистика пользователя.
    """

    user = await get_user_by_tg_id(db, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")

    active_subscription = await get_active_subscription(db, user.id)
    if active_subscription is None:
        inactive_status = HysteriaUserStatus(
            client_id=build_hysteria_client_id(telegram_id),
            tx_bytes=0,
            rx_bytes=0,
            online_connections=0,
        )
        return build_stats_response(
            telegram_id=telegram_id,
            client_status=inactive_status,
            subscription_active=False,
            days_left=0,
        )

    client_id: str = build_hysteria_client_id(telegram_id)
    try:
        client_status = await hysteria_client.get_user_status(
            client_id=client_id,
            clear_traffic=clear_traffic,
        )
    except HysteriaApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return build_stats_response(
        telegram_id=telegram_id,
        client_status=client_status,
        subscription_active=True,
        days_left=calculate_days_left(active_subscription.end_date),
    )


@app.post(
    "/users/{telegram_id}/kick",
    response_model=KickUserResponse,
    tags=["Users", "Hysteria"],
)
async def kick_user(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
) -> KickUserResponse:
    """!
    @brief Принудительно отключает активные подключения пользователя.
    @details Эндпоинт обращается к Traffic Stats API `/kick` для client_id,
    связанного с указанным Telegram-пользователем. Если подписка не активна,
    отключение не выполняется.
    @param telegram_id Идентификатор пользователя в Telegram.
    @param db Сессия базы данных, внедренная через FastAPI.
    @return KickUserResponse Результат отправки команды отключения.
    """

    user = await get_user_by_tg_id(db, telegram_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден.")

    active_subscription = await get_active_subscription(db, user.id)
    if active_subscription is None:
        raise HTTPException(status_code=404, detail="Активная подписка не найдена.")

    client_id: str = build_hysteria_client_id(telegram_id)
    try:
        await hysteria_client.kick_clients([client_id])
    except HysteriaApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return KickUserResponse(
        telegram_id=telegram_id,
        client_id=client_id,
        kicked=True,
    )


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    """!
    @brief Проверка работоспособности API.
    @details Эндпоинт возвращает минимальный статус backend-сервиса без
    обращения к внешним зависимостям.
    @param None Функция не принимает аргументов.
    @return dict[str, str] Словарь со статусом сервиса.
    """

    return {"status": "ok", "service": "vpn-backend"}
