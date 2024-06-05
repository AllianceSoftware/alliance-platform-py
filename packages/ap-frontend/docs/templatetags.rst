Tags and Filters
****************

.. contents::
    :local:

.. _bundler-static-paths:

Static Paths
------------

Various template tags accept a path to an asset. For example, :ttag:`bundler_embed` accepts the path to an asset to embed
and :ttag:`component` accepts the path to a React component. These paths must be static values, i.e. they cannot be
template variables or expressions. This is because the paths must be known when the frontend build occurs, so that
the bundler knows which files to include in the build. The :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>`
management command will extract these paths from the templates and generate a list of files to include in the build.

Examples:

.. code-block:: html+django

    {# Valid, the path can be extracted by looking at the template file #}
    {% bundler_embed "styles.css" %}

    {# Invalid #}
    {% bundler_embed "styles.css"|upper %}
    {% bundler_embed variable %}

Bundler Tags
------------

.. templatetag:: bundler_embed

``bundler_embed``
-----------------

Return the embed HTML codes from the bundler to a specified asset.

Each asset can have multiple files associated with it. For example, a component might have javascript and css. You
can control which types of tags are included using the ``content_type`` kwarg. Common types are ``text/css`` and ``text/javascript``,
but it is ultimately based on the file extension (e.g. ``.png`` will be ``image/png``). Note that ``.css.ts`` is handled
as ``text/css`` and ``.ts`` and ``.tsx`` are handled as ``text/javascript``.

By default, the tags are added to the HTML by the :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_embed_collected_assets`.
This allows assets to be embedded as needed in templates but all added in one place in the HTML (most likely the ``<head>``).
You can force the tags to be outputted inline with ``inline=True``. Note that this only applies CSS and JS; other assets,
like images, will always be outputted inline.

Must be passed a :ref:`static path <bundler-static-paths>` to an asset.

Usage:

.. code-block:: html+django

    {% load bundler %}

    {% bundler_embed [path] [[content_type="css|js"] [inline=True] [html_*=...]] %}

================ =============================================================
Argument         Description
================ =============================================================
``path``         The path to the asset to embed. This must be a :ref:`static value <bundler-static-paths>`, i.e. it cannot be a template variable.
``content_type`` (optional) If set to either 'css' or 'js' only assets of the matching type will be embedded. If omitted
                 both types will be included (if available).
``inline``       (optional) If ``True`` the tags will be embedded inline, otherwise they will be added using the
                 :ttag:`bundler_embed_collected_assets` tag. Defaults to ``False``.
``html_*``       Any parameter with the ``html_`` prefix will have the ``html_`` stripped and will be passed through
                 to the embed tag. e.g. ``html_id="foo"`` would render ``<script id="foo" ...>``.
================ =============================================================

Usage with :ttag:`bundler_embed_collected_assets`:

