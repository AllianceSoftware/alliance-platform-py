from __future__ import annotations

from django.test import RequestFactory

from tests.parity.base import HtmlUIParityTestCase


class UITableParityTestCase(HtmlUIParityTestCase):
    fixture_component = "table"

    request_factory = RequestFactory()

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                # Sortable cases record the URL the React render happened at (ColumnHeaderLink
                # reads it from the SSR context); build the matching request for the static
                # renderer's URL generation.
                context_kwargs = None
                current_url = case.get("meta", {}).get("current_url")
                if current_url:
                    context_kwargs = {"request": self.request_factory.get(current_url)}
                self.assert_parity_case(case, context_kwargs)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template(
                '{% ui "table" aria_label="Users" %}{% ui "table_body" %}{% endui %}{% endui %}'
            )
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertTrue(
            any(
                path.endswith("@alliancesoftware/ui/components/table/Table.css.ts") for path in resource_paths
            )
        )
        self.assertTrue(any(path.endswith("@alliancesoftware/icons/Icon.css.ts") for path in resource_paths))
