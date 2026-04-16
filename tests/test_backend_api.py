from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.main import HysteriaUserStatus, app, get_db, hysteria_client
from backend.models import Subscription, User


class BackendApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._temp_dir.name) / "test.db"
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path.as_posix()}",
            echo=False,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async def override_get_db():
            async with self._session_factory() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        self._original_get_user_status = hysteria_client.get_user_status
        self._original_kick_clients = hysteria_client.kick_clients
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self._client.aclose()
        app.dependency_overrides.clear()
        hysteria_client.get_user_status = self._original_get_user_status
        hysteria_client.kick_clients = self._original_kick_clients
        await self._engine.dispose()
        self._temp_dir.cleanup()

    async def _register_user(
        self,
        telegram_id: int = 1001,
        username: str = "tester",
    ) -> httpx.Response:
        return await self._client.post(
            "/users/",
            json={"telegram_id": telegram_id, "username": username},
        )

    async def _generate_vpn_config(
        self,
        telegram_id: int = 1001,
        days: int = 30,
    ) -> httpx.Response:
        return await self._client.post(f"/vpn/generate/{telegram_id}?days={days}")

    async def _get_subscription_password(self, telegram_id: int) -> str:
        async with self._session_factory() as session:
            statement = (
                select(Subscription.hysteria_password)
                .join(User, User.id == Subscription.user_id)
                .where(User.telegram_id == telegram_id)
                .order_by(Subscription.id.desc())
                .limit(1)
            )
            result = await session.execute(statement)
            password = result.scalar_one()
        return password

    async def test_health_check_returns_ok(self) -> None:
        response = await self._client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "service": "vpn-backend"},
        )

    async def test_register_user_is_idempotent(self) -> None:
        first_response = await self._register_user()
        second_response = await self._register_user()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.json()["status"], "success")
        self.assertIn("уже зарегистрирован", second_response.json()["message"])

    async def test_generate_vpn_config_creates_and_reuses_active_subscription(
        self,
    ) -> None:
        await self._register_user()

        first_response = await self._generate_vpn_config(days=30)
        second_response = await self._generate_vpn_config(days=90)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)

        first_payload = first_response.json()
        second_payload = second_response.json()

        self.assertEqual(first_payload["telegram_id"], 1001)
        self.assertTrue(first_payload["config_url"].startswith("hysteria2://"))
        self.assertEqual(first_payload["days_left"], 30)
        self.assertEqual(first_payload["config_url"], second_payload["config_url"])
        self.assertEqual(second_payload["days_left"], 30)

    async def test_hysteria_auth_accepts_active_subscription(self) -> None:
        await self._register_user()
        await self._generate_vpn_config()
        password = await self._get_subscription_password(telegram_id=1001)

        response = await self._client.post(
            "/hysteria/auth",
            json={"addr": "127.0.0.1:50000", "auth": password, "tx": 0},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "id": "tg_1001"})

    async def test_user_stats_without_active_subscription_returns_zeroed_payload(
        self,
    ) -> None:
        await self._register_user()

        response = await self._client.get("/users/1001/stats")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "telegram_id": 1001,
                "client_id": "tg_1001",
                "subscription_active": False,
                "days_left": 0,
                "tx_bytes": 0,
                "rx_bytes": 0,
                "online_connections": 0,
            },
        )

    async def test_user_stats_with_active_subscription_uses_hysteria_status(
        self,
    ) -> None:
        await self._register_user()
        await self._generate_vpn_config()

        hysteria_client.get_user_status = AsyncMock(
            return_value=HysteriaUserStatus(
                client_id="tg_1001",
                tx_bytes=1024,
                rx_bytes=2048,
                online_connections=2,
            )
        )

        response = await self._client.get("/users/1001/stats")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["subscription_active"])
        self.assertEqual(response.json()["tx_bytes"], 1024)
        self.assertEqual(response.json()["rx_bytes"], 2048)
        self.assertEqual(response.json()["online_connections"], 2)
        hysteria_client.get_user_status.assert_awaited_once_with(
            client_id="tg_1001",
            clear_traffic=False,
        )

    async def test_kick_user_calls_hysteria_api_for_active_subscription(self) -> None:
        await self._register_user()
        await self._generate_vpn_config()
        hysteria_client.kick_clients = AsyncMock(return_value=None)

        response = await self._client.post("/users/1001/kick")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"telegram_id": 1001, "client_id": "tg_1001", "kicked": True},
        )
        hysteria_client.kick_clients.assert_awaited_once_with(["tg_1001"])

    async def test_subscribe_vpn_extends_active_subscription(self) -> None:
        await self._register_user()
        first = await self._client.post("/vpn/subscribe/1001?days=30")
        self.assertEqual(first.status_code, 200)
        first_left = first.json()["days_left"]
        second = await self._client.post("/vpn/subscribe/1001?days=14")
        self.assertEqual(second.status_code, 200)
        second_left = second.json()["days_left"]
        self.assertGreaterEqual(second_left, first_left + 13)


if __name__ == "__main__":
    unittest.main()
