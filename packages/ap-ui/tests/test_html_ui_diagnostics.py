from __future__ import annotations

import logging

from alliance_platform.ui.html_components import diagnostics
from alliance_platform.ui.html_components.components import UIButtonRenderer
from alliance_platform.ui.html_components.diagnostics import StaticComponentContractError
from alliance_platform.ui.html_components.diagnostics import report
from alliance_platform.ui.settings import ap_ui_settings
from django.conf import settings
from django.template import NodeList
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE
from django.test import SimpleTestCase
from django.test import override_settings

from tests.test_utils import override_ap_ui_settings

LOGGER = "alliance_platform.ui"

# Contains '%' so a message passed as a logging format string with arguments would not survive
MESSAGE = "Invalid 'width' prop passed: 100%"


def record_details(record):
    return (
        record.getMessage(),
        getattr(record, "component"),
        getattr(record, "origin"),
        getattr(record, "kind"),
    )


class DiagnosticsReportTestCase(SimpleTestCase):
    def setUp(self):
        super().setUp()
        diagnostics._reset_reported()
        self.addCleanup(diagnostics._reset_reported)

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_contract_report_logs_the_message_unchanged(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            report(MESSAGE, kind="contract", component="button", origin=Origin("templates/nav.html"))

        [record] = logs.records
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertEqual(record.msg, MESSAGE)
        self.assertEqual(record_details(record), (MESSAGE, "button", "templates/nav.html", "contract"))

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_unknown_details_log_as_none(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            report(MESSAGE, kind="contract", origin=Origin(UNKNOWN_SOURCE))

        self.assertEqual(record_details(logs.records[0]), (MESSAGE, None, None, "contract"))

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=True)
    def test_contract_report_raises_instead_of_logging_when_strict(self):
        origin = Origin("templates/nav.html")
        with self.assertNoLogs(LOGGER, level="WARNING"):
            with self.assertRaises(StaticComponentContractError) as raised:
                report(MESSAGE, kind="contract", component="button", origin=origin)

        self.assertEqual(str(raised.exception), f"{MESSAGE} (component 'button' in templates/nav.html)")
        self.assertEqual(raised.exception.component, "button")
        self.assertIs(raised.exception.origin, origin)

    def test_data_report_logs_whether_or_not_strict(self):
        for strict in (True, False):
            with self.subTest(strict=strict), override_ap_ui_settings(STATIC_COMPONENT_STRICT=strict):
                with self.assertLogs(LOGGER, level="WARNING") as logs:
                    report(MESSAGE, kind="data", component="pagination")

                self.assertEqual(
                    [record_details(record) for record in logs.records],
                    [(MESSAGE, "pagination", None, "data")],
                )

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=True)
    def test_error_message_names_what_is_known(self):
        origin = Origin("templates/nav.html")
        cases = [
            ({"component": "button", "origin": origin}, "Bad (component 'button' in templates/nav.html)"),
            ({"component": "button"}, "Bad (component 'button')"),
            ({"origin": origin}, "Bad (in templates/nav.html)"),
            ({"component": "button", "origin": Origin(UNKNOWN_SOURCE)}, "Bad (component 'button')"),
            ({}, "Bad"),
        ]
        for kwargs, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(StaticComponentContractError) as raised:
                    report("Bad", kind="contract", **kwargs)
                self.assertEqual(str(raised.exception), expected)

    @override_settings(DEBUG=False)
    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_contract_reports_log_once_per_component_and_message_outside_debug(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            for _ in range(3):
                report("Bad", kind="contract", component="button")
            report("Bad", kind="contract", component="icon")
            report("Worse", kind="contract", component="button")
            report("Bad", kind="contract", component="button")

        self.assertEqual(
            [(record.getMessage(), getattr(record, "component")) for record in logs.records],
            [("Bad", "button"), ("Bad", "icon"), ("Worse", "button")],
        )

    @override_settings(DEBUG=False)
    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_data_reports_always_log(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            for _ in range(3):
                report("Page 9 is past the last page", kind="data", component="pagination")

        self.assertEqual(len(logs.records), 3)

    @override_settings(DEBUG=True)
    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_nothing_is_deduplicated_in_debug(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            for _ in range(3):
                report("Bad", kind="contract", component="button")

        self.assertEqual(len(logs.records), 3)

    @override_settings(DEBUG=False)
    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_remembered_reports_are_bounded(self):
        with self.assertLogs(LOGGER, level="WARNING"):
            for index in range(diagnostics._MAX_REMEMBERED_REPORTS + 10):
                report(f"Bad {index}", kind="contract")

        self.assertLessEqual(len(diagnostics._reported), diagnostics._MAX_REMEMBERED_REPORTS)

    def test_unknown_kind_is_refused(self):
        with self.assertRaisesMessage(ValueError, "Unknown diagnostic kind 'warning'"):
            report("Bad", kind="warning")


class StaticComponentStrictSettingTestCase(SimpleTestCase):
    def without_strict_setting(self):
        return override_settings(ALLIANCE_PLATFORM={**settings.ALLIANCE_PLATFORM, "UI": {}})

    def test_defaults_to_debug(self):
        for debug in (True, False):
            with self.subTest(debug=debug), override_settings(DEBUG=debug), self.without_strict_setting():
                self.assertIs(ap_ui_settings.STATIC_COMPONENT_STRICT, debug)

    def test_default_follows_a_debug_override(self):
        with self.without_strict_setting():
            self.assertFalse(ap_ui_settings.STATIC_COMPONENT_STRICT)
            with override_settings(DEBUG=True):
                self.assertTrue(ap_ui_settings.STATIC_COMPONENT_STRICT)
            self.assertFalse(ap_ui_settings.STATIC_COMPONENT_STRICT)

    @override_settings(DEBUG=True)
    def test_explicit_value_wins_over_debug(self):
        with override_ap_ui_settings(STATIC_COMPONENT_STRICT=False):
            self.assertFalse(ap_ui_settings.STATIC_COMPONENT_STRICT)


class RendererReportTestCase(SimpleTestCase):
    def setUp(self):
        super().setUp()
        diagnostics._reset_reported()
        self.addCleanup(diagnostics._reset_reported)
        self.origin = Origin("templates/nav.html")
        self.renderer = UIButtonRenderer(
            props={},
            nodelist=NodeList(),
            origin=self.origin,
            target_var=None,
            register_asset=False,
        )

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=False)
    def test_report_fills_in_the_component_name_and_origin(self):
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.renderer.report(MESSAGE, kind="contract")

        self.assertEqual(
            record_details(logs.records[0]), (MESSAGE, "button", "templates/nav.html", "contract")
        )

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=True)
    def test_contract_report_raises_with_the_component_name_and_origin_when_strict(self):
        with self.assertRaises(StaticComponentContractError) as raised:
            self.renderer.report(MESSAGE, kind="contract")

        self.assertEqual(raised.exception.component, "button")
        self.assertIs(raised.exception.origin, self.origin)
