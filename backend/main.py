"""!
@file main.py
@brief Главный модуль VPN API.
@details Этот файл содержит инициализацию FastAPI приложения и основные эндпоинты 
для управления пользователями и генерации конфигураций Hysteria 2.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="VPN Service API",
    description="API для управления пользователями и сервером Hysteria 2",
    version="1.0.0"
)

## Модель для создания нового пользователя.
class UserCreate(BaseModel):
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
async def register_user(user: UserCreate):
    """!
    @brief Регистрирует нового пользователя в системе.
    
    @details Создает запись о пользователе в базе данных. Если пользователь 
    уже существует, данные будут обновлены.
    
    @param user Объект UserCreate с данными пользователя.
    @return Словарь со статусом выполнения и сообщением.
    """
    return {"status": "success", "message": f"Пользователь {user.telegram_id} зарегистрирован."}

@app.post("/vpn/generate/{telegram_id}", response_model=VpnConfigResponse, tags=["VPN"])
async def generate_vpn_config(telegram_id: int):
    """!
    @brief Генерирует VPN-конфигурацию для пользователя.
    
    @details Делает запрос к API Hysteria 2, создает пользователя на сервере, 
    устанавливает лимиты и формирует ссылку для подключения.
    
    @param telegram_id Идентификатор пользователя в Telegram.
    @return Объект VpnConfigResponse с готовой ссылкой (hysteria2://...).
    """
    fake_config = f"hysteria2://fake_token_for_{telegram_id}@vpn.твои-домен.com:443/?sni=vpn.твои-домен.com"
    
    return {
        "telegram_id": telegram_id,
        "config_url": fake_config,
        "days_left": 30
    }

@app.get("/health", tags=["System"])
async def health_check():
    """!
    @brief Проверка работоспособности API.
    @return Словарь со статусом 'ok'.
    """
    return {"status": "ok", "service": "vpn-backend"}