Alliance UI Tags and Filters
****************************

These template tags and filters provide a convenient way to render components from the Alliance UI React library in Django templates.

You can load the tags and filters with:

.. code-block:: html+django

    {% load alliance_platform.ui %}

You can see the main documentation for the Alliance UI components `here <https://main--64894ae38875dcf46367336f.chromatic.com/>`_.
Not all components have a tag; you can render them using the :ttag:`component` tag. See the linked documentation
for the props each component accept as they aren't duplicated in this documentation.

Any differences from the underlying React components are documented below.

Template Tags
-------------

The Alliance UI template tags serve as a convenient alternative to the :ttag:`component`
template tag, for easily embedding components from the Alliance UI library into Django templates. See the documentation for
the component tag for instructions on passing arguments and filters.

.. templatetag:: Button

``Button``
----------

Render a `Button <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-button--docs>`_ component from the
Alliance UI React library with the specified props.

Usage:

.. code-block:: html+django

    {% Button variant="outlined" %}Click Me{% endButton %}

You can render as a link by passing ``href``. To resolve named URLs, optionally with permission checks you can
use ``url`` or ``url_with_perm`` filters:


.. code-block:: html+django

    {% Button variant="outlined" color="secondary" size="md" href="my_app:organisation_update"|url_with_perm:organisation.pk|with_perm_obj:organisation %}
      Update
    {% endButton %}

.. templatetag:: ButtonGroup

``ButtonGroup``
---------------

Render a `ButtonGroup <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-buttongroup--docs>`_ component
from the Alliance UI React library with the specified props.

The children of the tag should be :ttag:`Button` tags.

.. code-block:: html+django

    {% ButtonGroup density="xs" size="sm" variant="link" %}
      {% Button href="my_app:mymodel_update"|url_with_perm:obj.pk|with_perm_obj:obj aria-label="Edit" %}
         {% Icon "Pencil01Outlined" %}
      {% endButton %}
      {% Button href="my_app:mymodel_detail"|url_with_perm:obj.pk|with_perm_obj:obj aria-label="View" %}
        {% Icon "FileSearch01Outlined" %}
      {% endButton %}
      {% Button href="my_app:mymodel_delete"|url_with_perm:obj.pk|with_perm_obj:obj aria-label="Delete" %}
        {% Icon "Trash01Outlined" %}
      {% endButton %}
    {% endButtonGroup %}

.. templatetag:: DatePicker

``DatePicker``
---------------

Render a `DatePicker <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-datepicker--docs>`_ component
from the Alliance UI React library with the specified props.

This can be used as date picker, or a datetime picker, depending on the specified ``granularity`` (default is "day").

``granularity`` can be one of "day", "hour", "minute", "second".

``default_value`` can be a string, in which case it will be parsed using :func:`~django:django.utils.dateparse.parse_date`
when the granularity is "day", otherwise :func:`~django:django.utils.dateparse.parse_datetime`. Otherwise ``default_value``
should be a :class:`python:datetime.date` instance when ``granularity="day"``, otherwise a :class:`python:datetime.date` instance

.. code-block:: html+django

    {% DatePicker name=widget.name default_value=raw_value %}{% endDatePicker %}

.. templatetag:: Icon

``Icon``
--------

Render an icon from `@alliancesoftware/icons <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/icons-icons--docs>`_.

See the `list of icons here <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/story/icons-icons--all-icons>`_.

.. code-block:: html+django

    {% Icon "Trash01Outlined" %}

It can be passed to other components props by using the ``as <var name>`` form

.. code-block:: html+django

    {% Icon "Trash01Outlined" as icon %}
    {% component "MyComponent" icon=icon %}{% endcomponent %}


.. templatetag:: InlineAlert

``InlineAlert``
---------------

Render an `InlineAlert <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-inlinealert--docs>`_ component
from the Alliance UI React library with the specified props.

.. code-block:: html+django

    {% InlineAlert intent="success" %}Changes saved successfully{% endInlineAlert %}


.. templatetag:: LabeledInput

``LabeledInput``
----------------

