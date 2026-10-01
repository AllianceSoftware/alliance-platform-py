Writing a static component
**************************

The :ttag:`ui` tag renders components from a registry of Python renderers. Each renderer turns a
tag's props and children into HTML on the server, with no React. Projects can add their own
renderers next to the built-ins and use them exactly like ``{% ui "button" %}``.

This page builds one example component. Its code is the renderer ap-ui's own test project
registers and tests, so what you read here is what the tests run.

Where renderers live
--------------------

A renderer is a subclass of
``alliance_platform.ui.html_components.base.BaseHtmlUIComponentRenderer``. Put your renderers in a
module of the app that owns them, for example ``myapp/static_components.py``, and register them
from that app's ``AppConfig``. Helper modules sit next to the base class:

* ``alliance_platform.ui.html_components.render_context``: render frames, typed payloads, child
  reports and document-unique ids.
* ``alliance_platform.ui.html_components.slots``: slot defaults for child components.
* ``alliance_platform.ui.html_components.content``: rendering rich content props
  (``RenderableContent``) safely.
* ``alliance_platform.ui.html_components.runtime``: marking a root for a JavaScript runtime.

The built-in renderers in ``alliance_platform.ui.html_components.components`` are complete
examples of every feature described here.

The example: a ``stat`` component
---------------------------------

``{% ui "stat" %}`` shows a labelled figure. The figure is a separate ``stat_value`` part that can
sit anywhere inside the stat, and an icon placed in the stat picks up the stat's icon styling:

.. code-block:: html+django

    {% load alliance_platform.ui %}

    {% ui "stat" label="Open jobs" size="lg" %}
      {% ui "icon" name="CheckCircleOutlined" %}{% endui %}
      {% ui "stat_value" %}{{ open_jobs }}{% endui %}
    {% endui %}

which renders (whitespace and the SVG trimmed, class names depend on your stylesheet):

.. code-block:: html

    <div data-apui="stat" data-size="lg" class="stat">
      <span class="stat-label">Open jobs</span>
      <span role="img" aria-hidden="true" data-apui-slot="icon" class="icon icon-plain icon-sm stat-icon">…</span>
      <span data-apui="stat-value" class="stat-value-lg">42</span>
    </div>

The stylesheet, ``frontend/src/components/Stat.css.ts``, is an ordinary vanilla-extract file that
exports ``stat``, ``label`` and ``icon`` styles and a ``value`` style variant for each size.

The renderers use the three ways components cooperate:

* a **frame with a typed payload** passes the stat's size down to ``stat_value``, however deeply it
  is nested;
* a **slot default** sizes and styles a child ``icon`` the stat does not render itself;
* a **child report** tells the stat whether a value rendered, so it can mark itself empty.

.. literalinclude:: ../test_alliance_platform_ui/static_components.py
    :language: python
    :start-at: from dataclasses import dataclass

The sections below explain each piece.

Registering a component
-----------------------

Register renderers with ``register_component(name, renderer_cls, *, replace=False)`` from your
app's ``AppConfig.ready()``:

.. literalinclude:: ../test_alliance_platform_ui/apps.py
    :language: python

* ``name`` is the snake_case name templates use (``^[a-z][a-z0-9_]*$``) and must equal the
  renderer's ``name`` attribute, so warnings, generated ids and the registry agree.
* Registering a different renderer under a taken name, including a built-in name, raises
  ``ValueError``. Pass ``replace=True`` to replace it deliberately. Registering the same renderer
  again does nothing, so a ``ready()`` that runs twice is harmless.

Registration must happen while Django loads apps, before any template compiles. ``{% ui %}``
looks components up when a template is compiled, not when it renders: an unknown component name,
or an unknown ``allowed_components`` entry, raises ``TemplateSyntaxError``, and a literal component
name compiles to an instance of the renderer registered at that moment. Compiled templates are
cached, so a later ``replace=True`` does not change templates that already compiled. ``ready()``
runs in every process, including management commands such as
:djmanage:`extract_frontend_resources <alliance-platform-frontend:extract_frontend_resources>`,
which compiles every template to find the files to build.

Contract attributes
-------------------

Class attributes declare what a component accepts. Before a renderer sees its props, the base
class normalizes template spellings (``label_position`` becomes ``labelPosition``, ``class``
becomes ``className``, ``data_x`` becomes ``data-x``), so contract attributes use the React prop
names. Props the contract does not accept warn and are dropped. Event handler props (``on*``) are
always dropped.

