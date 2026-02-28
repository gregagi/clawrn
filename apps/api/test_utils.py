from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.api.utils import _get_api_key_from_headers


class APIHeaderParsingTestCase(SimpleTestCase):
    def _request(self, headers):
        return SimpleNamespace(headers=headers)

    def test_get_api_key_from_headers_prefers_x_api_key(self):
        request = self._request({"X-API-Key": "abc123"})

        self.assertEqual(_get_api_key_from_headers(request), "abc123")

    def test_get_api_key_from_headers_accepts_bearer_scheme(self):
        request = self._request({"Authorization": "Bearer abc123"})

        self.assertEqual(_get_api_key_from_headers(request), "abc123")

    def test_get_api_key_from_headers_handles_non_string_authorization_safely(self):
        request = self._request({"Authorization": 12345})

        self.assertIsNone(_get_api_key_from_headers(request))

    def test_get_api_key_from_headers_handles_non_string_x_api_key_safely(self):
        request = self._request({"X-API-Key": object(), "Authorization": "Token fallback-key"})

        self.assertEqual(_get_api_key_from_headers(request), "fallback-key")

    def test_get_api_key_from_headers_handles_missing_headers_attribute(self):
        request = SimpleNamespace()

        self.assertIsNone(_get_api_key_from_headers(request))