Render an `LabeledInput <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-labeledinput--docs>`_ component
from the Alliance UI React library with the specified props.

This can be useful with custom widgets that get rendered with :ttag:`form_input` where you want standard rendering
of label, help text, validation, required indicator etc.

.. code-block:: html+django

    {% load alliance_platform.ui %}

    {# this is in your widget template. extra_widget_props come from `form_input` #}
    {% LabeledInput props=extra_widget_props %}
       {# render your widget here. validation, help text and label will be handled for you. %}
       <input />
    {% endLabeledInput %}

Alternatively, you can extend the ``alliance_platform/ui/labeled_input_base.html`` template
as a base and fill in the ``input`` block with the relevant HTML:

.. code-block:: html+django

    {% extends "alliance_platform/ui/labeled_input_base.html" %}

    {% block input %}
      <input type="{{ widget.type }}" name="{{ widget.name }}"{% if widget.value != None %} value="{{ widget.value|stringformat:'s' }}"{% endif %}>
    {% endblock %}

Finally, if you want to wrap a single instance of a widget without changing the template you can use
the ``non_standard_widget=True`` option to :ttag:`form_input`. This will render the widget as normal,
but wrap it in a ``LabeledInput`` component.

    .. code-block:: html+django

    {% form_input field non_standard_widget=True %}

.. templatetag:: Menubar

``Menubar``
-----------

Render an `Menubar <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-menubar--docs>`_ component.

You can use ``Menubar.Section``, ``Menubar.Item``, and `Menubar.SubMenu`` components to build the menu.

Here is a fully featured example that renders a Users section, followed by a link to an Audit logs page, and finally a
submenu with an icon for the current user's account management link and a logout button that submits a logout form.

.. code-block:: html+django

    {# logout should occur via post, so add a form here that can be submitted from the menu %}
    <form method="post" action="{% url 'logout' %}" id="logout-form">
      {% csrf_token %}
    </form>

    {% Icon "User01Outlined" size="xs" as UserIcon %}

    {% Menubar %}
      {% Menubar.Section title="Users" %}
        {% Menubar.Item href="my_app:adminprofile_list"|url_with_perm key="admin" %}
          Admin
        {% endMenubar.Item %}
        {% Menubar.Item href="my_app:client_list"|url_with_perm  %}
          Clients
        {% endMenubar.Item %}
      {% endMenubar.Section %}
      {% Menubar.Item href="my_app:audit_logs"|url_with_perm %}
        Audit
      {% endMenubar.Item %}
      {% Menubar.SubMenu text_value="My Account" title=UserIcon %}
        {% Menubar.Item href="my_app:personal-account"|url_with_perm %}
          My Account
        {% endMenubar.Item %}
        {% Menubar.Item element_type="button" type="submit" form="logout-form" %}
          Logout
        {% endMenubar.Item %}
      {% endMenubar.SubMenu %}
    {% endcomponent %}


.. templatetag:: Table

``Table``
-----------

Render an `Table <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-table--docs>`_ component.

You can use ``TableHeader``, ``TableBody``, ``Row``, ``Column`` and ``Cell`` components to build the menu.

This example renders a list of records, and allows sorting of columns by clicking on the column headers. This makes
use of the :tfilter:`table_sort_order` filter to determine the current sort order of the column and pass it through
in the expected format. The sort order is stored in the ``order`` query param.

.. code-block:: html+django

    {# Use this to render header as links to the current page with the sort column query param updated #}
    {% ColumnHeaderLink sort_query_param="order" as header_element_type %}{% endColumnHeaderLink %}

    {% Table column_header_element_type=header_element_type sort_order=request|table_sort_order:"order" sort_mode="multiple" sort_behavior="replace" aria-label="User List" %}
      {% TableHeader %}
        {% Column allows_sorting=True %}Name{% endColumn %}
        {% Column allows_sorting=True  %}Email{% endColumn %}
        {% Column %}Active{% endColumn %}
        {% Column %}Actions{% endColumn %}
      {% endTableHeader %}
      {% TableBody %}
        {% for obj in object_list %}
          {% Row key=obj.pk %}
            {% Cell %}{{ obj.name }}{% endCell %}
            {% Cell %}{{ obj.email }}{% endCell %}
            {% Cell %}{{ obj.is_active }}{% endCell %}
            {% Cell %}
              {% ButtonGroup density="xs" size="sm" variant="link" %}
                {% Button href="my_app:user_update"|url_with_perm:obj.pk|with_perm_obj:obj aria-label="Edit" %}
                   {% Icon "Pencil01Outlined" %}
                {% endButton %}
                {% Button href="my_app:user_detail"|url_with_perm:obj.pk|with_perm_obj:obj aria-label="View" %}
                  {% Icon "FileSearch01Outlined" %}
                {% endButton %}
                {% Button href="my_app:user_delete"|url_with_perm:obj.pk|with_perm_obj:obj aria-label="Delete" %}
                  {% Icon "Trash01Outlined" %}
                {% endButton %}
              {% endButtonGroup %}
            {% endCell %}
          {% endRow %}
         {% endfor %}
      {% endTableBody %}
    {% endTable %}


You can use it with the :ttag:`Pagination` component to render a paginated table.

.. code-block:: html+django

    {% Pagination page=page_obj.number total=paginator.count page_size=paginator.per_page boundary_count=2 sibling_count=1 aria-label="Pagination" is_page_size_selectable=allow_page_size_selection as pagination %}{% endPagination %}
    {% Table aria-label="User List" footer=pagination %}
      {% TableHeader %}
        {# omitted for brevity #}
      {% endTableHeader %}
      {% TableBody %}
        {# omitted for brevity #}
      {% endTableBody %}
    {% endTable %}

.. templatetag:: ColumnHeaderLink

``ColumnHeaderLink``
--------------------

For use with :ttag:`Table` components, this tag will render a link that updates the sort order query parameter when clicked.

See the :ttag:`Table` documentation for an example of how to use this tag.

.. templatetag:: Pagination

``Pagination``
--------------

Render an `Pagination <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-pagination--docs>`_ component.

Usage:

.. code-block:: html+django

    {% Pagination page=1 total=100 page_size=10 boundary_count=2 sibling_count=1 aria-label="Pagination" is_page_size_selectable=True %}{% endPagination %}

.. templatetag:: TimeInput

``TimeInput``
-------------

Render an `TimeInput <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/ui-timeinput--docs>`_ component.

The value passed to ``default_value`` can be a string, in which case it will be parsed using :func:`~django:django.utils.dateparse.parse_time`,
otherwise it should be :class:`python:datetime.time` instance.

Usage:

.. code-block:: html+django

    {% TimeInput name="time" default_value="12:45" %}{% endTimeInput %}

.. templatetag:: Fragment

``Fragment``
------------

Render a React ``Fragment``. Can be used in cases where you need to wrap multiple components in a single parent element.

.. code-block:: html+django

    {% Fragment as buttons %}
      {% Button variant="outlined" %}Click Me{% endButton %}
      {% Button variant="outlined" %}Also Click Me{% endButton %}
    {% endFragment %}

    {% component "MyComponent" extra=buttons %}{% endcomponent %}

Forms
-----
.. templatetag:: form

``form``
--------

Tag to setup a form context for :ttag:`form_input` tags

This tag doesn't render anything itself, it just sets up context for :ttag:`form_input` tags. This is to support
the ``auto_focus`` behaviour. This works by adding an ``auto_focus`` prop to the first field with errors, or the
first rendered field if no errors are present.

Usage:

.. code-block:: html+django

    {% load alliance_platform.form %}

    {% form form auto_focus=True %}
        <form method="post>
        {% for field in form.visible_fields %}
          {% form_input field %}
        {% endfor %}
        </form>
    {% endform %}


.. note::

    Usage of this tag requires the following :setting:`FORM_RENDERER <django:FORM_RENDERER>` setting to be set to::

        FORM_RENDERER = "alliance_platform.ui.forms.renderers.FormInputContextRenderer"

.. templatetag:: form_input

``form_input``
--------------

Renders a form input with additional props supported by widgets from ``alliance_platform.ui``.

.. note::

    Usage of this tag requires the following :setting:`FORM_RENDERER <django:FORM_RENDERER>` setting to be set to::

        FORM_RENDERER = "alliance_platform.ui.forms.renderers.FormInputContextRenderer"

This tag set's two extra template variables to be used by the widget template:

- ``raw_value`` - the raw value of the field. This is useful for components that need to access the raw value, not the
  value that has been transformed by a widget class. In many cases, a widget will transform the value to a string which
  works fine for plain HTML inputs, but for React components you often want the value in it's original type.
- ``extra_widget_props`` - a dict with the entries described below

- ``label`` - the label for the field. This will be the ``label`` value passed to the tag if any, otherwise ``field.label``.
- ``errorMessage`` - the error message for the field when in an invalid state. This is a comma separated list of errors
  as defined on ``field.errors``.
- ``validationState`` - ``"invalid"`` where there is an error, otherwise ``"valid"`` depending on the value of ``show_valid_state`` option
- ``is_required`` - whether the field is required. This is based on the ``required`` attribute on the form field unless overridden with the ``is_required`` option to this tag.
- ``description`` - the help text for the field. You can explicitly specify this with the ``help_text`` option, otherwise the ``field.help_text`` value will be used.
- ``autoFocus`` - whether the field should be focused on page load. This is set based on the ``auto_focus`` option to the parent ``form`` tag.

The following options can be passed to the tag to override defaults:

- ``label`` - set the label for the input. If not specified will use ``field.label``.
- ``help_text`` - help text to show below the input. If not specified will use ``field.help_text``.
- ``show_valid_state`` - if true, ``validationState`` will be set to `"valid"` when there is no error . If not specified
  will default to ``False``. For most components in @alliancesoftware/ui this results in it showing a tick icon and/or
  rendering green, but may have no effect. If this is ``False`` only error states will be shown.
- ``is_required`` - if true, will show the input as required. If not specified will use the model field ``required``
  setting.

In addition, you can pass through any extra attributes that should be set on the input. For example, to set an
addon for an ``alliance_platform.ui`` ``TextInput`` you could do the following:

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

.. admonition:: Usage with other widgets

    This tag only provides the extra template variables described above - it does not change the rendering itself. The
    tag will render :meth:`~django:django.forms.BoundField.as_widget`, it is then up to the selected widget to make
    use of the provided values as shown above.

    In the ``template-django`` project this is handled in the overridden widget templates in ``xenopus_frog_app/templates/django/forms/widgets``.
    Note that this may be incomplete; for any widgets not overridden the default Django widget template will be used
    which won't make use of the extra template variables. If you have a widget template that you wish to convert to
    the same pattern as @alliancesoftware/ui components, you can use the ``alliance_platform/ui/labeled_input_base.html`` template
    as a base and fill in the ``input`` block with the relevant HTML:

    .. code-block:: html+django

        {% extends "alliance_platform/ui/labeled_input_base.html" %}

        {% block input %}
          <input type="{{ widget.type }}" name="{{ widget.name }}"{% if widget.value != None %} value="{{ widget.value|stringformat:'s' }}"{% endif %}>
        {% endblock %}

    Alternatively, you can use the ``non_standard_widget=True`` option to force the tag to wrap the widget in a
    :ttag:`LabeledInput`. This is the equivalent of using the ``labeled_input_base.html`` template but is more
    convenient for one-off cases or where you do not want to override the template.

    .. code-block:: html+django

        {% form_input field non_standard_widget=True %}

``query_params``
----------------

Add a dictionary to the template context with keys set by arbitrary keyword arguments, to pass to the ``with_params`` filter. See :tfilter:`with_params`
for usage example.

Filters
-------

.. templatefilter:: url_with_perm

``url_with_perm``
--------------------

Resolve a URL and check if the current user has permission to access it.

If you don't need permission checks, use :tfilter:`url`.

If permission check fails, the component that uses the value will be omitted from rendering.

Usage:

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm:2 %}Link{% endcomponent %}

The above example will resolve the URL "my_url_name" with the argument ``2``.

If you need multiple arguments you can use the ``with_arg`` filter:

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm:2|with_arg:"another arg" %}Link{% endcomponent %}

To pass kwargs you can use the ``with_kwargs`` filter:

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm|with_kwargs:my_kwargs %}Link{% endcomponent %}

Note that as there's no way to define a dictionary in the standard Django template language, you'll need to
pass it in context.


To do object level permission checks use the ``with_perm_obj`` filter to pass through the object:

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm:obj.pk|with_obj:obj %}Link{% endcomponent %}

Note that you still have to pass through the pk to resolve the URL with. Passing the object just allows the permission
checks to work without having to manually look up the object. Due to how the ``DetailView.get_object`` method works,
if you are not going to pass the object you must use ``with_kwargs`` to pass through the ID rather than a positional
argument:

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm|with_kwargs:kwargs %}Link{% endcomponent %}

Note that the above would do a query to retrieve the object, so it's better to pass the object if you have already
retrieved it.

.. templatefilter:: url

``url``
-------

Behaves same as :tfilter:`url_with_perm` but does not check any permissions.

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm|with_kwargs:kwargs %}

.. templatefilter:: with_arg

``with_arg``
--------------------

Add an argument to a :tfilter:`url_with_perm` or :tfilter:`url` filter. This is useful when you need to pass multiple arguments to a URL.

.. code-block:: html+django

    {# This will resolve "my_url_name" with args [2, "another arg"]
    {% component "a" href="my_url_name"|url_with_perm:2|with_arg:"another arg" %}Link{% endcomponent %}

.. templatefilter:: with_kwargs

``with_kwargs``
--------------------

Add kwargs to a :tfilter:`url_with_perm` or :tfilter:`url` filter.

.. code-block:: html+django

    {% component "a" href="my_url_name"|url_with_perm|with_kwargs:my_kwargs %}Link{% endcomponent %}

.. templatefilter:: with_params

``with_params``
--------------------

Add query params to a :tfilter:`url_with_perm` or :tfilter:`url` filter.

.. code-block:: html+django

    {% query_params x=1 id=record.pk as my_query %}
    {% Button href="my_url"|url_with_perm|with_query:my_query %}

.. templatefilter:: with_perm_object

``with_perm_object``
--------------------

Add an object to a :tfilter:`url_with_perm` filter for the purposes of object level permission checks.

This is useful if you already have the object and want to pass it through to the permission check, thereby avoiding
another database query.

.. code-block:: html+django

    {% component "a" href="organisation_detail"|url_with_perm:organisation.pk|with_perm_obj:organisation %}
        View
    {% endButton %}

.. templatefilter:: unwrap_list

``unwrap_list``
---------------

Unwrap a list of length 1 into the single item it contains. This is useful when you have a list of items but you know
there will only ever be one item in the list. For example, the django radio input widget value is always a list even
though there's only a single value.

.. code-block:: html+django

    {% component "@alliancesoftware/ui" "RadioGroup" props=widget.attrs|merge_props:extra_widget_props|html_attr_to_jsx type=widget.type name=widget.name default_value=widget.value|unwrap_list %}
        ...
    {% endcomponent %}


.. templatefilter:: table_sort_order

``table_sort_order``
--------------------

For use with :ttag:`Table` components, this filter will return the current sort order from the request.

For example, if the current url was ``/foo?ordering=-bar,email`` this filter would return::

   [
      {'column': 'email', 'direction': 'ascending'},
      {'column': 'name', 'direction': 'descending'}
   ]

This filter expects to be passed the current :class:`~django:django.http.HttpRequest` object, and optionally the query parameter name to look for.
If the query parameter name is not specified it defaults to `"ordering"`.

In no ordering is present in the URL an empty list ``[]`` will be returned.

Usage:

.. code-block:: html+django

    {% Table sort_order=request|table_sort_order:"order" %}
      ...
    {% endTable %}