.. code-block:: html+django

    {# in the base template (e.g. base.html) #}
    <!doctype html>
    {% load bundler %}
    <html lang="en-AU">
      <head>
        {% bundler_embed_collected_assets %}
      </head>
      <body>{% block body %}{% endblock %}</body>
    </html>

    {# in other individual templates, e.g. 'myview.html' #}

    {% extends "base.html" %}
    {% block body %}
        {% bundler_embed "MyComponent.ts" %}
        {% bundler_embed "logo.png" html_alt="My Component Logo" %}
        <h1>My View</h1>
    {% endblock %}

would output:

.. code-block:: html

    <!doctype html>
    <html lang="en-AU">
      <head>
        <script type="module" src="http://localhost:5173/assets/MyComponent.js"></script>
        <link rel="stylesheet" href="http://localhost:5173/assets/MyComponent.css" />
      </head>
      <body>
        <img src="http://localhost:5173/assets/logo.png" alt="My Component Logo" />
        <h1>My View</h1>
      </body>
    </html>

Using ``inline=True`` instead:

.. code-block:: html+django

    {% extends "base.html" %}
    {% block body %}
        {% bundler_embed "MyComponent.ts" inline=True %}
        <h1>My View</h1>
    {% endblock %}

would output:

.. code-block:: html

    <!doctype html>
    <html lang="en-AU">
      <head></head>
      <body>
        <script type="module" src="http://localhost:5173/assets/MyComponent.js"></script>
        <link rel="stylesheet" href="http://localhost:5173/assets/MyComponent.css" />
        <h1>My View</h1>
      </body>
    </html>

Note that in the example above ``logo.png`` is always embedded inline as it is not a javascript or css file.

.. templatetag:: bundler_url

``bundler_url``
-----------------

Return the URL from the bundler to a specified asset.

If you want to embed the asset with the appropriate HTML tags, use :ttag:`bundler_embed` instead.

Must be passed a :ref:`static path <bundler-static-paths>` to an asset.

If dev, this will return the path to the asset in the dev server. If not dev, this will return the path to the built
asset.

Usage:

.. code-block:: html+django

    {% load bundler %}

    {% bundler_url [static path] [as varname] %}

Examples:

.. code-block:: html+django

    {% bundler_url "style.css" %}

would output, in dev::

    http://localhost:5173/assets/style.css

in production::

    /assets/style-abc123.css

.. code-block:: html+django

    {% bundler_url "script.js" as script_url %}

    {# script_url is now available as a template variable #}

.. templatetag:: bundler_preamble

``bundler_preamble``
--------------------

Adds necessary code for things like enabling HMR. This tag accepts no arguments.

Typically this is only required in development but that is up to the Bundler to decide - the tag should
be included for both production and development.

Usage:

.. code-block:: html+django

    {% load bundler %}

    {# In the <head> element #}
    {% bundler_preamble %}

.. templatetag:: bundler_dev_checks

``bundler_dev_checks``
----------------------

Performs dev specific checks and may render some HTML to communicate messages to user

Currently checks if the dev server is running for this project, and if not displays an error.

Error will be logged to Django dev console. In addition, an error icon and toggleable modal message will be shown
in the HTML unless :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.BUNDLER_DISABLE_DEV_CHECK_HTML` is set.

This only applies in development, in production this tag is a no-op.

This tag accepts no arguments.

Usage:

.. code-block:: html+django

    {% load bundler %}

    {# At the end of the <body> element #}
    <body>
        ...
        {% bundler_dev_checks %}
    </body>

.. templatetag:: bundler_embed_collected_assets

``bundler_embed_collected_assets``
----------------------------------

Add tags to header for assets required in page. This tag accepts no arguments.

This makes using assets in templates easier, without needing to worry about adding it to the correct template area
or having duplicate tags from including the same asset more than once. You can embed assets as you need to use them,
at any level of the template hierarchy, and they will be added to the header in one place with no duplication.

This works with :class:`~alliance_platform.frontend.bundler.context.BundlerAssetContext` to collect all the assets used
within a template. See :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` for how
this context is created for you in Django views.

Because each asset must specify asset paths statically, this tag can retrieve assets from ``BundlerAssetContext``
and embed the required tags before the rest of the template is rendered.

Some existing assets are those created by the :func:`~alliance_platform.frontend.templatetags.vanilla_extract.stylesheet`,
:func:`~alliance_platform.frontend.templatetags.react.component`, or :func:`~alliance_platform.frontend.templatetags.bundler.bundler_embed`
tags. See the individual implementations for options that may influence how they are embedded (e.g. the ``inline``
option provided by ``bundler_embed``).

:data:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.html_target` will control whether scripts are included
and whether CSS is outputted in line in ``style`` tags or linked externally.

Generally, this tag should be used in the ``<head>`` of the HTML document. All script tags are non-blocking by default.

Usage:

.. code-block:: html+django

    {% load bundler %}

    {# In the <head> element #}
    <head>
        {% bundler_embed_collected_assets %}
    </head>

    <body>
        {# The actual output for this tag will be handled by bundler_embed_collected_assets, so will appear in head #}
        {% bundler_embed "style.css" %}
    </body>

React Tags
----------

.. templatetag:: component

``component``
-------------

Render a React component with the specified props

Usage:

.. code-block:: html+django

    {% load react %}

    {# using common components, e.g. div, h1, etc. #}
    {% component [dom element name] [prop_name=prop_value...] %} [children] {% endcomponent %}

    {# using a named export #}
    {% component [module path] [component import name] [prop_name=prop_value...] %} [children] {% endcomponent %}

    {# component path should have a default export #}
    {% component [component path] [component name] [prop_name=prop_value...] %} [children] {% endcomponent %}

There are three ways to specify which component to render. The first is for a `"common component" <https://react.dev/reference/react-dom/components/common>`_
which is to say a built-in browser component (e.g. ``div``):

.. code-block:: html+django

    {% component "h2" %}Heading{% endcomponent %}

The other two are for using a component defined in an external file. These will be loaded via
the specified bundler class (currently :class:`~alliance_platform.frontend.bundler.vite.ViteBundler`). With
a single argument it specifies that the default export from the file is the component to use:

.. code-block:: html+django

    {% component "components/Button" %}Click Me{% endcomponent %}

With two arguments the first is the file path and the second is the named export from that file:

.. code-block:: html+django

    {% component "components/Table" "Column" %}Name{% endcomponent %}

The last option has a variation for using a property of the export. This is useful for components
where related components are added as properties, e.g. ``Table`` and ``Table.Column``:

.. code-block:: html+django

    {% component "components" "Table.Column" %}Name{% endcomponent %}

Note that this is only available when using named exports; default exports don't support it due to
ambiguity around whether the ``.`` indicates file extension or property access.

You can omit the file extension - the above could resolve to ``components/Table.tsx`` (``.js`` and ``.ts`` are also
supported). See :ref:`resolving_paths` for details on how the file path is resolved.

Props are specified as keyword arguments to the tag:

.. code-block:: html+django

    {% component "components/Button" variant="primary" %}Click Me{% endcomponent %}

Additionally, a dict of props can be passed under the ``props`` kwarg:

.. code-block:: html+django

    {% component "components/Button" variant="primary" props=button_props %}Click Me{% endcomponent %}

Children can be passed between the opening ``{% component %}`` and closing ``{% endcomponent %}``. Whitespace
is handled the same as in JSX:

* Whitespace at the beginning and ending of lines is removed
* Blank lines are removed
* New lines adjacent to other components are removed
* New lines in the middle of a string literal is replaced with a single space

So the following are all equivalent:

.. code-block:: html+django

    {% component "div" %}Hello World{% endcomponent %}

    {% component %}
        Hello world
    {% endcomponent %}


    {% component %}
        Hello
        world
    {% endcomponent %}


    {% component %}

        Hello world
    {% endcomponent %}

Components can be nested:

.. code-block:: html+django

    {% component "components/Button" type="primary" %}
        {% components "icons" "Menu" %}{% endcomponent %}
        Open Menu
    {% end_component %}

and you can include HTML tags as children:

.. code-block:: html+django

    {% component "components/Button" type="primary" %}
        <strong>Delete</strong> Item
    {% end_component %}

You can use ``as <variable name>`` to store in a variable in context that can then be passed to another tag:

.. code-block:: html+django

    {% component "icons" "Menu" as icon %}{% end_component %}
    {% component "components/Button" type="primary" icon=icon %}Open Menu{% end_component %}

All props must be JSON serializable. :class:`~alliance_platform.frontend.prop_handlers.ComponentProp` can be used to define
how to serialize data, with a matching implementation in ``propTransformers.tsx`` to de-serialize it.

For example :class:`~alliance_platform.frontend.prop_handlers.DateProp` handles serializing a python ``datetime`` and
un-serializing it as a native JS ``Date`` on the frontend. See :class:`~alliance_platform.frontend.prop_handlers.ComponentProp`
for documentation about adding your own complex props.

Components are rendered using the ``renderComponent`` function in :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.REACT_RENDER_COMPONENT_FILE`. This can be modified as needed,
for example if a new provider is required.

.. note:: All props passed through are converted to camel case automatically (i.e. ``my_prop`` will become ``myProp``)

Server Side Rendering (SSR)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Components will automatically be rendered on the server. See :ref:`ssr` for details about how this works.

To opt out of SSR pass ``ssr:disabled=True`` to the component after the component name:

.. code-block:: html+django

    {% component 'components/Button.tsx' ssr:disabled=True %}...{% endcomponent %}

Alternatively, you can disable SSR entirely by passing ``disable_ssr=True`` to :class:`~alliance_platform.frontend.bundler.vite.ViteBundler`.

Note that when SSR is disabled, nothing will be rendered on the initial page load, so there will be a flash of
content as the component is rendered on the client side.

Options
~~~~~~~

Various options can be passed to the component tag. To differentiate from actual props to the component they are
prefixed with `ssr:` for server side rendering options, `component:` for general component options, or `container:`
for options relating to the container the component is rendered into.

- ``ssr:disabled=True`` - if specified, no server side rendering will occur for this component
- ``component:omit_if_empty=True`` - if specified, the component will not be rendered if it has no children. This is
  useful for when components may not be rendered based on permission checks
- ``container:tag`` - the HTML tag to use for the container. Defaults to the custom element ``dj-component``.
- ``container:<any other prop>`` - any other props will be passed to the container element. For example, to add
  an id to the container you can use ``container:id="my-id"``. Note that while you can pass a style string, it's
  likely to be of little use with the default container style ``display: contents``. Most of the time you can just
  do the styling on the component itself.

For example:

.. code-block:: html+django

    {% component 'core-ui' 'Button' ssr:disabled=True variant="Outlined"%}
        ...
    {% endcomponent %}

Limitations
~~~~~~~~~~~

Currently, attempting to render a django form widget that is itself a React component within another component will
not work. This is due to how django widgets have their own templates that are rendered in an isolated context. For
example, this will not work if ``form.field`` also uses the ``{% component %}`` tag:

.. code-block:: html+django

        {% component 'MyComponent' %}
            {{ form.field }}
        {% endcomponent %}


.. templatetag:: react_refresh_preamble

``react_refresh_preamble``
--------------------------

Add `react-refresh <https://www.npmjs.com/package/react-refresh>`_ support

Currently only works with :class:`~alliance_platform.frontend.bundler.vite.ViteBundler`. This must appear after
:meth:`~alliance_platform.frontend.templatetags.bundler.bundler_preamble`.

This is a development only feature; in production the tag is a no-op.

See https://vitejs.dev/guide/backend-integration.html

Usage:

.. code-block:: html+django

    {% bundler_preamble %}
    {% react_refresh_preamble %}

Vanilla Extract Stylesheet
--------------------------

.. templatetag:: stylesheet

``stylesheet``
--------------

Add a vanilla extract CSS file the page, optionally exposing class name mapping in a template variable.

Usage:

.. code-block:: html+django

    {% load vanilla_extract %}

    {% stylesheet [path] [as varname] %}

The tag accepts a single argument, the path to the vanilla extract CSS file. This path must be a :ref:`static value <bundler-static-paths>`.

If the CSS file includes exported class names, you can access the mapping by specifying a variable with the syntax
``as <var name>``.

If you do not specify a variable using the ``as <var name>`` syntax, the styles will only be available globally,
and any specified variables will be ignored.

For more information on how paths are resolved, refer to the documentation on :ref:`resolving_paths`.

The CSS file is not embedded inline where the tag is used, rather it is added by the :ttag:`bundler_embed_collected_assets`
tag.

Example:

.. code-block:: html+django

    {% load vanilla_extract %}

    <head>
        {% bundler_embed_collected_assets %}
    </head>

    {% stylesheet "./myView.css.ts" as styles %}

    <div class="{{ styles.section }}">
        <h1 class="{{ styles.heading }}">My View</h1>
        ...
    </div>

.. note:: If you need to include a plain CSS file use the :ttag:`bundler_embed` tag instead.

.. admonition:: Vite plugin required

    This functionality relies on the plugin defined by in ``frontend/vite/plugins/vanillaExtractWithExtras.ts``
    in the template proejct.

Forms
-----
.. templatetag:: form

``form``
--------

Tag to setup a form context for form_input tags

This tag doesn't render anything itself, it just sets up context for ``form_input`` tags. This is to support
the ``auto_focus`` behaviour. This works by adding an ``auto_focus`` prop to the first field with errors, or the
first rendered field if no errors are present.

Usage:

.. code-block:: html+django

    {% load form %}

    {% form form auto_focus=True %}
        <form method="post>
        {% for field in form.visible_fields %}
          {% form_input field %}
        {% endfor %}
        </form>
    {% endform %}


.. note::

    Usage of this tag requires the following :setting:`FORM_RENDERER <django:FORM_RENDERER>` setting to be set to::

        FORM_RENDERER = "alliance_platform.frontend.forms.renderers.FormInputContextRenderer"

.. templatetag:: form_input

``form_input``
--------------

Renders a form input with additional props supported by ``alliance_ui``.

This sets ``label``, ``errorMessage``, ``validationState``, ``description`` and ``isRequired``. In addition, it may
set ``autoFocus`` based on the ``auto_focus`` setting on the parent ``form`` tag.

The following options can be passed to the tag to override defaults:

- ``label`` - set the label for the input. If not specified will use ``field.label``.
- ``help_text`` - help text to show below the input. If not specified will use ``field.help_text``.
- ``show_valid_state`` - if true, will show the 'valid' (i.e. success) state of the input. If not specified will use
  ``False``. For most components in alliance-ui this results in it showing a tick icon and/or rendering green. If
  this is ``False`` only error states will be shown.
- ``is_required`` - if true, will show the input as required. If not specified will use the model field ``required``
  setting.

In addition, you can pass through any extra attributes that should be set on the input. For example, to set an
addon for an ``alliance_ui`` ``TextInput`` you could do the following:

.. code-block:: html+django

    {% form_input field addonBefore="$" %}

Note that the attributes supported here depend entirely on the widget. If the widget is a React component, you
can also pass react components to the tag:

.. code-block:: html+django

    {% Icon "SearchOutlined" as search_icon %}
    {% form_input field addonBefore=search_icon %}

The additional props are added to the key ``extra_widget_props`` - so the relevant widget template needs to include
this for the props to be passed through:

.. code-block:: html+django

    {% component "@alliancesoftware/ui" "TextInput" props=widget.attrs|merge_props:extra_widget_props|html_attr_to_jsx type=widget.type name=widget.name default_value=widget.value %}
    {% endcomponent %}

If you want the widget template to work even if ``extra_widget_props`` isn't available (e.g. for usage without ``form_input``),
then you can do the following:

.. code-block:: html+django

    {% with extra_widget_props=extra_widget_props|default:None %}
      {% component "@alliancesoftware/ui" "TextInput" props=widget.attrs|merge_props:extra_widget_props|html_attr_to_jsx type=widget.type name=widget.name default_value=widget.value %}
      {% endcomponent %}
    {% endwith %}

Filters
-------

.. templatefilter:: merge_props

``merge_props``
---------------

Merge props from two dicts together. You can pass this through the :tfilter:`html_attr_to_jsx` filter to convert
prop names to those expected in JSX.

Usage:

.. code-block:: html+django

    {% component "MyComponent" props=widget.attrs|merge_props:some_more_props|html_attr_to_jsx %}{% endcomponent %}

.. templatefilter:: html_attr_to_jsx

``html_attr_to_jsx``
--------------------

Convert html attributes to casing expected by JSX

Calls :meth:`~alliance_platform.frontend.util.transform_attribute_names`

Usage:

.. code-block:: html+django

    {% component "MyComponent" props=widget.attrs|html_attr_to_jsx %}{% endcomponent %}


``none_as_nan``
--------------------

Convert ``None`` to :data:`math.nan <python:math.nan>`

This is useful for props that should be passed as NaN to the component. The `NumberInput <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-numberinput--docs>`_ component uses ``NaN``
instead of ``null`` for no value.

Usage:

.. code-block:: html+django

    {% component "@alliancesoftware/ui" "NumberInput" default_value=widget.value|none_as_nan %}{% endcomponent %}
