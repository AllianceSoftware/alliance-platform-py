from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import cast
from unittest import mock
from urllib.parse import quote
import warnings

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.templatetags.react import DeferredProp
from alliance_platform.frontend.templatetags.react import OmitComponentFromRendering
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.menubar import (
    UIMenubarRenderer,
)
from allianceutils.auth.permission import AmbiguousGlobalPermissionWarning
from allianceutils.tests.util import warning_filter
from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.http import HttpRequest
from django.template import Context
from django.template import Template
from django.template import TemplateSyntaxError
from django.template.base import NodeList
from django.test import TestCase
from django.test import override_settings
from test_alliance_platform_ui.factory import UserFactory
from test_alliance_platform_ui.models import User

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.base import test_development_bundler
from tests.parity.style_mocks import make_style_mapping_resolver
from tests.test_utils import override_ap_frontend_settings
from tests.test_utils.bundler import TestViteBundler
from tests.test_utils.bundler import bundler_kwargs
from tests.test_utils.bundler import bypass_frontend_resource_registry

BASIC_MENUBAR_TEMPLATE = (
    '{% ui "menubar" aria_label="Primary navigation" %}'
    '{% ui "menubar_item" key="dashboard" href="/dashboard/" %}Dashboard{% endui %}'
    '{% ui "menubar_submenu" key="users" title="Users" %}'
    '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
    '{% ui "menubar_item" href="/customers/" %}Customers{% endui %}'
    "{% endui %}"
    '{% ui "menubar_item" href="/audit/" %}Audit{% endui %}'
    "{% endui %}"
)


class DeniedUrl(DeferredProp):
    """Stand-in for a denied ``url_with_perm`` value (raises like ``NamedUrlDeferredProp``)."""

    def resolve(self, context: Context):
        raise OmitComponentFromRendering()


