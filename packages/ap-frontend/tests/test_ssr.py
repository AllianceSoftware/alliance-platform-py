import json
from unittest import mock

from alliance_platform.frontend.bundler.ssr import BundlerAssetServerSideRenderer
from alliance_platform.frontend.bundler.ssr import SSRItem
from django.test import SimpleTestCase
import requests

from tests.test_utils import bundler as bundler_test_utils
from tests.test_utils import override_ap_frontend_settings


class DummySSRItem(SSRItem):
    def get_ssr_type(self):
        return "Component"

    def get_ssr_payload(self, ssr_context):
        return {
            "component": "div",
            "props": {"label": "hello"},
            "identifierPrefix": "ITEM",
        }


class MockResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.content = json.dumps(data).encode()

    def json(self):
        return self._data


class SSRRendererTests(SimpleTestCase):
    def create_bundler(self):
        return bundler_test_utils.TestViteBundler(
            **bundler_test_utils.bundler_kwargs,  # type: ignore[arg-type]
            mode="development",
        )

    @override_ap_frontend_settings()
    def test_payload_uses_v2_shape(self):
        bundler = self.create_bundler()
        renderer = BundlerAssetServerSideRenderer({"PLACEHOLDER": DummySSRItem()})

        def mocked_post(*args, **kwargs):
            payload = json.loads(kwargs["data"])
            self.assertEqual(payload["version"], 2)
            self.assertTrue(isinstance(payload["requestId"], str) and payload["requestId"])
            self.assertIn("items", payload)
            self.assertIn("requiredImports", payload)
            return MockResponse(
                {
                    "renderedItems": {
                        "PLACEHOLDER": {
                            "html": "<div>rendered</div>",
                            "renderErrors": [],
                        }
                    },
                    "errors": {},
                }
            )

        with mock.patch("alliance_platform.frontend.bundler.ssr.get_bundler", return_value=bundler):
            with mock.patch("requests.post", side_effect=mocked_post):
                result = renderer.process("PLACEHOLDER", global_context={})
                self.assertEqual(result, "<div>rendered</div>")

    @override_ap_frontend_settings()
    def test_process_handles_cancelled_response_shape(self):
        bundler = self.create_bundler()
        renderer = BundlerAssetServerSideRenderer({"PLACEHOLDER": DummySSRItem()})

        with mock.patch("alliance_platform.frontend.bundler.ssr.get_bundler", return_value=bundler):
            with mock.patch("requests.post", return_value=MockResponse({"cancelled": True})):
                result = renderer.process("PLACEHOLDER", global_context={})
                self.assertEqual(result, "<!-- SSR_FAILED -->")

    @override_ap_frontend_settings(SSR_CANCEL_ON_TIMEOUT=True)
    def test_timeout_triggers_cancel_request(self):
        bundler = self.create_bundler()
        renderer = BundlerAssetServerSideRenderer({})
        payload = {"requestId": "req-1", "version": 2, "items": {}, "requiredImports": {}}
        called_urls: list[str] = []

        def mocked_post(url, *args, **kwargs):
            called_urls.append(url)
            if url.endswith("/ssr"):
                raise requests.exceptions.Timeout()
            return MockResponse({"cancelled": True})

        with mock.patch("alliance_platform.frontend.bundler.ssr.get_bundler", return_value=bundler):
            with mock.patch("alliance_platform.frontend.bundler.ssr.requests.post", side_effect=mocked_post):
                self.assertIsNone(renderer.process_ssr(payload))

        self.assertTrue(any(url.endswith("/ssr") for url in called_urls))
        self.assertTrue(any(url.endswith("/ssr/cancel") for url in called_urls))
