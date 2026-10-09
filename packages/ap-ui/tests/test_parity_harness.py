from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from tests.parity.base import CSS_MAPPINGS_PATH
from tests.parity.base import SYNC_FIXTURES_COMMAND
from tests.parity.base import HtmlUIParityTestCase
from tests.parity.normalizers import normalize_class_attributes
from tests.parity.normalizers import normalize_class_tokens
from tests.parity.normalizers import normalize_css_var_hashes

# Expected results come from running normalizeClassTokens in scripts/parity_cases/_helpers.mjs on
# the same arguments: (class value, allowed prefixes, keep_class_tokens, expected tokens).
JS_NORMALIZE_CLASS_TOKENS_CASES: list[tuple[str, list[str], list[str], list[str]]] = [
    (
        "Button_baseButton__1xyn7kcv font__1g6dhcj7u font_textSizes_sm__1g6dhcjb custom-class",
        ["Button"],
        [],
        ["Button_baseButton", "custom-class"],
    ),
    ("Icon_sizes_xxs__17znlfqe Icon_sizes_xxs__17znlfq8", ["Icon"], [], ["Icon_sizes_xxs"]),
    ("Button_sizes_sm__1xyn7kcx Button_sizes__1xyn7kcw", ["Button"], [], ["Button_sizes_sm"]),
    (
        "Popover_popover_bottom__ovoqx83 Popover_popoverBase__ovoqx80 OverlayCommon_overlayBase__16wtmn70",
        ["Popover"],
        [],
        ["Popover_popover_bottom"],
    ),
    (
        "NumberInput_stepButton_default__17rv46z5 NumberInput_stepButtonBase__17rv46z2",
        ["NumberInput"],
        [],
        ["NumberInput_stepButton_default"],
    ),
    (
        "Icon_circleBase__17znlfqu Icon_variants_circle__17znlfqy",
        ["Icon"],
        [],
        ["Icon_circleBase", "Icon_variants_circle"],
    ),
    (
        "Pagination_pagination_compact__1negsl65 Pagination_basePagination__1negsl61",
        ["Pagination"],
        [],
        ["Pagination_pagination_compact", "Pagination_basePagination"],
    ),
    (
        "LabeledInput_labeledInput__17lyobc6 LabeledInput_labeledInput_inputSize_sm__17lyobc7",
        ["LabeledInput"],
        [],
        ["LabeledInput_labeledInput_inputSize_sm"],
    ),
    (
        "LabeledInput_labeledInput__17lyobc6 LabeledInput_labeledInput_inputSize_sm__17lyobc7",
        ["LabeledInput"],
        ["LabeledInput_labeledInput"],
        ["LabeledInput_labeledInput", "LabeledInput_labeledInput_inputSize_sm"],
    ),
    ("Other_thing plain plain_child", [], [], ["Other_thing", "plain_child"]),
    ("  \t ", [], [], []),
    ("__1a2b3c Table_row__165xtj02", ["Table"], [], ["Table_row"]),
    ("a__b__c", ["a"], [], ["a__b"]),
]


class NormalizeClassTokensTestCase(SimpleTestCase):
    def test_matches_the_generator(self):
        for class_value, prefixes, keep_class_tokens, expected in JS_NORMALIZE_CLASS_TOKENS_CASES:
            with self.subTest(class_value=class_value, prefixes=prefixes, keep=keep_class_tokens):
                self.assertEqual(
                    normalize_class_tokens(class_value, prefixes, keep_class_tokens),
                    expected,
                )

    def test_class_attributes_are_rewritten_and_dropped_when_empty(self):
        self.assertEqual(
            normalize_class_attributes(
                '<div class="Table_tableWrapper__165xtj01 extra" data-class="x__y">'
                '<span class="font__1g6dhcj7u">a class="b__c"</span><input class="Table_row__1"/></div>',
                ["Table"],
            ),
            '<div class="Table_tableWrapper extra" data-class="x__y">'
            '<span>a class="b__c"</span><input class="Table_row"/></div>',
        )

    def test_css_var_hashes_are_stripped_from_style_attributes(self):
        self.assertEqual(
            normalize_css_var_hashes(
                '<th style="--components-table-columnWidth__1n87t70xc: 96px; color: red">--level__1a: 1</th>'
            ),
            '<th style="--components-table-columnWidth: 96px; color: red">--level__1a: 1</th>',
        )


class ParityHarnessTestCase(HtmlUIParityTestCase):
    def test_stylesheet_missing_from_the_mappings_fails_with_the_sync_command(self):
        # The example stat component's stylesheet is not in any parity case module.
        with self.assertRaises(self.failureException) as raised:
            with self.setup_render_context():
                self.render_ui_template('{% ui "stat" label="Open jobs" %}{% endui %}')

        message = str(raised.exception)
        self.assertIn(f"{CSS_MAPPINGS_PATH.name} has no class mapping for ", message)
        self.assertIn(str(Path("frontend/src/components/Stat.css.ts")), message)
        self.assertIn(SYNC_FIXTURES_COMMAND, message)

    def test_render_helpers_return_readable_class_names(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "pagination" page=1 total=10 page_size=10 aria_label="Pagination" %}'
            )

        # Hashes are stripped and the typography composed into the page button class is left out
        self.assertIn(
            'class="focusRing_base Button_baseButton Pagination_pageButton Pagination_grayButtonBase '
            'Pagination_basePageButton Pagination_currentPage"',
            output,
        )
        self.assertNotIn("font_", output)