class UIMenubarComponentsTestCase(HtmlUIParityTestCase):
    """Unit tests for the static menubar components not covered by the parity fixtures."""

    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings]

    def test_menubar_renders_full_structure(self):
        output, caught = self.render_with_warnings(BASIC_MENUBAR_TEMPLATE)
        self.assertEqual(caught, [])
        # Root element with layout/orientation attributes, role and classes
        self.assertIn('data-apui="menubar"', output)
        self.assertIn('data-layout="horizontal"', output)
        self.assertIn('data-root-item-display="icon-and-label"', output)
        self.assertIn('data-orientation="horizontal"', output)
        self.assertIn('role="menubar"', output)
        self.assertIn('aria-orientation="horizontal"', output)
        self.assertIn('aria-label="Primary navigation"', output)
        self.assertIn('class="Menubar_menubar Menubar_horizontal"', output)
        self.assertNotIn("data-apui-menu-item-tooltip", output)
        # State class names exposed for the runtime
        self.assertIn('data-open-class="Menubar_isOpen"', output)
        self.assertIn('data-focused-class="Menubar_isFocused"', output)
        self.assertIn('data-popover-open-class="Popover_isOpen"', output)
        # Link item: real anchor with role/level/label and the content wrapper structure
        self.assertIn(
            '<li role="none" data-key="dashboard">'
            '<a role="menuitem" class="Menubar_menubarMenuItem Menubar_menubarMenuItemBase Menubar_rootMenuItem" data-level="0" '
            'aria-label="Dashboard" tabindex="0" href="/dashboard/">'
            '<div data-apui-menu-item-content-wrapper="">'
            '<span class="Menubar_menubarMenuItemContent" data-contentlevel="0" '
            'data-apui-menu-item-content="">'
            '<span data-apui-slot="label">Dashboard</span></span></div></a></li>',
            output,
        )
        # Submenu trigger: button with popup wiring and a chevron icon
        self.assertIn('<li role="none" data-key="users" data-apui-menu-submenu="">', output)
        self.assertIn('data-apui-menu-submenu-trigger=""', output)
        self.assertIn('data-apui-menu-submenu-chevron=""', output)
        self.assertIn('data-has-dropdown="true"', output)
        self.assertIn('aria-haspopup="true"', output)
        self.assertIn('aria-expanded="false"', output)
        self.assertIn('data-open="false"', output)
        self.assertIn('aria-controls="apui-menu-users"', output)
        self.assertIn("Menubar_hasDropdown", output)
        self.assertIn("Menubar_dropdownIcon", output)
        self.assertIn('d="M6 9L12 15L18 9"', output)  # chevron down
        # Popup: hidden popover wrapper containing the vertical menu
        self.assertIn(
            '<div class="Popover_popover_bottom" role="presentation" hidden data-apui-menu-popover="" '
            'data-placement="bottom"><div class="Popover_inner">'
            '<ul role="menu" id="apui-menu-users" class="Menubar_menubarMenu Menubar_vertical" '
            'data-apui-menu-container="" style="--level: 1">',
            output,
        )
        # Submenu children are one level deeper and unfocusable while hidden
        self.assertIn(
            '<a role="menuitem" class="Menubar_menubarMenuItem Menubar_menubarMenuItemBase Menubar_subMenu" data-level="1" '
            'aria-label="Admin" tabindex="-1" href="/admin/">',
            output,
        )

    def test_roving_tabindex_assignment(self):
        output, caught = self.render_with_warnings(BASIC_MENUBAR_TEMPLATE)
        self.assertEqual(caught, [])
        # Only the first enabled root item is a tab stop
        self.assertEqual(output.count('tabindex="0"'), 1)
        self.assertIn('aria-label="Dashboard" tabindex="0"', output)

    def test_default_focused_key_claims_tab_stop(self):
        template = (
            '{% ui "menubar" aria_label="Nav" default_focused_key="audit" %}'
            '{% ui "menubar_item" key="dashboard" href="/dashboard/" %}Dashboard{% endui %}'
            '{% ui "menubar_item" key="audit" href="/audit/" %}Audit{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('data-default-focused-key="audit"', output)
        self.assertEqual(output.count('tabindex="0"'), 1)
        self.assertIn('aria-label="Audit" tabindex="0"', output)

    def test_vertical_layout(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="vertical" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('data-layout="vertical"', output)
        self.assertIn('data-orientation="vertical"', output)
        self.assertIn('aria-orientation="vertical"', output)
        self.assertIn('class="Menubar_menubar Menubar_vertical"', output)
        # Vertical root submenus fly out to the right with a right-pointing chevron
        self.assertIn('data-placement="right"', output)
        self.assertIn('class="Popover_popover_right', output)
        self.assertIn('d="M9 18L15 12L9 6"', output)

    def test_inline_layout(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('data-layout="inline"', output)
        self.assertIn('data-orientation="vertical"', output)
        self.assertIn('class="Menubar_menubar Menubar_vertical Menubar_inline"', output)
        # Inline presentation uses the same stable popover subtree as flyout layouts. CSS makes
        # the shell display: contents while inline; the wrapper still owns closed/open visibility.
        self.assertIn(
            '<div class="Popover_popover_right" role="presentation" hidden '
            'data-apui-menu-popover="" data-placement="right"><div class="Popover_inner">'
            '<ul role="menu" id="apui-menu-users" class="Menubar_menubarMenu Menubar_vertical" '
            'data-apui-menu-container="" style="--level: 1">',
            output,
        )
        self.assertNotIn("data-apui-menu-popup", output)
        # Inline submenu chevron points down while closed
        self.assertIn('d="M6 9L12 15L18 9"', output)

    def test_initial_inline_layout_keeps_popup_tree_for_runtime_layout_switch(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" default_expanded_keys="users" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)

        self.assertEqual(caught, [])
        self.assertEqual(output.count("data-apui-menu-popover"), 1)
        self.assertEqual(output.count('id="apui-menu-users"'), 1)
        self.assertNotIn("data-apui-menu-popup", output)
        self.assertIn(
            'class="Popover_popover_right Popover_isOpen" role="presentation" '
            'data-apui-menu-popover="" data-placement="right"',
            output,
        )
        self.assertNotIn(" hidden ", output)
        self.assertIn('data-layout="inline"', output)
        self.assertIn('data-apui-attach="menubar"', output)
        self.assertNotIn("<script", output)

    def test_expanded_keys_storage_key_is_exposed_to_the_static_runtime(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" '
            'expanded_keys_storage_key="primary-navigation-expanded" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)

        self.assertEqual(caught, [])
        self.assertIn(
            'data-expanded-keys-storage-key="primary-navigation-expanded"',
            output,
        )
        self.assertIn('data-apui-attach="menubar"', output)

    def test_expanded_keys_cookie_is_applied_during_the_server_render(self):
        request = HttpRequest()
        request.COOKIES["primary-navigation-expanded"] = quote(json.dumps(["reports"]), safe="")
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" '
            'default_expanded_keys="manage" '
            'expanded_keys_storage_key="primary-navigation-expanded" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_submenu" key="reports" title="Reports" %}'
            '{% ui "menubar_item" href="/weekly/" %}Weekly{% endui %}'
            "{% endui %}"
            "{% endui %}"
            '{% ui "menubar_submenu" key="manage" title="Manage" %}'
            '{% ui "menubar_item" href="/account/" %}Account{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )

        output, caught = self.render_with_warnings(template, {"request": request})

        self.assertEqual(caught, [])
        # The nested stored key opens its ancestor path in the HTML response, before JavaScript.
        self.assertRegex(
            output,
            re.compile(
                r'data-key="users" data-apui-menu-submenu=""><button[^>]+aria-expanded="true"',
                re.DOTALL,
            ),
        )
        self.assertRegex(
            output,
            re.compile(
                r'data-key="reports" data-apui-menu-submenu=""><button[^>]+aria-expanded="true"',
                re.DOTALL,
            ),
        )
        self.assertRegex(
            output,
            re.compile(
                r'data-key="manage" data-apui-menu-submenu=""><button[^>]+aria-expanded="false"',
                re.DOTALL,
            ),
        )

    def test_empty_expanded_keys_cookie_overrides_defaults(self):
        request = HttpRequest()
        request.COOKIES["primary-navigation-expanded"] = quote(json.dumps([]), safe="")
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" '
            'default_expanded_keys="users" '
            'expanded_keys_storage_key="primary-navigation-expanded" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )

        output, caught = self.render_with_warnings(template, {"request": request})

        self.assertEqual(caught, [])
        self.assertIn('aria-label="Users" aria-haspopup="true" aria-expanded="false"', output)

    def test_invalid_expanded_keys_cookie_falls_back_to_defaults(self):
        request = HttpRequest()
        request.COOKIES["primary-navigation-expanded"] = "%7Binvalid"
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" '
            'default_expanded_keys="users" '
            'expanded_keys_storage_key="primary-navigation-expanded" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )

        output, caught = self.render_with_warnings(template, {"request": request})

        self.assertEqual(caught, [])
        self.assertIn('aria-label="Users" aria-haspopup="true" aria-expanded="true"', output)

    def test_invalid_expanded_keys_cookie_name_is_ignored(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" '
            'expanded_keys_storage_key="not a cookie" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
        )

        output, caught = self.render_with_warnings(template)

        self.assertEqual(
            caught,
            ["Prop 'expandedKeysStorageKey' must be a valid cookie name; it will be ignored"],
        )
        self.assertNotIn("data-expanded-keys-storage-key", output)

    def test_button_item_passes_through_form_attributes(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" element_type="button" type="submit" form="logout-form" '
            'name="action" value="logout" %}Logout{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn("<button role=", output)
        self.assertIn('type="submit"', output)
        self.assertIn('form="logout-form"', output)
        self.assertIn('name="action"', output)
        self.assertIn('value="logout"', output)
        self.assertIn("Menubar_menubarMenuItemButton", output)

    def test_button_only_props_warn_on_anchors(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/x/" form="logout-form" %}Home{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertNotIn("logout-form", output)
        self.assertEqual(
            caught,
            [
                "Prop 'form' is only supported when 'menubar_item' renders a button element "
                "and will be ignored"
            ],
        )

    def test_class_kwargs_merge_with_default_classes(self):
        template = (
            '{% ui "menubar" aria_label="Nav" class="my-menubar" %}'
            '{% ui "menubar_item" href="/x/" class="my-item" %}Home{% endui %}'
            '{% ui "menubar_submenu" key="users" title="Users" class="my-trigger" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            '{% ui "menubar_section" class="my-section" separator_class_name="my-separator" %}'
            '{% ui "menubar_item" href="/a/" %}A{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('class="Menubar_menubar my-menubar Menubar_horizontal"', output)
        self.assertIn(
            'class="Menubar_menubarMenuItem Menubar_menubarMenuItemBase Menubar_rootMenuItem my-item"', output
        )
        self.assertIn(
            'class="Menubar_menubarMenuItem Menubar_menubarMenuItemBase Menubar_menubarMenuItemButton Menubar_hasDropdown '
            'Menubar_rootMenuItem my-trigger"',
            output,
        )
        self.assertIn('class="Menubar_section my-section"', output)
        self.assertIn('class="Menubar_separator my-separator"', output)

    def test_denied_href_omits_item(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertIn("Dashboard", output)
        self.assertNotIn("Secret", output)

    def test_submenu_with_only_denied_children_is_omitted(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href=denied %}Admin{% endui %}'
            '{% ui "menubar_item" href=denied %}Customers{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertIn("Dashboard", output)
        self.assertNotIn("Users", output)
        self.assertNotIn("data-apui-menu-submenu", output)
        self.assertNotIn("Admin", output)

    def test_section_with_only_denied_children_is_omitted(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
            '{% ui "menubar_section" title="Admin tools" %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertIn("Dashboard", output)
        self.assertNotIn("Admin tools", output)
        self.assertNotIn("Menubar_section", output)
        self.assertNotIn("Menubar_separator", output)

    def test_submenu_inside_section_prunes_both(self):
        # Mirrors the primary nav Manage menu: section > submenu > denied items
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
            '{% ui "menubar_section" %}'
            '{% ui "menubar_submenu" key="manage" title="Manage" %}'
            '{% ui "menubar_item" href=denied %}My Account{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertIn("Dashboard", output)
        self.assertNotIn("Manage", output)
        self.assertNotIn("Menubar_section", output)

    def test_empty_menubar_renders_nothing_by_default(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertEqual(output.strip(), "")

    def test_render_when_empty_renders_empty_menubar(self):
        template = (
            '{% ui "menubar" aria_label="Nav" render_when_empty=True %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertIn('role="menubar"', output)
        self.assertNotIn("<li", output)

    def test_hide_when_empty_false_renders_empty_submenu_and_section(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
            '{% ui "menubar_submenu" key="users" title="Users" hide_when_empty=False %}'
            '{% ui "menubar_item" href=denied %}Admin{% endui %}'
            "{% endui %}"
            '{% ui "menubar_section" title="Tools" hide_when_empty=False %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertIn("data-apui-menu-submenu", output)
        self.assertIn('aria-controls="apui-menu-users"', output)
        self.assertIn(
            '<ul role="menu" id="apui-menu-users" class="Menubar_menubarMenu Menubar_vertical" '
            'data-apui-menu-container="" style="--level: 1"></ul>',
            output,
        )
        self.assertIn("Menubar_section", output)
        self.assertIn("Tools", output)
        self.assertNotIn("Admin", output)
        self.assertNotIn("Secret", output)

    def test_current_item_marks_ancestors(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_section" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" is_current=True %}Admin{% endui %}'
            '{% ui "menubar_item" href="/customers/" %}Customers{% endui %}'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        # The current item gets aria-current (defaulting to "page") and data-current
        self.assertIn('data-current="true" aria-current="page" href="/admin/"', output)
        # The submenu trigger and the section li expose the current state too
        self.assertIn('aria-controls="apui-menu-users" tabindex="0" data-current="true"', output)
        self.assertIn(
            '<li role="presentation" class="Menubar_section" data-apui-menu-section="" '
            'data-level="0" data-current="true">',
            output,
        )
        # Non-current siblings are not marked
        self.assertNotIn('aria-label="Customers" tabindex="-1" data-current', output)

    def test_default_expanded_keys_renders_submenu_open(self):
        template = (
            '{% ui "menubar" aria_label="Nav" default_expanded_keys="users" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('aria-expanded="true"', output)
        self.assertIn('data-open="true"', output)
        self.assertIn("Menubar_isOpen", output)
        # Chevron points up while open (horizontal root)
        self.assertIn('d="M18 15L12 9L6 15"', output)
        # The popover renders visible (no hidden attribute) with the overlay isOpen class
        self.assertIn(
            'class="Popover_popover_bottom Popover_isOpen" role="presentation" data-apui-menu-popover=""',
            output,
        )
        self.assertNotIn(" hidden ", output)

    def test_separator_renders_between_sections_only(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_section" aria_label="First" %}'
            '{% ui "menubar_item" href="/a/" %}A{% endui %}'
            "{% endui %}"
            '{% ui "menubar_section" aria_label="Second" %}'
            '{% ui "menubar_item" href="/b/" %}B{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertEqual(output.count('role="separator"'), 1)
        # Horizontal root separators are vertical dividers
        self.assertIn(
            '<li role="separator" aria-orientation="vertical" class="Menubar_separator" '
            'data-apui-menu-separator="" data-level="0">',
            output,
        )
        # The separator belongs to the second section (renders before its li)
        first_index = output.index('aria-label="First"')
        separator_index = output.index('role="separator"')
        self.assertGreater(separator_index, first_index)

    def test_pruned_first_section_does_not_leave_leading_separator(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_section" aria_label="First" %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
            '{% ui "menubar_section" aria_label="Second" %}'
            '{% ui "menubar_item" href="/b/" %}B{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertNotIn('role="separator"', output)
        self.assertIn('aria-label="Second"', output)

    def test_section_title_renders_heading_and_labels_group(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="inline" %}'
            '{% ui "menubar_section" title="Tools" %}'
            '{% ui "menubar_item" href="/a/" %}A{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn(
            '<div class="Menubar_sectionHeading" id="apui-menubar-1" role="presentation" '
            'data-apui-menu-section-heading="" data-level="0">'
            '<span class="Menubar_sectionHeadingText" data-apui-slot="label">Tools</span></div>',
            output,
        )
        self.assertIn(
            '<ul role="group" aria-labelledby="apui-menubar-1" '
            'data-apui-menu-section-items="" data-level="0">',
            output,
        )
        self.assertIn('data-apui-menu-section="" data-level="0"', output)

    def test_unknown_props_warn_and_are_dropped(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/x/" unknown_attr="boom" %}Home{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertNotIn("boom", output)
        self.assertEqual(
            caught,
            ["Prop 'unknownAttr' is not a supported 'menubar_item' prop and will be ignored"],
        )

    def test_event_handler_props_warn_and_never_render(self):
        template = (
            '{% ui "menubar" aria_label="Nav" on_action="alert(1)" %}'
            '{% ui "menubar_item" href="/x/" on_click="alert(1)" %}Home{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertNotIn("alert(1)", output)
        self.assertEqual(
            caught,
            [
                "Prop 'onAction' will be ignored: client-side action callbacks are not supported "
                "by static menubar components",
                "Prop 'onClick' will be ignored: event handlers are not supported by static "
                "menubar components",
            ],
        )

    def test_selection_and_collection_props_warn(self):
        template = (
            '{% ui "menubar" aria_label="Nav" selection_mode="multiple" items=items %}'
            '{% ui "menubar_item" href="/x/" %}Home{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"items": [1, 2]})
        self.assertNotIn("selection", output.replace("data-", ""))
        self.assertCountEqual(
            caught,
            [
                "Prop 'selectionMode' will be ignored: selection is not supported by static "
                "menubar components yet",
                "Prop 'items' will be ignored: collection render props are not supported by "
                "static menubar components",
            ],
        )

    def test_rich_item_content_without_text_value_warns(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/x/" %}<b>Bold</b> label{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(
            caught,
            ["'menubar_item' has non-plain-text content; pass 'text_value' so it has an accessible label"],
        )
        # Best-effort derived label from the stripped text
        self.assertIn('aria-label="Bold label"', output)
        # Rich content is not re-wrapped in a span
        self.assertIn("<b>Bold</b> label", output)

    def test_rich_item_content_with_text_value_does_not_warn(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/x/" text_value="Bold label" %}<b>Bold</b> label{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('aria-label="Bold label"', output)

    def test_submenu_without_title_warns_and_renders_nothing(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/x/" %}Home{% endui %}'
            '{% ui "menubar_submenu" %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertNotIn("Admin", output)
        self.assertEqual(
            caught,
            ["'menubar_submenu' requires a 'title' prop; the submenu will not be rendered"],
        )

    def test_menubar_without_label_warns(self):
        template = '{% ui "menubar" %}{% ui "menubar_item" href="/x/" %}Home{% endui %}{% endui %}'
        output, caught = self.render_with_warnings(template)
        self.assertIn('role="menubar"', output)
        self.assertEqual(
            caught,
            [
                "The 'menubar' component should have an 'aria_label' or 'aria_labelledby' prop "
                "for accessibility"
            ],
        )

    def test_disabled_anchor_item_renders_as_div(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href="/x/" is_disabled=True %}Home{% endui %}'
            '{% ui "menubar_item" element_type="button" is_disabled=True %}Logout{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        # Disabled anchors become divs with no href, matching React
        self.assertIn(
            '<div role="menuitem" class="Menubar_menubarMenuItem Menubar_menubarMenuItemBase Menubar_disabled Menubar_rootMenuItem" '
            'data-level="0" data-disabled="true" aria-disabled="true" aria-label="Home" tabindex="-1">',
            output,
        )
        self.assertNotIn('href="/x/"', output)
        # Disabled buttons keep the button element with aria-disabled (no native disabled attr,
        # matching the React output; the runtime blocks activation)
        self.assertIn("<button role=", output)
        self.assertNotIn("<button role=" + '"menuitem" disabled', output)
        # Disabled items never claim the roving tab stop
        self.assertNotIn('tabindex="0"', output)

    def test_disabled_submenu_renders_closed_even_when_default_expanded(self):
        template = (
            '{% ui "menubar" aria_label="Nav" default_expanded_keys="users" %}'
            '{% ui "menubar_submenu" key="users" title="Users" is_disabled=True %}'
            '{% ui "menubar_item" href="/admin/" %}Admin{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('aria-expanded="false"', output)
        self.assertIn('data-disabled="true"', output)
        self.assertIn(" hidden ", output)

    def test_data_attributes_pass_through(self):
        template = (
            '{% ui "menubar" aria_label="Nav" data_testid="primary-nav" %}'
            '{% ui "menubar_item" href="/x/" data_testid="home-link" %}Home{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)
        self.assertEqual(caught, [])
        self.assertIn('data-testid="primary-nav"', output)
        self.assertIn('data-testid="home-link"', output)

    def test_item_outside_menubar_warns_and_renders_nothing(self):
        template = '{% ui "menubar_item" href="/x/" %}Home{% endui %}'
        output, caught = self.render_with_warnings(template)
        self.assertEqual(output, "")
        self.assertEqual(
            caught,
            ["'menubar_item' was rendered outside of a '{% ui \"menubar\" %}' component; rendering nothing"],
        )

    def test_included_section_and_items_keep_enclosing_menubar_context(self):
        with self.setup_render_context():
            partial = Template(
                "{% load alliance_platform.ui %}"
                '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
                '{% ui "menubar_section" title="Account" %}'
                '{% ui "menubar_item" href="/profile/" %}Profile{% endui %}'
                "{% endui %}"
            )
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(
                    '{% ui "menubar" aria_label="Nav" %}{% include nav_items only %}{% endui %}',
                    {"nav_items": partial},
                )

        self.assertEqual([str(item.message) for item in caught_warnings], [])
        self.assertIn("Menubar_section", output)
        self.assertIn('href="/dashboard/"', output)
        self.assertIn('href="/profile/"', output)
        self.assertIn('aria-label="Dashboard" tabindex="0"', output)

    def test_repeated_included_menubars_generate_document_unique_heading_ids(self):
        with self.setup_render_context():
            partial = Template(
                "{% load alliance_platform.ui %}"
                '{% ui "menubar" aria_label="Nav" %}'
                '{% ui "menubar_section" title="Account" %}'
                '{% ui "menubar_submenu" key="manage" title="Manage" %}'
                '{% ui "menubar_item" href="/profile/" %}Profile{% endui %}'
                "{% endui %}"
                "{% endui %}"
                "{% endui %}"
            )
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(
                    "{% include navbar %}{% include navbar %}",
                    {"navbar": partial},
                )

        self.assertEqual([str(item.message) for item in caught_warnings], [])
        heading_ids = re.findall(r'id="(apui-menubar-\d+)"', output)
        self.assertEqual(heading_ids, ["apui-menubar-1", "apui-menubar-2"])
        self.assertEqual(
            re.findall(r'aria-labelledby="(apui-menubar-\d+)"', output),
            heading_ids,
        )
        popup_ids = re.findall(r'id="(apui-menu-manage(?:-\d+)?)"', output)
        self.assertEqual(popup_ids, ["apui-menu-manage", "apui-menu-manage-2"])
        self.assertEqual(
            re.findall(r'aria-controls="(apui-menu-manage(?:-\d+)?)"', output),
            popup_ids,
        )

    def test_section_supports_explicit_heading_id(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_section" title="Account" heading_id="account-heading" %}'
            '{% ui "menubar_item" href="/profile/" %}Profile{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)

        self.assertEqual(caught, [])
        self.assertIn('id="account-heading"', output)
        self.assertIn('aria-labelledby="account-heading"', output)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template(BASIC_MENUBAR_TEMPLATE)
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]
        for expected in (
            "@alliancesoftware/ui/components/menu-bar/Menubar.css.ts",
            "@alliancesoftware/ui/components/overlay/Popover.css.ts",
            "@alliancesoftware/icons/Icon.css.ts",
            "static-svg/outlined/ChevronDownOutlined.svg",
            "static-svg/outlined/ChevronRightOutlined.svg",
            "static-svg/outlined/ChevronUpOutlined.svg",
            "@alliancesoftware/ui/components/menu-bar/Menubar.auto.ts",
        ):
            self.assertTrue(
                any(path.endswith(expected) for path in resource_paths),
                f"{expected} not found in {resource_paths}",
            )

    def test_collected_assets_document_does_not_embed_chevron_images(self):
        with self.setup_render_context():
            output = self.render_ui_document(BASIC_MENUBAR_TEMPLATE)

        self.assertEqual(output.count("<svg"), 1)
        self.assertNotIn("<img", output)
        self.assertIn("Menubar.auto.ts", output)
        self.assertIn("<script src=", output)
        self.assertIn("Menubar_menubar", output)

    def test_collected_auto_attach_runtime_is_deduplicated_for_multiple_menubars(self):
        with self.setup_render_context():
            output = self.render_ui_document(BASIC_MENUBAR_TEMPLATE + BASIC_MENUBAR_TEMPLATE)

        self.assertEqual(output.count("Menubar.auto.ts"), 1)
        self.assertEqual(output.count('data-apui-attach="menubar"'), 2)
        self.assertNotIn('<script type="module">', output)

    def test_collected_assets_document_with_explicit_icon_has_only_inline_svgs(self):
        template = (
            '{% ui "menubar" aria_label="Primary navigation" %}'
            '{% ui "menubar_item" href="/settings/" text_value="Settings" %}'
            '{% ui "icon" name="Pencil01Outlined" %}{% endui %}'
            "Settings"
            "{% endui %}"
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/users/" %}Users{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        with self.setup_render_context():
            output = self.render_ui_document(template)

        self.assertEqual(output.count("<svg"), 2)
        self.assertNotIn("<img", output)
        self.assertIn(
            'class="Icon_icon Icon_variants_plain Icon_sizes_xs Menubar_itemIcon"',
            output,
        )
        self.assertIn(
            '<div data-apui-menu-item-content-wrapper="">'
            '<span class="Menubar_menubarMenuItemContent" data-contentlevel="0" '
            'data-apui-menu-item-content=""><span role="img"',
            output,
        )
        self.assertIn('</span><span data-apui-slot="label">Settings</span>', output)
        self.assertIn('data-has-leading-icon="true"', output)
        self.assertIn("Menubar_hasLeadingIcon", output)
        self.assertIn("Menubar.auto.ts", output)

    def test_icon_only_root_items_keep_accessible_labels_and_render_visual_tooltips(self):
        template = (
            '{% ui "menubar" aria_label="Nav" layout="vertical" root_item_display="icon-only" %}'
            '{% ui "menubar_item" href="/dashboard/" text_value="Dashboard" %}'
            '{% ui "icon" name="Pencil01Outlined" %}{% endui %}Dashboard'
            "{% endui %}"
            '{% ui "menubar_item" href="/help/" %}Help{% endui %}'
            '{% ui "menubar_submenu" key="admin" title="Administration" icon="Pencil01Outlined" %}'
            '{% ui "menubar_item" href="/users/" text_value="Users" %}'
            '{% ui "icon" name="Pencil01Outlined" %}{% endui %}Users'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )

        output, caught = self.render_with_warnings(template)

        self.assertEqual(caught, [])
        self.assertIn('data-root-item-display="icon-only"', output)
        self.assertIn('aria-label="Dashboard"', output)
        self.assertIn('aria-label="Help"', output)
        self.assertIn('aria-label="Administration"', output)
        self.assertIn('aria-label="Users"', output)
        help_tag = re.search(r'<a\b[^>]*href="/help/"[^>]*>', output)
        self.assertIsNotNone(help_tag)
        assert help_tag is not None
        self.assertNotIn("data-has-leading-icon", help_tag.group(0))
        self.assertIn('<span data-apui-slot="label">Help</span>', output)
        self.assertEqual(output.count('data-apui-menu-item-tooltip=""'), 2)
        self.assertIn(
            '<span data-apui-menu-item-tooltip="" aria-hidden="true">Dashboard</span>',
            output,
        )
        self.assertIn(
            '<span data-apui-menu-item-tooltip="" aria-hidden="true">Administration</span>',
            output,
        )
        self.assertNotIn(
            '<span data-apui-menu-item-tooltip="" aria-hidden="true">Users</span>',
            output,
        )
        # Root and submenu aggregates plus each of the three icon-bearing item elements.
        self.assertEqual(output.count('data-has-leading-icon="true"'), 5)

    def test_invalid_root_item_display_warns_and_falls_back(self):
        template = (
            '{% ui "menubar" aria_label="Nav" root_item_display="labels-only" %}'
            '{% ui "menubar_item" href="/help/" %}Help{% endui %}'
            "{% endui %}"
        )

        output, caught = self.render_with_warnings(template)

        self.assertIn('data-root-item-display="icon-and-label"', output)
        self.assertEqual(caught, ["Invalid 'rootItemDisplay' prop passed: labels-only"])

    def test_submenu_popup_tracks_leading_icons(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_submenu" key="users" title="Users" %}'
            '{% ui "menubar_item" href="/profile/" text_value="Profile" %}'
            '{% ui "icon" name="Pencil01Outlined" %}{% endui %}Profile'
            "{% endui %}"
            "{% endui %}"
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)

        self.assertEqual(caught, [])
        self.assertIn(
            'class="Menubar_menubarMenu Menubar_vertical Menubar_hasLeadingIcon"',
            output,
        )
        self.assertIn('data-has-leading-icon="true"', output)

    def test_icon_props_render_safe_submenu_and_section_titles(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_submenu" key="manage" title="Manage" icon="Pencil01Outlined" %}'
            '{% ui "menubar_item" href="/profile/" %}Profile{% endui %}'
            "{% endui %}"
            '{% ui "menubar_section" title="Account" icon="AlertCircleOutlined" %}'
            '{% ui "menubar_item" href="/logout/" %}Logout{% endui %}'
            "{% endui %}"
            "{% endui %}"
        )
        with self.setup_render_context() as asset_context:
            output = self.render_ui_document(template)
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertNotIn("<img", output)
        self.assertIn("Menubar_itemIcon", output)
        self.assertIn("Menubar_sectionHeadingIcon", output)
        self.assertIn("Menubar_sectionHeadingText", output)
        self.assertIn('</span><span data-apui-slot="label">Manage</span>', output)
        self.assertIn(
            'class="Icon_icon Icon_variants_plain Icon_sizes_xs Menubar_sectionHeadingIcon"', output
        )
        self.assertIn('data-apui-slot="icon"', output)
        for icon_name in ("Pencil01Outlined.svg", "AlertCircleOutlined.svg"):
            self.assertTrue(any(path.endswith(icon_name) for path in resource_paths))

    def test_icon_props_must_be_static(self):
        with self.setup_render_context():
            with self.assertRaisesMessage(TemplateSyntaxError, "static string literal"):
                self.render_ui_template(
                    '{% ui "menubar_submenu" title="Manage" icon=icon_name %}'
                    '{% ui "menubar_item" %}Profile{% endui %}'
                    "{% endui %}",
                    {"icon_name": "Pencil01Outlined"},
                )

    def test_collected_assets_document_in_production_keeps_chevrons_build_only(self):
        manifest: dict[str, dict[str, object]] = {}
        style_paths = (
            "@alliancesoftware/ui/components/menu-bar/Menubar.css.ts",
            "@alliancesoftware/ui/components/overlay/Popover.css.ts",
            "@alliancesoftware/icons/Icon.css.ts",
        )
        runtime_path = "@alliancesoftware/ui/components/menu-bar/Menubar.auto.ts"

        with TemporaryDirectory() as temp_dir:
            build_dir = Path(temp_dir)
            assets_dir = build_dir / "assets"
            assets_dir.mkdir(parents=True)
            for style_path in style_paths:
                style_name = Path(style_path).name.removesuffix(".css.ts")
                manifest[style_path] = {
                    "file": f"assets/{style_name}-built.js",
                    "src": style_path,
                    "css": [f"assets/{style_name}-built.css"],
                }
            manifest[runtime_path] = {
                "file": "assets/Menubar.auto-built.js",
                "src": runtime_path,
            }

            for icon_name in (
                "ChevronDownOutlined",
                "ChevronRightOutlined",
                "ChevronUpOutlined",
            ):
                icon_source = (
                    Path(__file__).resolve().parent / f"fixtures/icons/static-svg/outlined/{icon_name}.svg"
                )
                icon_manifest_path = str(icon_source.relative_to(settings.PROJECT_DIR))
                built_icon_path = assets_dir / f"{icon_name}-built.svg"
                built_icon_path.write_text(icon_source.read_text())
                manifest[icon_manifest_path] = {
                    "file": f"assets/{built_icon_path.name}",
                    "src": icon_manifest_path,
                }

            (build_dir / "manifest.json").write_text(json.dumps(manifest))
            production_bundler = TestViteBundler(
                **{**bundler_kwargs, "build_dir": build_dir, "mode": "production"}
            )

            with override_ap_frontend_settings(BUNDLER=production_bundler):
                with BundlerAssetContext(
                    skip_checks=True,
                    frontend_resource_registry=bypass_frontend_resource_registry,
                ) as asset_context:
                    with mock.patch(
                        "alliance_platform.ui.templatetags.alliance_platform.html_components.base.resolve_vanilla_extract_class_mapping",
                        side_effect=make_style_mapping_resolver(),
                    ):
                        output = self.render_ui_document(BASIC_MENUBAR_TEMPLATE)
                    resource_paths = [
                        str(resource.path) for resource in asset_context.get_resources_for_bundling()
                    ]

        self.assertEqual(output.count("<svg"), 1)
        self.assertNotIn("<img", output)
        self.assertIn("/static/assets/Menubar.auto-built.js", output)
        self.assertIn("/static/assets/Menubar-built.css", output)
        for icon_name in (
            "ChevronDownOutlined.svg",
            "ChevronRightOutlined.svg",
            "ChevronUpOutlined.svg",
        ):
            self.assertTrue(any(path.endswith(icon_name) for path in resource_paths))

    def test_resource_discovery_does_not_require_asset_context(self):
        # The dispatcher resolves resources through renderers created with register_asset=False;
        # this must work without an active BundlerAssetContext (e.g. during extract-assets).
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            renderer = UIMenubarRenderer(
                props={},
                nodelist=NodeList(),
                origin=None,
                target_var=None,
                register_asset=False,
            )
            resource_paths = [str(resource.path) for resource in renderer.get_resources_for_bundling()]
        self.assertEqual(len(resource_paths), 7)
        self.assertTrue(any("Menubar.auto" in path for path in resource_paths))
        self.assertTrue(any("ChevronDownOutlined.svg" in path for path in resource_paths))

    def test_missing_runtime_resource_is_an_incompatible_ui_version_error(self):
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            renderer = UIMenubarRenderer(
                props={},
                nodelist=NodeList(),
                origin=None,
                target_var=None,
                register_asset=False,
            )
            resolve_frontend_resource = renderer.resolve_frontend_resource

            def resolve_with_missing_runtime(path, resolve_extensions=None):
                if path.endswith("Menubar.auto.ts"):
                    raise TemplateSyntaxError("module not found")
                return resolve_frontend_resource(path, resolve_extensions)

            with mock.patch.object(
                renderer,
                "resolve_frontend_resource",
                side_effect=resolve_with_missing_runtime,
            ):
                with self.assertRaisesMessage(
                    TemplateSyntaxError,
                    "Upgrade @alliancesoftware/ui to a compatible version",
                ):
                    renderer.get_resources_for_bundling()

    def test_runtime_marks_rendered_root_for_external_auto_attachment(self):
        with self.setup_render_context():
            output = self.render_ui_template(BASIC_MENUBAR_TEMPLATE)
        self.assertIn('data-apui-attach="menubar"', output)
        self.assertNotIn("data-djid", output)
        self.assertNotIn("<script", output)

    def test_runtime_layout_contract_uses_one_mutable_menu_tree(self):
        with self.setup_render_context():
            output = self.render_ui_template(BASIC_MENUBAR_TEMPLATE)

        self.assertEqual(output.count('data-apui="menubar"'), 1)
        self.assertEqual(output.count('id="apui-menu-users"'), 1)
        self.assertEqual(output.count('data-apui-menu-submenu=""'), 1)
        self.assertIn('data-layout="horizontal"', output)
        self.assertIn('data-orientation="horizontal"', output)
        self.assertIn('aria-orientation="horizontal"', output)
        self.assertIn('data-apui-attach="menubar"', output)

    def test_no_script_rendered_for_empty_menubar(self):
        template = (
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_item" href=denied %}Secret{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template, {"denied": DeniedUrl()})
        self.assertEqual(caught, [])
        self.assertNotIn("<script", output)

    def test_rerendering_shared_template_does_not_leak_state(self):
        with self.setup_render_context():
            template_obj = Template(
                "{% load alliance_platform.ui %}"
                '{% ui "menubar" aria_label="Nav" %}'
                '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
                '{% ui "menubar_submenu" key="users" title="Users" %}'
                '{% ui "menubar_item" href=maybe_denied %}Admin{% endui %}'
                "{% endui %}"
                "{% endui %}"
            )

            def render(**context_kwargs):
                context = Context(context_kwargs)
                context.template = template_obj
                return template_obj.render(context)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                denied_output = render(maybe_denied=DeniedUrl())
                allowed_output = render(maybe_denied="/admin/")
                denied_again = render(maybe_denied=DeniedUrl())
        self.assertEqual([str(item.message) for item in caught_warnings], [])

        self.assertNotIn("Users", denied_output)
        self.assertIn("Users", allowed_output)
        self.assertIn('href="/admin/"', allowed_output)
        self.assertNotIn("Users", denied_again)
        # The roving tab stop is re-assigned per render rather than accumulating
        for output in (denied_output, allowed_output, denied_again):
            self.assertEqual(output.count('tabindex="0"'), 1)


@override_ap_frontend_settings(DEBUG_COMPONENT_OUTPUT=False)
@override_settings(
    AUTHENTICATION_BACKENDS=("rules.permissions.ObjectPermissionBackend",),
    ROOT_URLCONF="test_alliance_platform_ui.urls",
)
@warning_filter("ignore", category=AmbiguousGlobalPermissionWarning)
class UIMenubarUrlWithPermTestCase(TestCase):
    """End-to-end permission pruning through the real ``url_with_perm`` filter."""

    PERM = "test_utils.link_is_allowed"
    GLOBAL_PERM_URL = "url_with_perm_global"

    NAV_TEMPLATE = (
        "{% load alliance_platform.ui %}"
        '{% ui "menubar" aria_label="Nav" %}'
        '{% ui "menubar_item" href="/dashboard/" %}Dashboard{% endui %}'
        '{% ui "menubar_submenu" key="users" title="Users" %}'
        '{% ui "menubar_item" href=perm_url|url_with_perm %}Admin{% endui %}'
        "{% endui %}"
        "{% endui %}"
    )

    @contextmanager
    def setup_render_context(self):
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True,
                frontend_resource_registry=bypass_frontend_resource_registry,
            ):
                with mock.patch(
                    "alliance_platform.ui.templatetags.alliance_platform.html_components.base.resolve_vanilla_extract_class_mapping",
                    side_effect=make_style_mapping_resolver(),
                ):
                    yield

    def render_nav(self, template_obj: Template, user: User) -> str:
        request = HttpRequest()
        request.user = user
        request.session = SessionBase()
        context = Context({"request": request, "perm_url": self.GLOBAL_PERM_URL})
        context.template = template_obj
        return template_obj.render(context)

    def test_denied_url_with_perm_prunes_item_and_empty_submenu(self):
        privileged = cast(User, UserFactory(is_superuser=True))
        unprivileged = cast(User, UserFactory(is_superuser=False))
        self.assertTrue(privileged.has_perm(self.PERM))
        self.assertFalse(privileged is unprivileged)

        with self.setup_render_context():
            template_obj = Template(self.NAV_TEMPLATE)
            allowed_output = self.render_nav(template_obj, privileged)
            denied_output = self.render_nav(template_obj, unprivileged)
            # Re-render for the privileged user with the same compiled template to confirm the
            # denied render did not leak state
            allowed_again = self.render_nav(template_obj, privileged)

        self.assertIn("Users", allowed_output)
        self.assertIn("Admin", allowed_output)
        self.assertIn("Dashboard", denied_output)
        self.assertNotIn("Users", denied_output)
        self.assertNotIn("Admin", denied_output)
        self.assertIn("Admin", allowed_again)