``name``
    The registered snake_case name.
``apui_name``
    The value of the root ``data-apui`` marker and the prefix of generated ids
    (``apui-<apui_name>-1``). Defaults to ``name`` with hyphens, so the example's value part is
    marked ``data-apui="stat-value"``. Set it to keep an existing marker, for example in a
    subclass with a new name.
``slot_name``
    The slot this component reads parent-provided defaults from (see `Slot defaults`_).
``supported_props``
    The accepted prop names. ``None`` leaves filtering to the renderer.
``prop_rules``
    Validation for supplied values, built with ``enum_prop_rule(values, invalid_fallback=...)`` or
    ``typed_prop_rule(*types, validator=..., invalid_fallback=..., allow_none=...)``. An invalid
    value warns and is replaced by the fallback, or dropped when there is none. A prop with a
    rule is accepted even if it is not in ``supported_props``.
``prop_aliases`` and ``deprecated_prop_aliases``
    Alternative names mapped to the canonical prop name. Deprecated aliases also warn. When both
    spellings are passed, the canonical one wins.
``unsupported_prop_reasons``
    Props that are refused with a specific explanation, typically React-only behaviour.
``forwarded_props``
    Plain attributes, such as ``id`` and ``title``, that ``collect_forwarded_props()`` copies to
    the root element. They count as supported.
``allow_data_props``, ``allow_aria_props`` and ``extra_allowed_aria_props``
    Whether arbitrary ``data-*`` and ``aria-*`` attributes are accepted, and which ``aria-*`` names
    are accepted when arbitrary ones are not.
``non_scalar_props``
    Props that may hold lists, dicts or other objects. Other props must be scalars unless a prop
    rule validates them.
``none_meaningful_props``
    Props where an explicit ``None`` is kept. Elsewhere ``None`` means the prop was not passed.
``prop_filter_context`` and ``event_handler_prop_reason``
    Wording used in the warnings above.

Hooks
-----

``BaseHtmlUIComponentRenderer.render()`` runs the same steps for every component: resolve and
normalize the props, merge slot defaults, apply the contract, push the component's frame, render
the children, render the component and publish its child report. A prop that raises
``OmitComponentFromRendering``, such as a denied ``url_with_perm`` link, makes the component render
nothing. Override these hooks:

``render_component(context, props, children_html)``
    Required. Return the component's HTML, or ``""`` to render nothing. ``children_html`` is
    already rendered and safe. Build elements with ``render_tag(tag_name, attrs, children_html)``,
    which escapes attribute values and omits ``None`` and ``False``.
``render_children_for_component(context, props)``
    Renders the children before ``render_component`` runs. The default is
    ``render_children(context)``. Override it to set slot defaults or collect child reports, as
    the stat does. Return ``""`` and call ``render_children()`` from ``render_component`` instead
    when the children need state the component sets up first.
``build_render_frame(context, props)``
    Returns the frame pushed while the children and the component render. The default carries only
    the component name. Override it to attach a payload.
``build_child_report(context, props, rendered)``
    Returns a ``ChildReport`` for a parent that collects them, or ``None``.
``resolve_component_resources()``
    Returns the files the component needs (see `Resources`_).
``get_resources_to_embed()``
    Returns the subset of those resources to add to the page. Defaults to all of them.

``resolve_props(context)`` can also be overridden, for example to refuse to render outside a
required parent. Helpers to call from hooks include ``render_children``, ``render_tag``,
``render_icon``, ``collect_forwarded_props``, ``join_classes``, ``resolve_frontend_resource``,
``resolve_vanilla_extract_mapping`` and the style getters ``get_style_class``,
``get_nested_style_class`` and ``get_recipe_classes``. Names starting with an underscore are
internal.

Frames and typed payloads
-------------------------

Every component renders inside a ``RenderFrame`` on a stack shared by the whole document render.
The stack survives ``{% include %}``, including ``{% include ... only %}``, which plain template
variables do not. A frame can carry a payload: any object, usually a dataclass, that components
rendered inside it look up by type with ``find_render_payload(context, PayloadType)``. The nearest
payload of that type wins, so the same component can nest inside itself.

The stat attaches ``StatPayload`` in ``build_render_frame`` and ``stat_value`` reads it to pick
its size class. When no stat encloses the value, ``find_render_payload`` returns ``None`` and the
value warns and renders nothing.

