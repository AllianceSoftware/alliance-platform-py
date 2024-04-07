from pathlib import Path
import threading
from typing import Callable
from unittest import mock

from alliance_platform.frontend.bundler.context import BundlerAsset
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE
from django.test import TestCase
from django.test import modify_settings
from django.test import override_settings
from django.urls import reverse


def execute_request(
    client: object,
    url_path: str,
    data: dict[str, str | int] | None = None,
    thread_count: int = 1,
    prehook: Callable[[object, int], object] | None = None,
):
    """
    Execute a request, optionally on multiple threads

    Taken from https://github.com/AllianceSoftware/django-allianceutils/blob/f31e9ef343ef6ade4776ebcbbb0c22445c5bc1f9/test_allianceutils/tests/middleware/tests.py#L22

    :param url_path: URL path to request
    :param data: POST variables
    :param thread_count: number of threads to create & run this request in
    :return: a list of responses if `thread_pool` more than 1, otherwise a single response
    """
    thread_exceptions = []
    thread_responses = []

    def do_request(client=None, count=None):
        try:
            if prehook:
                client = prehook(client, count)
            response = client.post(path=url_path, data=data, content_type="application/json")
            thread_responses.append(response)
        except Exception as ex:
            thread_exceptions.append(ex)
            raise

    if thread_count == 1:
        do_request(client, 0)
        return thread_responses[0]

    threads = [threading.Thread(target=do_request, args=(client, count)) for count in range(thread_count)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if thread_exceptions:
        raise Exception(f"Found {len(thread_exceptions)} exception(s): {thread_exceptions}")

    return thread_responses


@override_settings(ROOT_URLCONF="test_alliance_platform_frontend.urls")
@modify_settings(
    MIDDLEWARE={
        "remove": ["stronghold.middleware.LoginRequiredMiddleware"],
        "append": [
            "alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware",
        ],
    },
)
class BundlerAssetContextTestCase(TestCase):
    def setUp(self):
        self.path = reverse("bundler_container_ids")

    def test_container_ids_unique(self):
        """Make sure container ids are unique when multiple threads used"""
        thread_count = 13
        container_count = 3
        responses = execute_request(
            client=self.client,
            url_path=self.path,
            thread_count=thread_count,
            data={"containerCount": container_count},
        )
        container_ids = []
        for response in responses:
            container_ids += response.json()["container_ids"]
        self.assertEqual(len(container_ids), thread_count * container_count)
        self.assertEqual(len(container_ids), len(set(container_ids)))

    def test_middleware_queue_ssr_json_response(self):
        # Can't SSR if response isn't text/html - check for this
        with mock.patch(
            "alliance_platform.frontend.bundler.ssr.BundlerAssetServerSideRenderer.process_ssr"
        ) as mock_method:
            with self.assertWarns(
                UserWarning, msg="There are items to SSR but the response is application/json"
            ):
                self.client.post(
                    reverse("bundler_ssr"),
                    data={"items": ["item 1", "item 2"]},
                    content_type="application/json",
                )
                mock_method.assert_not_called()

    def test_middleware_queue_ssr(self):
        with mock.patch(
            "alliance_platform.frontend.bundler.ssr.BundlerAssetServerSideRenderer.process_ssr"
        ) as mock_method:
            # Mock server rendering to just return dummy html for each item
            mock_method.return_value = {
                "renderedItems": {
                    "<!-- ___SSR_PLACEHOLDER_0___ -->": {"html": "<rendered item 1>"},
                    "<!-- ___SSR_PLACEHOLDER_1___ -->": {"html": "<rendered item 2>"},
                },
                "errors": {},
            }
            response = self.client.post(
                reverse("bundler_ssr"),
                data={"items": ["item 1", "item 2"]},
                content_type="application/json",
                HTTP_ACCEPT="text/html",
            )
            self.assertEqual(
                [
                    "item 1: <rendered item 1>",
                    "item 2: <rendered item 2>",
                ],
                response.content.decode().split("\n"),
            )

    def test_asset_context_get_assets(self):
        my_asset_paths = [Path("/path1")]

        class MyAsset(BundlerAsset):
            def get_paths_for_bundling(self) -> list[Path]:
                return my_asset_paths

        my_other_asset_paths = [Path("/other/path1"), Path("/other/path2")]

        class MyOtherAsset(BundlerAsset):
            def get_paths_for_bundling(self) -> list[Path]:
                return my_other_asset_paths

        with BundlerAssetContext(skip_checks=True) as context:
            origin = Origin(UNKNOWN_SOURCE)
            asset1 = MyAsset(origin)
            asset2 = MyOtherAsset(origin)
            self.assertEqual(asset1.bundler_asset_context, context)
            self.assertEqual(set(context.get_assets()), {asset1, asset2})
            self.assertEqual(set(context.get_assets(MyAsset)), {asset1})
            self.assertEqual(set(context.get_asset_paths()), {*my_asset_paths, *my_other_asset_paths})
            self.assertEqual(set(context.get_asset_paths(MyOtherAsset)), set(my_other_asset_paths))
