from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class BackendClientError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class VpnConfig:
    telegram_id: int
    config_url: str
    days_left: int


@dataclass(slots=True)
class UserStats:
    telegram_id: int
    client_id: str
    subscription_active: bool
    days_left: int
    tx_bytes: int
    rx_bytes: int
    online_connections: int


class BackendClient:
    def __init__(self) -> None:
        self._base_url = os.getenv("BACKEND_URL", "http://backend:8000").rstrip("/")
        self._timeout = aiohttp.ClientTimeout(
            total=float(os.getenv("BACKEND_TIMEOUT_SECONDS", "10"))
        )
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            logger.info("Backend client session started for %s", self._base_url)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            logger.info("Backend client session closed")

    async def register_user(
        self,
        telegram_id: int,
        username: str | None,
    ) -> dict[str, Any]:
        payload = {"telegram_id": telegram_id, "username": username}
        return await self._request_json("POST", "/users/", json=payload)

    async def generate_vpn_config(
        self,
        telegram_id: int,
        days: int = 30,
    ) -> VpnConfig:
        payload = await self._request_json(
            "POST",
            f"/vpn/generate/{telegram_id}",
            params={"days": str(days)},
        )
        return VpnConfig(
            telegram_id=int(payload["telegram_id"]),
            config_url=str(payload["config_url"]),
            days_left=int(payload["days_left"]),
        )

    async def subscribe_vpn(self, telegram_id: int, days: int) -> VpnConfig:
        payload = await self._request_json(
            "POST",
            f"/vpn/subscribe/{telegram_id}",
            params={"days": str(days)},
        )
        return VpnConfig(
            telegram_id=int(payload["telegram_id"]),
            config_url=str(payload["config_url"]),
            days_left=int(payload["days_left"]),
        )

    async def get_user_stats(self, telegram_id: int) -> UserStats:
        payload = await self._request_json("GET", f"/users/{telegram_id}/stats")
        return UserStats(
            telegram_id=int(payload["telegram_id"]),
            client_id=str(payload["client_id"]),
            subscription_active=bool(payload["subscription_active"]),
            days_left=int(payload["days_left"]),
            tx_bytes=int(payload["tx_bytes"]),
            rx_bytes=int(payload["rx_bytes"]),
            online_connections=int(payload["online_connections"]),
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            raise BackendClientError("HTTP session is not initialized.")

        url = f"{self._base_url}{path}"
        logger.info("Backend request: %s %s params=%s", method, url, params)
        try:
            async with self._session.request(
                method=method,
                url=url,
                json=json,
                params=params,
            ) as response:
                data = await self._read_response(response)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.exception("Backend request failed: %s %s", method, url)
            raise BackendClientError(
                "Backend is unavailable. Check BACKEND_URL and service state."
            ) from exc

        if response.status >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            message = str(detail or f"Backend returned HTTP {response.status}.")
            logger.warning(
                "Backend error response: %s %s status=%s detail=%s",
                method,
                url,
                response.status,
                message,
            )
            raise BackendClientError(message, status_code=response.status)

        if not isinstance(data, dict):
            logger.warning(
                "Backend returned unexpected response format for %s %s",
                method,
                url,
            )
            raise BackendClientError("Backend returned an unexpected response format.")
        logger.info("Backend response: %s %s status=%s", method, url, response.status)
        return data

    async def _read_response(
        self,
        response: aiohttp.ClientResponse,
    ) -> dict[str, Any] | list[Any] | str | None:
        if response.content_type == "application/json":
            return await response.json()

        text = await response.text()
        return text or None
