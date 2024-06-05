Overview
=========

.. _styling:

Styling
#######

When styling components in this library the preferred approach is to use `Vanilla Extract <https://vanilla-extract.style/>`_ for the following reasons:

- Automatic namespacing eliminates the need for naming conventions like BEM, making it easier to write and manage styles.
- The build system will extract used vanilla-extract styles to static CSS for use in production, which improves performance (i.e. there's no required JS runtime for the styles).
- Sharing common styles across components or pages is easier since you can just import from the file.
- Having a full featured programming language at your disposal is very useful for things like writing variations for a
  component

To load vanilla-extract styles in your templates, use the :ttag:`stylesheet`
template tag. This tag allows you to load the styles and get access to the class names in a context variable.

In some cases, you may need to import vanilla CSS instead of using vanilla-extract, such as when working with third-party
modules. In those cases, you can use the :ttag:`bundler_embed` tag to import the CSS.

.. _react:

React
#####

Django templates are easy and convenient, but oftentimes you need more than static HTML. Turning the whole page into a
React page is often overkill and means you lose the ability to use things like Django forms. However, you can use the
:ttag:`component` tag to easily render a React component in part of the page, or
the whole page as required.

By combining Django templates with React components, you can take advantage of the benefits of both technologies. See
:ttag:`component` for details on how to do it.

By default, props passed to the component must be JSON serializable. However, if you need to pass complex props, you can
use the :class:`~alliance_platform.frontend.prop_handlers.ComponentProp` to automatically convert them to a format that can be
passed to the component. For example, :class:`~alliance_platform.frontend.prop_handlers.DateProp` allows you to pass a ``datetime``
object and have it passed to the component as a JavaScript ``Date``.

Combine this with :ref:`Server Side Rendering (SSR) <ssr>` to get the best of both worlds. By using SSR, you can render the React
component on the server and send the generated HTML to the client, allowing for perceived faster load times and avoiding
flashes of content as things render dynamically.

.. _resolving_paths:

Resolving Paths
###############

Various template tags accept a string to an asset, for example a React component or a stylesheet. This section
describes how the value passed here is handled.

When a string representing a path is passed to a template tag, the bundler will resolve it
based on the settings in :data:`~alliance_platform.frontend.bundler.base.BaseBundler.path_resolvers`.
There is no default behaviour, but there are some classes you can use for common cases.

To define your own behavior, you can subclass :class:`~alliance_platform.frontend.bundler.base.PathResolver`. In
this example, ``AlliancePlatformPackageResolver`` will resolve any usages of ``@alliancesoftware/ui`` or ``@alliancesoftware/icons``
to the ``node_modules`` directory. This allows you to use ``{% component "@alliancesoftware/ui" "Table" %}`` rather than
``{% component "/node_modules/@alliancesoftware/ui" "Table" %}``:

.. code-block:: python

    class AlliancePlatformPackageResolver(PathResolver):
        """Resolve usages of @alliancesoftware/* packages to node_modules directory.

        Allows usages like ``{% component "@alliancesoftware/ui" "Table" %}``` rather than
        ``{% component "/node_modules/@alliancesoftware/ui" "Table" %}```.
        """

        def resolve(self, path: str, context: ResolveContext):
            if path.startswith("@alliancesoftware/ui") or path.startswith("@alliancesoftware/icons"):
                return ap_frontend_settings.NODE_MODULES_DIR / path
            return None

.. note::

    While we work with ``Path`` objects here, in production the bundler will handle these even if the source code
    doesn't exist in the filesystem. For example, the ViteBundler will use the resolved paths to index into its generated
    manifest file. In the example above, the resolved path might be ``/node_modules/@alliancesoftware/ui/Table.tsx``,
    which would have an entry in the manifest file mapping it to the generate file ``Table.hash123.js``.

    In development, extra checks are done to ensure the file used exists on the filesystem.

Here is a more complete example of what ``path_resolvers`` could be set to:

.. code-block:: python

    path_resolvers=[
        AlliancePlatformPackageResolver(),
        RelativePathResolver(),
        RegExAliasResolver("^/", str(settings.PROJECT_DIR) + "/"),
        SourceDirResolver(root_dir / "frontend/src"),
    ]

This will resolve paths as follows:

- If path is in the form of ``@alliancesoftware/ui`` or ``@alliancesoftware/icons``, it will be resolved to the ``node_modules`` directory.
- If the path is relative (starting with ``./`` or ``../``), it is resolved relative to the template file that contains the tag.
- If the path starts with ``/``, it is resolved relative to ``settings.PROJECT_DIR``.
- Otherwise, it is resolved relative to ``frontend/src``.

So the following paths would be resolved as follows, assuming ``PROJECT_DIR`` is ``/root``:

- ``@alliancesoftware/ui`` -> ``/root/node_modules/@alliancesoftware/ui``
- ``./MyComponent`` called from within ``my_site/templates/file.html`` -> ``/root/my_site/templates/MyComponent``
- ``components/MyComponent`` -> ``/root/frontend/src/components/MyComponent``
- ``/my_file`` -> ``/root/my_file``

As most of the time you will be including components from one directory (e.g. ``frontend/src/``), this setup makes
that the easiest.

.. _ssr:

Server Side Rendering (SSR)
###########################

Server Side Rendering (SSR) is a technique used to render components on the server, and send the generated HTML to the client,
which is then hydrated with JavaScript to allow interactivity. This technique can improve perceived website performance, as it
shows the content immediately rather than waiting for JavaScript to be loaded, parsed and executed. It can also benefit SEO or
potentially be used for things like PDF rendering that relies on static HTML.

SSR is enabled by default and works as follows:

- Each component rendered in a template queues itself to be rendered with :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.queue_ssr`.
- :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` accesses the context and retrieves all the queued SSR items.
- It then serializes the queued items and calls out to javascript, which renders each component to static HTML and returns it

    - In development this is handled by ``dev-server.ts``. This allows Vite to process the required modules without having to do a full production build
    - In production it is handled by ``production-ssr-server.ts`` which works with the production built files.

Currently, the only thing that gets rendered on the server is React components. :class:`~alliance_platform.frontend.templatetags.react.ComponentSSRItem`
is used to describe the component that needs to be rendered. See its documentation for details on how each component
is serialized.

.. admonition:: Disabling SSR

    To disable SSR entirely you can pass ``disable_ssr=True`` to :class:`~alliance_platform.frontend.bundler.vite.ViteBundler`.

.. note::

    The above references to ``dev-server.ts`` and ``production-ssr-server.ts`` are specific to the template-django setup.
    These will be available in a separate package in the future.


Quick Reference
###############

* To get the bundler instance use :func:`~alliance_platform.frontend.bundler.get_bundler`
* To render a React component in a template use the :ttag:`component` tag:

.. code-block:: html+django

    {% load react %}

    <!-- Default export -->
    {% component "components/Button" type="primary" %}
        <strong>Click Me</strong>
    {% endcomponent %}
    <!-- Named export -->
    {% component "components/Table" "Column" %}Header{% endcomponent %}
    <!-- Pass a component as a prop to another component -->
    {% component "components/Icons" "Menu" as menu_icon %}{% endcomponent %}
    {% component "components/Button" icon=menu_icon %}{% endcomponent %}

* To include a Vanilla Extract stylesheet in a template use the :ttag:`stylesheet` tag:

.. code-block:: html+django

    {% load vanilla_extract %}
    {% stylesheet "./MyView.css.ts" as styles %}

    <div class="{{ styles.wrapper }}{% if is_delete %} {{ styles.deleteWrapper }}{% endif %}">
        ...
    </div>

* To include a plain CSS file in a template use :ttag:`bundler_embed`:

.. code-block:: html+django

    {% load bundler %}
    {% bundler_embed "./normalize.css" %}
