from __future__ import annotations

from alliance_platform.ui.html_components.slots import get_slot_context
from alliance_platform.ui.html_components.slots import merge_slot_props
from alliance_platform.ui.html_components.slots import push_slot_scope
from alliance_platform.ui.html_components.slots import replace_slot_scope
from django.template import Context
from django.test import SimpleTestCase


class HtmlUISlotsTestCase(SimpleTestCase):
    def test_merge_slot_props_prefers_child_values(self):
        merged = merge_slot_props(
            {"variant": "outlined", "size": "sm", "className": "slot-class"},
            {"size": "lg", "className": "child-class"},
        )

        self.assertEqual(merged["variant"], "outlined")
        self.assertEqual(merged["size"], "lg")
        self.assertEqual(merged["className"], "slot-class child-class")

    def test_push_slot_scope_merges_and_restores_context(self):
        context = Context()

        with push_slot_scope(context, {"button": {"variant": "solid"}}):
            with push_slot_scope(
                context,
                {"button": {"size": "lg"}, "badge": {"color": "gray"}},
            ):
                slot_context = get_slot_context(context)
                self.assertEqual(slot_context["button"], {"size": "lg"})
                self.assertEqual(slot_context["badge"], {"color": "gray"})

            slot_context = get_slot_context(context)
            self.assertEqual(slot_context["button"], {"variant": "solid"})
            self.assertNotIn("badge", slot_context)

        self.assertEqual(get_slot_context(context), {})

    def test_replace_slot_scope_hides_and_restores_inherited_slots(self):
        context = Context()

        with push_slot_scope(context, {"heading": {"className": "outer-heading"}}):
            with replace_slot_scope(context, {}):
                self.assertEqual(get_slot_context(context), {})

            self.assertEqual(
                get_slot_context(context),
                {"heading": {"className": "outer-heading"}},
            )
