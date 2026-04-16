from __future__ import annotations

import unittest
from typing import Any

from bot.backend_client import BackendClient, BackendClientError, UserStats, VpnConfig


class DummyBackendClient(BackendClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None]] = []
        self._next_response: dict[str, Any] = {}

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((method, path, json, params))
        return self._next_response


class BackendClientMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_vpn_config_maps_payload_to_dataclass(self) -> None:
        client = DummyBackendClient()
        client._next_response = {
            "telegram_id": "1001",
            "config_url": "hysteria2://test@vpn.example.com:443/",
            "days_left": "30",
        }

        config: VpnConfig = await client.generate_vpn_config(telegram_id=1001, days=30)

        self.assertEqual(config.telegram_id, 1001)
        self.assertEqual(config.days_left, 30)
        self.assertTrue(config.config_url.startswith("hysteria2://"))
        self.assertEqual(
            client.calls[0],
            ("POST", "/vpn/generate/1001", None, {"days": "30"}),
        )

    async def test_get_user_stats_maps_payload_to_dataclass(self) -> None:
        client = DummyBackendClient()
        client._next_response = {
            "telegram_id": "1001",
            "client_id": "tg_1001",
            "subscription_active": True,
            "days_left": "10",
            "tx_bytes": "512",
            "rx_bytes": "1024",
            "online_connections": "2",
        }

        stats: UserStats = await client.get_user_stats(telegram_id=1001)

        self.assertEqual(stats.telegram_id, 1001)
        self.assertEqual(stats.client_id, "tg_1001")
        self.assertTrue(stats.subscription_active)
        self.assertEqual(stats.days_left, 10)
        self.assertEqual(stats.tx_bytes, 512)
        self.assertEqual(stats.rx_bytes, 1024)
        self.assertEqual(stats.online_connections, 2)
        self.assertEqual(client.calls[0], ("GET", "/users/1001/stats", None, None))

    async def test_request_json_without_started_session_raises_error(self) -> None:
        client = BackendClient()

        with self.assertRaises(BackendClientError):
            await client._request_json("GET", "/health")


if __name__ == "__main__":
    unittest.main()
