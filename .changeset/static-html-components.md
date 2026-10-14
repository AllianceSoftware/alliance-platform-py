---
"alliance-platform-frontend": patch
"alliance-platform-ui": patch
---

Add the `{% ui %}` template tag, which renders Alliance UI components as static HTML with no React on
the page: icons, buttons and button groups, text, number and text area inputs, labeled inputs, inline
alerts, menubars, pagination, tables, and the content, heading, header and footer layout parts.
Components take snake_case props, the leaf components take no end tag, and the React tags remain for
everything the static components do not cover. The
[`{% ui %}` reference](https://alliance-platform.readthedocs.io/projects/ui/latest/templatetags.html#ui)
documents every component and its props, and
[Writing a static component](https://alliance-platform.readthedocs.io/projects/ui/latest/static_components.html)
covers adding your own.

-   Forms: the opt-in
    [`StaticFormRenderer`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#static-form-widgets)
    renders Django's text, number and text area widgets with the static components, and
    `{% ui "labeled_input" %}` wraps any other control in the inputs' label, help text and error
    message. Form help text and errors marked safe keep their HTML in both the React and static
    widgets.
-   The `alliance_platform.ui` template library now provides the `merge_props` and `none_as_nan`
    filters.
-   Template mistakes are logged to the `alliance_platform.ui` logger; the
    [`STATIC_COMPONENT_STRICT`](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#settings)
    setting, which defaults to `DEBUG`, raises them instead.
-   Requires builds of `@alliancesoftware/ui` and `@alliancesoftware/icons` that ship a
    `static-contract.json`. A
    [system check](https://alliance-platform.readthedocs.io/projects/ui/latest/installation.html#system-checks)
    reports an installed version the renderers do not support, and `extract_frontend_resources` now
    runs the system checks tagged `alliance_platform_frontend_build` and fails the build on an error.
