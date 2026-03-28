"""!
@file hysteria_client.py
@brief Клиент и настройки интеграции с Hysteria 2.
@details Модуль содержит загрузку настроек Hysteria 2 из переменных окружения,
асинхронный клиент для Traffic Stats API и вспомогательные функции для сборки
клиентского URI и преобразования идентификаторов пользователей.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx


def parse_bool_env(value: str | None, default: bool = False) -> bool:
    """!
    @brief Преобразует значение переменной окружения в bool.
    @details Функция поддерживает распространенные строковые представления
    булевых значений и возвращает значение по умолчанию, если переменная
    окружения не задана.
    @param value Строковое значение переменной окружения или None.
    @param default Значение, которое используется при отсутствии переменной.
    @return bool Результат преобразования в булев тип.
    """

    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class HysteriaTrafficStats:
    """!
    @brief Статистика трафика клиента Hysteria 2.
    @details Объект хранит значения переданного и полученного трафика в байтах
    из Traffic Stats API Hysteria 2.
    @param tx_bytes Количество переданных байт с точки зрения клиента.
    @param rx_bytes Количество полученных байт с точки зрения клиента.
    @return HysteriaTrafficStats Типизированный контейнер статистики трафика.
    """

    tx_bytes: int
    rx_bytes: int


@dataclass(slots=True)
class HysteriaUserStatus:
    """!
    @brief Сводное состояние пользователя в Hysteria 2.
    @details Объект объединяет статистику трафика и количество онлайн-подключений
    конкретного клиента, идентифицируемого через client_id.
    @param client_id Уникальный идентификатор клиента в Hysteria 2.
    @param tx_bytes Количество переданных байт.
    @param rx_bytes Количество полученных байт.
    @param online_connections Число активных клиентских подключений.
    @return HysteriaUserStatus Типизированный контейнер состояния пользователя.
    """

    client_id: str
    tx_bytes: int
    rx_bytes: int
    online_connections: int


@dataclass(slots=True)
class HysteriaSettings:
    """!
    @brief Настройки интеграции с Hysteria 2.
    @details Объект содержит адрес Traffic Stats API, параметры авторизации,
    а также публичные настройки сервера, необходимые для сборки клиентского URI.
    @param api_url Базовый URL Traffic Stats API.
    @param api_token Секрет API для заголовка Authorization или None.
    @param server_host Публичный адрес Hysteria-сервера для клиентов.
    @param server_port Публичный порт Hysteria-сервера.
    @param server_sni Значение SNI для TLS или None.
    @param server_insecure Флаг разрешения небезопасного TLS.
    @param obfs Тип обфускации или None.
    @param obfs_password Пароль обфускации или None.
    @param request_timeout_seconds Таймаут HTTP-запросов к Traffic Stats API.
    @return HysteriaSettings Типизированный набор настроек Hysteria 2.
    """

    api_url: str
    api_token: str | None
    server_host: str
    server_port: str
    server_sni: str | None
    server_insecure: bool
    obfs: str | None
    obfs_password: str | None
    request_timeout_seconds: float


class HysteriaApiError(RuntimeError):
    """!
    @brief Ошибка взаимодействия с Traffic Stats API Hysteria 2.
    @details Исключение поднимается в случаях сетевой ошибки, таймаута или
    некорректного ответа от Traffic Stats API.
    @param message Текст ошибки.
    @return HysteriaApiError Исключение уровня интеграционного клиента.
    """


def load_hysteria_settings() -> HysteriaSettings:
    """!
    @brief Загружает настройки Hysteria 2 из переменных окружения.
    @details Функция считывает конфигурацию Traffic Stats API и публичные
    параметры сервера для сборки клиентских URI, используя безопасные значения
    по умолчанию для локальной разработки.
    @param None Функция не принимает аргументов.
    @return HysteriaSettings Экземпляр настроек интеграции с Hysteria 2.
    """

    api_url: str = os.getenv("HYSTERIA_API_URL", "http://127.0.0.1:25413")
    api_token: str | None = os.getenv("HYSTERIA_API_TOKEN")
    server_host: str = os.getenv("HYSTERIA_SERVER_HOST", "vpn.example.com")
    server_port: str = os.getenv("HYSTERIA_SERVER_PORT", "443")
    server_sni: str | None = os.getenv("HYSTERIA_SERVER_SNI") or server_host
    server_insecure: bool = parse_bool_env(os.getenv("HYSTERIA_SERVER_INSECURE"))
    obfs: str | None = os.getenv("HYSTERIA_OBFS")
    obfs_password: str | None = os.getenv("HYSTERIA_OBFS_PASSWORD")
    request_timeout_seconds: float = float(
        os.getenv("HYSTERIA_REQUEST_TIMEOUT_SECONDS", "10")
    )

    return HysteriaSettings(
        api_url=api_url.rstrip("/"),
        api_token=api_token,
        server_host=server_host,
        server_port=server_port,
        server_sni=server_sni,
        server_insecure=server_insecure,
        obfs=obfs,
        obfs_password=obfs_password,
        request_timeout_seconds=request_timeout_seconds,
    )


def build_hysteria_client_id(telegram_id: int) -> str:
    """!
    @brief Формирует client_id для Hysteria 2 по Telegram ID.
    @details Стабильный client_id используется в HTTP auth backend и затем
    фигурирует в логах и Traffic Stats API Hysteria 2.
    @param telegram_id Уникальный идентификатор пользователя в Telegram.
    @return str Строковый идентификатор клиента для Hysteria 2.
    """

    return f"tg_{telegram_id}"


class HysteriaApiClient:
    """!
    @brief Асинхронный клиент Traffic Stats API Hysteria 2.
    @details Класс инкапсулирует сетевое взаимодействие с эндпоинтами
    `/traffic`, `/online` и `/kick`, а также умеет собирать клиентский URI
    из настроек сервера и пользовательского auth-значения.
    @param settings Настройки подключения и публикации клиента.
    @return HysteriaApiClient Экземпляр клиента Traffic Stats API.
    """

    def __init__(self, settings: HysteriaSettings) -> None:
        """!
        @brief Инициализирует клиент Traffic Stats API.
        @details Конструктор сохраняет загруженные настройки интеграции
        для последующего выполнения HTTP-запросов и сборки URI.
        @param settings Настройки Hysteria 2.
        @return None Конструктор не возвращает значение.
        """

        self._settings: HysteriaSettings = settings

    def build_client_uri(self, auth_value: str) -> str:
        """!
        @brief Собирает URI подключения Hysteria 2 для клиента.
        @details Функция формирует URI по официальной схеме Hysteria 2,
        включая auth-компонент и необходимые query-параметры TLS/obfs.
        @param auth_value Значение auth, которое клиент использует для входа.
        @return str Готовый URI формата `hysteria2://...`.
        """

        encoded_auth: str = quote(auth_value, safe="")
        host_port: str = f"{self._settings.server_host}:{self._settings.server_port}"
        query_params: dict[str, str] = {}

        if self._settings.server_sni:
            query_params["sni"] = self._settings.server_sni
        if self._settings.server_insecure:
            query_params["insecure"] = "1"
        if self._settings.obfs:
            query_params["obfs"] = self._settings.obfs
        if self._settings.obfs_password:
            query_params["obfs-password"] = self._settings.obfs_password

        query_string: str = urlencode(query_params)
        if query_string:
            return f"hysteria2://{encoded_auth}@{host_port}/?{query_string}"
        return f"hysteria2://{encoded_auth}@{host_port}/"

    async def get_traffic(self, clear: bool = False) -> dict[str, HysteriaTrafficStats]:
        """!
        @brief Получает карту трафика клиентов из Hysteria 2.
        @details Метод вызывает эндпоинт `/traffic` Traffic Stats API и
        преобразует ответ в типизированную структуру статистики.
        @param clear Если True, Hysteria очистит счетчики после чтения.
        @return dict[str, HysteriaTrafficStats] Карта client_id к статистике.
        """

        payload: dict[str, Any] = await self._request_json(
            method="GET",
            path="/traffic",
            params={"clear": "1"} if clear else None,
        )
        traffic_map: dict[str, HysteriaTrafficStats] = {}
        for client_id, stats in payload.items():
            stats_map: dict[str, Any] = stats if isinstance(stats, dict) else {}
            traffic_map[client_id] = HysteriaTrafficStats(
                tx_bytes=int(stats_map.get("tx", 0)),
                rx_bytes=int(stats_map.get("rx", 0)),
            )
        return traffic_map

    async def get_online(self) -> dict[str, int]:
        """!
        @brief Получает карту онлайн-клиентов из Hysteria 2.
        @details Метод вызывает эндпоинт `/online` Traffic Stats API и
        приводит значения количества подключений к типу int.
        @param None Метод не принимает дополнительных аргументов.
        @return dict[str, int] Карта client_id к числу онлайн-подключений.
        """

        payload: dict[str, Any] = await self._request_json(method="GET", path="/online")
        return {client_id: int(count) for client_id, count in payload.items()}

    async def kick_clients(self, client_ids: list[str]) -> None:
        """!
        @brief Разрывает активные подключения указанных клиентов.
        @details Метод вызывает эндпоинт `/kick` Traffic Stats API. Hysteria
        попытается отключить указанные client_id, но при активном auth backend
        клиент сможет переподключиться, если подписка все еще действительна.
        @param client_ids Список идентификаторов клиентов для отключения.
        @return None Метод не возвращает значение.
        """

        await self._request_json(method="POST", path="/kick", json_body=client_ids)

    async def get_user_status(
        self,
        client_id: str,
        clear_traffic: bool = False,
    ) -> HysteriaUserStatus:
        """!
        @brief Получает сводный статус одного клиента Hysteria 2.
        @details Метод объединяет данные из эндпоинтов `/traffic` и `/online`
        для одного client_id, чтобы вернуть трафик и текущие подключения.
        @param client_id Уникальный идентификатор клиента Hysteria 2.
        @param clear_traffic Если True, Hysteria очистит счетчики после чтения.
        @return HysteriaUserStatus Сводное состояние клиента.
        """

        traffic_map: dict[str, HysteriaTrafficStats] = await self.get_traffic(
            clear=clear_traffic
        )
        online_map: dict[str, int] = await self.get_online()
        traffic: HysteriaTrafficStats = traffic_map.get(
            client_id,
            HysteriaTrafficStats(tx_bytes=0, rx_bytes=0),
        )
        online_connections: int = online_map.get(client_id, 0)
        return HysteriaUserStatus(
            client_id=client_id,
            tx_bytes=traffic.tx_bytes,
            rx_bytes=traffic.rx_bytes,
            online_connections=online_connections,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: Any = None,
    ) -> dict[str, Any]:
        """!
        @brief Выполняет HTTP-запрос к Traffic Stats API и возвращает JSON.
        @details Метод централизует формирование заголовков, таймаутов и
        обработку сетевых ошибок при обращении к Hysteria 2 API.
        @param method HTTP-метод запроса.
        @param path Путь эндпоинта относительно базового URL API.
        @param params Query-параметры или None.
        @param json_body JSON-тело запроса или None.
        @return dict[str, Any] JSON-ответ, приведенный к словарю.
        """

        headers: dict[str, str] = {}
        if self._settings.api_token:
            headers["Authorization"] = self._settings.api_token

        url: str = f"{self._settings.api_url}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.request_timeout_seconds,
            ) as client:
                response: httpx.Response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
                response.raise_for_status()
                if not response.content:
                    return {}
                data: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HysteriaApiError(f"Не удалось выполнить запрос к Hysteria API: {exc}") from exc

        if not isinstance(data, dict):
            raise HysteriaApiError("Hysteria API вернул ответ в неожиданном формате.")
        return data
