from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from alliance_platform.ui.management.commands.ui_migration_check import LEGACY_COMPONENT_MIGRATIONS
from alliance_platform.ui.templatetags.alliance_platform.ui import register
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.test import override_settings


class UIMigrationCheckTestCase(SimpleTestCase):
    def write_template(self, base_dir: Path, relative_path: str, contents: str) -> Path:
        path = base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def run_check(
        self,
        base_dir: Path,
        *paths: str | Path,
        strict: bool = False,
    ) -> str:
        stdout = StringIO()
        with override_settings(BASE_DIR=base_dir):
            call_command(
                "ui_migration_check",
                *(str(path) for path in paths),
                strict=strict,
                no_color=True,
                stdout=stdout,
            )
        return stdout.getvalue()

    def test_central_mapping_covers_registered_legacy_component_tags(self):
        registered_components = set(register.tags) - {"create_dict", "icon", "ui"}
        mapped_named_tags = {
            name for name, migration in LEGACY_COMPONENT_MIGRATIONS.items() if migration.named_tag
        }
        self.assertEqual(mapped_named_tags, registered_components)

    def test_default_discovery_reports_relative_file_and_exact_line_and_skips_build_dirs(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/navigation.html",
                '{% load alliance_platform.ui %}\n\n{% Button variant="plain" %}Home{% endButton %}\n',
            )
            self.write_template(base_dir, "node_modules/ignored.html", "{% Button %}Ignored{% endButton %}")
            self.write_template(base_dir, "build/ignored.html", "{% Button %}Ignored{% endButton %}")
            self.write_template(
                base_dir,
                ".claude/worktrees/ignored.html",
                "{% Button %}Ignored{% endButton %}",
            )

            output = self.run_check(base_dir)

        self.assertIn(
            'templates/navigation.html:3: [READY] tag Button -> {% ui "button" %}',
            output,
        )
        self.assertNotIn("ignored.html", output)
        self.assertIn("Button: ready=1", output)
        self.assertIn("Total: 1", output)

    def test_renderer_contract_accepts_aliases_data_and_aria_and_flags_unsupported_props(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/button.html",
                '{% Button class_name="action" data_testid="save" aria_label="Save" '
                "disabled=True made_up=True on_press=handler %}Save{% endButton %}",
            )

            output = self.run_check(base_dir)

        self.assertIn("[REVIEW] tag Button", output)
        self.assertIn("unsupported props: madeUp, onPress", output)
        self.assertNotIn("className,", output)
        self.assertNotIn("data-testid", output)
        self.assertNotIn("aria-label", output)
        self.assertNotIn("isDisabled", output)

    def test_bulk_props_and_legacy_render_options_require_review(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/bulk.html",
                "{% Button props=button_props component:omit_if_empty=True %}Save{% endButton %}",
            )

            output = self.run_check(base_dir)

        self.assertIn("bulk props= requires review because its keys are not statically known", output)
        self.assertIn("legacy rendering options require review: component:omit_if_empty", output)
        self.assertIn("Button: review=1", output)

    def test_generic_alliance_ui_components_are_reported_and_custom_components_are_excluded(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/generic.html",
                '{% component "@alliancesoftware/ui" "TextInput" placeholder="Name" made_up=True %}'
                "{% endcomponent %}\n"
                '{% component "@alliancesoftware/ui" "Badge" %}New{% endcomponent %}\n'
                '{% component "components/MyCard" "MyCard" %}Custom{% endcomponent %}\n',
            )

            output = self.run_check(base_dir)

        self.assertIn(
            'component "@alliancesoftware/ui" "TextInput" -> {% ui "text_input" %}',
            output,
        )
        self.assertIn("unsupported props: madeUp", output)
        self.assertIn(
            'component "@alliancesoftware/ui" "Badge" -> no static equivalent yet',
            output,
        )
        self.assertNotIn("MyCard", output)
        self.assertIn("Badge: no-static-equivalent=1", output)
        self.assertIn("TextInput: review=1", output)

    def test_dynamic_icon_names_are_flagged_where_static_migration_requires_literals(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/icons.html",
                "{% Icon icon_name %}\n"
                '{% Icon "CheckOutlined" %}\n'
                '{% Menubar.SubMenu title="Manage" icon=menu_icon %}'
                "{% endMenubar.SubMenu %}\n"
                '{% component "@alliancesoftware/ui" "Menubar.Section" '
                'title="Account" icon=section_icon %}{% endcomponent %}\n',
            )

            output = self.run_check(base_dir)

        self.assertIn("templates/icons.html:1: [REVIEW] tag Icon", output)
        self.assertIn("templates/icons.html:2: [READY] tag Icon", output)
        self.assertIn("icon name must be a static string literal", output)
        self.assertIn("templates/icons.html:3: [REVIEW] tag Menubar.SubMenu", output)
        self.assertIn("icon must be a static string literal", output)
        self.assertIn(
            'templates/icons.html:4: [REVIEW] component "@alliancesoftware/ui" "Menubar.Section"',
            output,
        )
        self.assertIn("Icon: ready=1, review=1", output)

    def test_pagination_has_static_renderer_and_behavioral_props_have_clear_review_reasons(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/pagination.html",
                "{% Pagination page=page total=total page_size=page_size "
                'aria_label="Pagination" %}{% endPagination %}\n'
                "{% Pagination total=total is_page_size_selectable=True "
                "on_page_change=callback %}{% endPagination %}",
            )

            output = self.run_check(base_dir)

        self.assertIn(
            'templates/pagination.html:1: [READY] tag Pagination -> {% ui "pagination" %}',
            output,
        )
        self.assertIn(
            'templates/pagination.html:2: [REVIEW] tag Pagination -> {% ui "pagination" %}',
            output,
        )
        self.assertIn("unsupported props: isPageSizeSelectable, onPageChange", output)
        self.assertIn("isPageSizeSelectable: page-size selection requires", output)
        self.assertIn("onPageChange: callback pagination is not supported", output)
        self.assertIn("Pagination: ready=1, review=1", output)

    def test_inline_alert_has_static_renderer_and_flags_dismissal_behavior(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/alerts.html",
                '{% InlineAlert intent="danger" %}Failed{% endInlineAlert %}\n'
                '{% component "@alliancesoftware/ui" "InlineAlert" is_dismissable=True %}'
                "Dismiss me{% endcomponent %}",
            )

            output = self.run_check(base_dir)

        self.assertIn(
            'templates/alerts.html:1: [READY] tag InlineAlert -> {% ui "inline_alert" %}',
            output,
        )
        self.assertIn(
            'templates/alerts.html:2: [REVIEW] component "@alliancesoftware/ui" "InlineAlert"',
            output,
        )
        self.assertIn("isDismissable: dismissible alerts require client-side state", output)
        self.assertIn("InlineAlert: ready=1, review=1", output)

    def test_generic_layout_components_have_static_renderers(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/layout.html",
                '{% component "@alliancesoftware/ui" "Heading" %}Title{% endcomponent %}\n'
                '{% component "@alliancesoftware/ui" "Header" %}Header{% endcomponent %}\n'
                '{% component "@alliancesoftware/ui" "Content" %}Content{% endcomponent %}\n'
                '{% component "@alliancesoftware/ui" "Footer" %}Footer{% endcomponent %}',
            )

            output = self.run_check(base_dir)

        for line, component, renderer in [
            (1, "Heading", "heading"),
            (2, "Header", "header"),
            (3, "Content", "content"),
            (4, "Footer", "footer"),
        ]:
            self.assertIn(
                f'templates/layout.html:{line}: [READY] component "@alliancesoftware/ui" '
                f'"{component}" -> {{% ui "{renderer}" %}}',
                output,
            )

    def test_intrinsic_component_wrappers_suggest_native_html_and_note_deferred_urls(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/native.html",
                '{% component "a" href="/about/" %}About{% endcomponent %}\n'
                '{% component "a" href="private"|url_with_perm %}Private{% endcomponent %}\n'
                '{% component "components/Card" "Card" %}Custom{% endcomponent %}\n',
            )

            output = self.run_check(base_dir)

        self.assertIn('templates/native.html:1: [NATIVE] component "a" -> native <a> HTML', output)
        self.assertIn('templates/native.html:2: [REVIEW] component "a" -> native <a> HTML', output)
        self.assertIn("native HTML does not automatically preserve component omission (href)", output)
        self.assertNotIn("Card", output)
        self.assertIn("a: review=1, native=1", output)

    def test_explicit_directory_and_file_paths_narrow_the_scan(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(base_dir, "templates/one.html", "{% Button %}One{% endButton %}")
            selected = self.write_template(
                base_dir,
                "other/two.html",
                "{% ButtonGroup %}{% endButtonGroup %}",
            )

            directory_output = self.run_check(base_dir, selected.parent)
            file_output = self.run_check(base_dir, selected)

        for output in (directory_output, file_output):
            self.assertIn("other/two.html:1", output)
            self.assertNotIn("templates/one.html", output)

    def test_findings_succeed_by_default_and_strict_mode_exits_nonzero(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(base_dir, "templates/button.html", "{% Button %}Save{% endButton %}")

            output = self.run_check(base_dir)
            self.assertIn("Button: ready=1", output)

            strict_stdout = StringIO()
            with override_settings(BASE_DIR=base_dir):
                with self.assertRaisesMessage(
                    CommandError,
                    "UI migration check found 1 legacy usage(s)",
                ):
                    call_command(
                        "ui_migration_check",
                        strict=True,
                        no_color=True,
                        stdout=strict_stdout,
                    )
            self.assertIn("Summary:", strict_stdout.getvalue())

    def test_invalid_path_is_a_command_error(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            with override_settings(BASE_DIR=base_dir):
                with self.assertRaisesMessage(CommandError, "Template path does not exist"):
                    call_command("ui_migration_check", base_dir / "missing")

    def test_custom_only_scan_reports_no_findings(self):
        with TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            self.write_template(
                base_dir,
                "templates/custom.html",
                '{% component "components/Card" "Card" %}Custom{% endcomponent %}',
            )

            output = self.run_check(base_dir)

        self.assertIn("No legacy Alliance UI template usages found.", output)
