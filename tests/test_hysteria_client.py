from __future__ import annotations

import unittest

from backend.hysteria_client import (
    HysteriaApiClient,
    HysteriaSettings,
    build_hysteria_client_id,
    parse_bool_env,
)


class HysteriaHelpersTests(unittest.TestCase):
    def test_parse_bool_env_supports_common_truthy_values(self) -> None:
        self.assertTrue(parse_bool_env("1"))
        self.assertTrue(parse_bool_env("true"))
        self.assertTrue(parse_bool_env(" YES "))
        self.assertTrue(parse_bool_env("On"))

    def test_parse_bool_env_returns_default_for_none(self) -> None:
        self.assertTrue(parse_bool_env(None, default=True))
        self.assertFalse(parse_bool_env(None, default=False))

    def test_build_hysteria_client_id(self) -> None:
        self.assertEqual(build_hysteria_client_id(123456), "tg_123456")

    def test_build_client_uri_with_optional_params(self) -> None:
        settings = HysteriaSettings(
            api_url="http://127.0.0.1:25413",
            api_token=None,
            server_host="vpn.example.com",
            server_port="443",
            server_sni="vpn.example.com",
            server_insecure=True,
            obfs="salamander",
            obfs_password="obfs-secret",
            request_timeout_seconds=10.0,
        )
        client = HysteriaApiClient(settings)

        uri = client.build_client_uri("pass with spaces")

        self.assertTrue(uri.startswith("hysteria2://pass%20with%20spaces@vpn.example.com:443/"))
        self.assertIn("sni=vpn.example.com", uri)
        self.assertIn("insecure=1", uri)
        self.assertIn("obfs=salamander", uri)
        self.assertIn("obfs-password=obfs-secret", uri)


if __name__ == "__main__":
    unittest.main()
