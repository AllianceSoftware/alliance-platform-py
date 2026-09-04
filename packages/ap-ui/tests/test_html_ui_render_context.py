from __future__ import annotations

from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import ChildReport
from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import RenderFrame
from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import (
    collect_child_reports,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import (
    find_leading_child_report,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import (
    find_render_payload,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import (
    push_render_frame,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.render_context import report_child
from django.template import Context
from django.test import SimpleTestCase


class HtmlUIRenderContextTestCase(SimpleTestCase):
    def test_leading_child_report_must_anchor_at_the_start(self):
        report = ChildReport(component="icon", slot="icon", html="<i>icon</i>")

        self.assertEqual(
            find_leading_child_report(
                " <i>icon</i> Label ",
                [report],
                component="icon",
                slot="icon",
            ),
            (report, "Label"),
        )
        self.assertIsNone(
            find_leading_child_report(
                "<span><i>icon</i></span> Label",
                [report],
                component="icon",
                slot="icon",
            )
        )

    def test_nearest_typed_payload_is_restored_after_nested_frame(self):
        context = Context()

        with push_render_frame(context, RenderFrame(component="outer", payload="outer")):
            self.assertEqual(find_render_payload(context, str), "outer")
            with push_render_frame(context, RenderFrame(component="inner", payload="inner")):
                self.assertEqual(find_render_payload(context, str), "inner")
            self.assertEqual(find_render_payload(context, str), "outer")

        self.assertIsNone(find_render_payload(context, str))

    def test_frames_are_restored_when_rendering_raises(self):
        context = Context()

        with self.assertRaisesMessage(RuntimeError, "render failed"):
            with push_render_frame(context, RenderFrame(component="broken", payload="value")):
                raise RuntimeError("render failed")

        self.assertIsNone(find_render_payload(context, str))

    def test_non_component_scopes_are_transparent_but_components_are_report_boundaries(self):
        context = Context()
        report = ChildReport(component="icon", slot="icon", html="<span></span>")

        with push_render_frame(context, RenderFrame(component="button")):
            with collect_child_reports(context) as reports:
                with push_render_frame(context, RenderFrame(slots={"icon": {"size": "xs"}})):
                    report_child(context, report)
                with push_render_frame(context, RenderFrame(component="wrapper")):
                    report_child(context, report)

            self.assertEqual(reports, [report])

    def test_each_collection_receives_a_fresh_report_list(self):
        context = Context()
        first_report = ChildReport(component="icon", slot="icon", html="<span>first</span>")
        second_report = ChildReport(component="icon", slot="icon", html="<span>second</span>")

        with push_render_frame(context, RenderFrame(component="button")) as frame:
            with collect_child_reports(context) as first:
                report_child(context, first_report)
            with collect_child_reports(context) as second:
                report_child(context, second_report)

            self.assertEqual(first, [first_report])
            self.assertEqual(second, [second_report])
            self.assertEqual(frame.child_reports, [first_report, second_report])