Renderer instances are template nodes shared by every render of a compiled template, possibly on
several threads at once. Keep per-render state in payloads, never on ``self``. Payloads may be
mutable: the built-in table counts rendered rows in its payload to decide whether to show its
empty state. ``generate_html_id(context, prefix)`` and ``claim_html_id(context, preferred_id)`` in
the same module return ids that are unique within the document.

Slot defaults
-------------

A parent sets defaults for components it does not render itself by passing ``slot_overrides`` to
``render_children``. Each key is a slot name and each value is a dict of props. A component inside
the parent whose ``slot_name`` matches, or that passes ``slot="<name>"`` explicitly, merges the
defaults under its own props: props passed in the template win and ``className`` values are
joined. Defaults use the normalized prop names (``className``, ``isDisabled``). The stat gives
icons a size and a class, and an icon's own ``size`` overrides the default.

Slot defaults reach every component inside the parent until another component replaces the scope;
``content`` resets it with ``replace_slot_scope(context, {})`` so its children start clean. The
built-in slot names are ``icon``, ``button``, ``buttonGroup``, ``content``, ``heading``,
``header``, ``footer`` and ``pagination``.

Child reports
-------------

A child report is a fact a component publishes to its parent after it renders. The parent opts in
by rendering its children inside ``with collect_child_reports(context):``. Each child component
that renders non-empty output then adds the ``ChildReport`` from its ``build_child_report`` to
the parent's frame, and the parent reads them in ``render_component`` from
``get_current_component_frame(context).child_reports``.

Reports go to the nearest enclosing component only. A ``stat_value`` wrapped in a
``{% ui "content" %}`` reports to the content component, which does not collect, so the stat
does not see it even though the payload still reaches the value. Components rendered with
``as <var>``, omitted, or rendering an empty string do not report. The built-in ``icon`` reports
``ChildReport(component="icon", slot=..., html=...)``, which ``button`` and ``menubar_item`` use,
together with ``find_leading_child_report()``, to detect icon-only and leading-icon content.

Resources
---------

``resolve_component_resources()`` lists the frontend files a component needs: stylesheets,
JavaScript runtimes and static icon SVGs.
:djmanage:`extract_frontend_resources <alliance-platform-frontend:extract_frontend_resources>`
includes them in production builds, and rendering a component adds them to the page through
``{% bundler_embed_collected_assets %}``. Resources are resolved at build time without a request
or context, so they may only depend on static props (``self.props`` holds the unresolved template
expressions).

``resolve_frontend_resource(path)`` resolves a path through the bundler the same way the
:ttag:`component <alliance-platform-frontend:component>` tag does, and
``resolve_vanilla_extract_mapping(path)`` returns the class names a ``.css.ts`` file exports. Read
them with ``get_style_class(mapping, "label")``, ``get_nested_style_class(mapping, "value", size)``
for style variants and ``get_recipe_classes`` for recipes. A missing class resolves to ``""``.

Components that inline icons with ``render_icon()`` should list each icon with
``alliance_platform.ui.icons.get_static_icon_resource(name, origin=self.origin)`` so the SVG is
built, and leave the image out of ``get_resources_to_embed()`` because its markup is already in
the page. A component with a JavaScript runtime lists the module and marks its root with
``add_auto_attach_marker(attrs, token)`` from the ``runtime`` module.

Testing
-------

``alliance_platform.ui.test_utils.StaticComponentTestCase`` is a ``SimpleTestCase`` with two
helpers:

* ``static_render_context(style_mappings=None, *, bundler=None, frontend_resource_registry=None)``
  is a context manager that sets up what compiling and rendering components needs. It enters a
  ``BundlerAssetContext`` with its checks skipped, yields it so tests can inspect the resources
  used, and resolves vanilla-extract class names from ``style_mappings`` rather than the bundler's
  mapping files. ``style_mappings`` is plain data keyed by stylesheet file name, or a longer
  trailing path when names collide, in the shape the vanilla-extract mapping files use. Classes
  you leave out resolve to ``""``. ``bundler`` and ``frontend_resource_registry`` default to your
  settings.
* ``render_ui_template(template_body, context=None)`` compiles the template with
  ``alliance_platform.ui`` loaded and renders it. Call it inside ``static_render_context``.

The stat's tests:

.. literalinclude:: ../tests/test_static_component_example.py
    :language: python
    :start-at: from alliance_platform.ui.html_components import built_in_registry
    :end-before: def test_payload_reaches_values_nested_in_markup

For tests that need the database, combine the base with Django's ``TestCase``:
``class StatTestCase(StaticComponentTestCase, TestCase)``.
