"""!
@file main.py
@brief Главный модуль VPN API.
@details Этот файл содержит инициализацию FastAPI приложения и основные эндпоинты
для управления пользователями и генерации конфигураций Hysteria 2.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import math
import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем нашу базу данных, модели и CRUD
from backend.database import engine, Base, get_db
from backend.crud import get_user_by_tg_id, create_user, create_subscription, get_active_subscription

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # При запуске приложения создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Действия при выключении (пока не требуются)


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
        end_date if end_date.tzinfo is not None else end_date.replace(tzinfo=timezone.utc)
    )
    remaining_seconds: float = (
        normalized_end_date - datetime.now(timezone.utc)
    ).total_seconds()
    if remaining_seconds <= 0:
        return 0
    return math.ceil(remaining_seconds / 86400)

app = FastAPI(
    title="VPN Service API",
    description="API для управления пользователями и сервером Hysteria 2",
    version="1.0.0",
    lifespan=lifespan
)

## Модель для создания нового пользователя.
class UserCreateSchema(BaseModel):
    ## Telegram ID пользователя (уникальный идентификатор).
    telegram_id: int
    ## Имя пользователя (опционально).
    username: str | None = None

## Модель ответа с конфигурацией VPN.
class VpnConfigResponse(BaseModel):
    ## Telegram ID пользователя.
    telegram_id: int
    ## Ссылка-конфигурация для клиента Hysteria 2.
    config_url: str
    ## Количество оставшихся дней подписки.
    days_left: int

@app.post("/users/", tags=["Users"])
async def register_user(
    user: UserCreateSchema,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """!
    @brief Регистрирует нового пользователя в системе.
    
    @details Создает запись о пользователе в базе данных. Если пользователь 
    уже существует, данные будут обновлены (пока просто сообщаем, что он есть).
    
    @param user Объект UserCreateSchema с данными пользователя.
    @param db Сессия базы данных (внедряется автоматически).
    @return Словарь со статусом выполнения и сообщением.
    """
    existing_user = await get_user_by_tg_id(db, user.telegram_id)
    if existing_user:
        return {"status": "success", "message": f"Пользователь {user.telegram_id} уже зарегистрирован."}

    try:
        new_user = await create_user(db, user.telegram_id, user.username)
    except IntegrityError:
        await db.rollback()
        return {
            "status": "success",
            "message": f"Пользователь {user.telegram_id} уже зарегистрирован.",
        }

    return {"status": "success", "message": f"Пользователь {new_user.telegram_id} успешно создан."}

@app.post("/vpn/generate/{telegram_id}", response_model=VpnConfigResponse, tags=["VPN"])
async def generate_vpn_config(
    telegram_id: int,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
) -> VpnConfigResponse:
    """!
    @brief Генерирует VPN-конфигурацию для пользователя.
    
    @details Создает подписку в БД и формирует ссылку для Hysteria 2.
    
    @param telegram_id Идентификатор пользователя в Telegram.
    @param days Количество дней подписки (по умолчанию 30).
    @param db Сессия базы данных (внедряется автоматически).
    @return Объект VpnConfigResponse с готовой ссылкой (hysteria2://...).
    """
    # 1. Ищем пользователя
    user = await get_user_by_tg_id(db, telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден. Сначала зарегистрируйтесь.")
    
    # 2. Проверяем, есть ли активная подписка (чтобы не дублировать)
    active_sub = await get_active_subscription(db, user.id)

    if active_sub:
        password = active_sub.hysteria_password
        days_left = calculate_days_left(active_sub.end_date)
    else:
        # Генерируем уникальный пароль для Hysteria
        password = str(uuid.uuid4())
        new_subscription = await create_subscription(db, user.id, password, days)
        days_left = calculate_days_left(new_subscription.end_date)

    # 3. Формируем конфиг
    config_url = f"hysteria2://{password}@vpn.твой-домен.com:443/?sni=vpn.твой-домен.com"

    return VpnConfigResponse(
        telegram_id=telegram_id,
        config_url=config_url,
        days_left=days_left,
    )

@app.get("/health", tags=["System"])
async def health_check():
    """!
    @brief Проверка работоспособности API.
    @return Словарь со статусом 'ok'.
    """
    return {"status": "ok", "service": "vpn-backend"}
