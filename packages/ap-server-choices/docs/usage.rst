Usage
#####

Once installation is complete and the view is registered, you can start using the decorator :func:`~alliance_platform.server_choices.decorators.server_choices`
to register choices. The most basic usage is:

.. code-block:: python

    @server_choices()
    class MyForm(ModelForm):
        class Meta:
            model = MyModel
            fields = [
                "field1",
                "field2",
            ]

Imagine ``field1`` and ``field2`` are both foreign keys. The ``server_choices`` decorator will automatically register those
fields, and then the frontend can fetch the available choices from :class:`~alliance_platform.server_choices.views.ServerChoicesView`
a page at a time. In this example the fields are inferred from the class being decorated using the
:meth:`~alliance_platform.server_choices.class_handlers.form.FormServerChoiceFieldRegistration.infer_fields` method.

Out of the box there is support for decorating Django forms, Django filter sets, and
DRF serializers. In the above example, the ``@server_choices`` decorator defers to the :class:`~alliance_platform.server_choices.class_handlers.form.FormServerChoiceFieldRegistration`
registration class. If the class being decorated was a FilterSet or a Serializer then the
:class:`~alliance_platform.server_choices.class_handlers.django_filters.FilterSetServerChoiceFieldRegistration` or
:class:`~alliance_platform.server_choices.class_handlers.rest_framework.SerializerServerChoiceFieldRegistration` registration
class would be used instead. The decorator passes through the arguments to the registration class. This also means
you can add additional registration classes to handle other usages not covered by the default ones.

.. note::
    DRF integration is optional and only activated if ``rest_framework`` is installed.

Instead of inferring fields, you can also explicitly specify the fields to register:

.. code-block:: python

    @server_choices(['field1])
    class MyForm(ModelForm):
        ...

You can also decorate multiple times to configure each field individually:

.. code-block:: python

    @server_choices(['field1], page_size=0)
    @server_choices(['field2], page_size=50)
    class MyForm(ModelForm):
        ...

Choices can be defined as either a queryset, or as a list of 2-tuples (key, value). By default, inference will only pick up
queryset choices - for example ``ModelChoiceField`` on a Django Form. To use other choices opt in explicitly:

.. code-block:: python

    @server_choices(["simple"], perm="some_perm") 
    class TestForm(Form):
        simple = ChoiceField(choices=[("choice_a", "Choice A"), ("choice_b", "Choice B")]) 

The rationale for this is that most often choices defined like this are fine to embed in the HTML upfront - dynamically fetching choices
is only needed when working with large lists of choices.


Label & Value
=============

Each choice returned from the view only includes, by default, a label and value. The label is the text that is displayed
to the user and the value should be a unique identifier for the choice.

The default implementation of the label depends on how choices are defined. If it is a queryset then the label is the
``__str__`` of the object. If it is a list of tuples then the label is the second element of the tuple. For a queryset,
the value is always the primary key. For a list of tuples, the value is the first element of the tuple.

To customise the label you can pass the ``get_label`` argument to the decorator:

.. code-block:: python

    @server_choices(
        ['field2]
        get_label=lambda registry, item: f"Item: {str(item)}",
    )
    class MyForm(ModelForm):
        ...

.. note::
    The ``registry`` argument is the :class:`~alliance_platform.server_choices.class_handlers.base.ServerChoicesFieldRegistration`
    instance, and is passed through to most of the methods you can override.

Permissions
===========

When the endpoint is used to get the available choices permission checks are always applied. You can control what permission is
used by passing the :code:`perm` kwarg. If not specified and the django Model can be inferred from the decorated
class (eg. when using a :class:`~rest_framework.serializers.ModelSerializer`, :class:`~django.forms.ModelForm` or
:class:`~django_filters.filterset.FilterSet`) then the :code:`create` permission for that model as returned by
:func:`~alliance_platform.core.auth.resolve_perm_name` will be used.

For example if you had a :code:`ModelForm` for the model :code:`User` which had foreign keys to :code:`Address`
and :code:`Group` then the choices for both models would be the :code:`create` permission on :code:`User`. The
rationale for this is if you weren't using server_choices and rendering the form directly there would be no specific
check on the foreign key form fields - all the options would be embedded directly in the returned HTML. Using
:code:`create` means if you can create the main record you can see the options for each field you need to save on
that record. Note that the only information exposed about the related is the :code:`pk` and a label for it - you
can't access all the data from it.

For choice fields not associated with a model you must explicitly define the permission to use.


Serialized value
================

If you are using the default frontend widgets you will not need to customise the serialized value. If using a custom
implementation it may be necessary to change how the values are returned from the API endpoint. The default implementation
returns each choice as a dictionary with a ``label`` and ``value`` key:

.. code-block:: json

    {
        "label": "Item: 1",
        "value": 1
    }

You can change the key names by passing the ``label_field`` and ``value_field`` arguments
to the decorator:

.. code-block:: python

    @server_choices(
        ['field2]
        label_field="name",
        value_field="id",
    )
    class MyForm(ModelForm):
        ...

which would return:

.. code-block:: json

    {
        "name": "Item: 1",
        "id": 1
    }

You can also pass ``serialize`` to completely override the serialization process. This method needs to handle a single
value, or an iterable of values. The exact implementation will depend on the choices you are using, but if dealing with
a django model you might do something like:

.. code-block:: python

    def serialize(registry, item, request):
        if isinstance(item, MyRecord):
            return {"id": item.pk, "name": str(item), "len": len(str(item))}
        return [serialize(registry, item, request) for item in item]

    @server_choices(
        ['field2]
        serialize=serialize,
    )
    class MyForm(ModelForm):
        ...


Frontend Widgets
================

Django
------

The :class:`default widget <alliance_platform.server_choices.class_handlers.form.ServerChoicesSelectWidget>` renders the component `ServerChoicesInput <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/form-serverchoicesinput--docs>`_.
This is used when decorating a Django form or filterset.

.. note

  The default widget assumes you have ``alliance_platform_frontend`` installed and configured.

  To change the default input you can override the template ``alliance_platform/server_choices/widgets/server_choices_select_widget.html``

You can pass through extra arguments via the widget. For example, say you want to further refine choices based on a
query parameter - we can pass that as an attribute to the widget.

.. code-block:: python

    def get_pizza_choices(registration, request):
        current_instance_id = request.query_params.get("currentInstanceId")
        if current_instance_id:
            return Pizza.objects.filter(name__icontains=query, pk=current_instance_id)
        return Pizza.objects.filter(name__icontains=query)

    @server_choices(["pizza"], search_fields=["name"], get_choices=get_pizza_choices)
    class PizzaItemForm(ModelForm):
        class Meta:
            model = PizzaItem
            fields = [
                "pizza",
                "restaurant",
                "price",
            ]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.instance:
                self_fields["pizza"].widget_attrs_update(query={"currentInstanceId": self_instance_pk})

Here ``currentInstanceId`` will come through as a query parameter. The ``get_choices`` method can retrieve this from the request
and do whatever is needed with it.

The widget is assigned automatically when the decorator is used, but you can also instantiate it directly to pass different attributes to it:

.. code-block:: python

  @server_choices(["pizza"]) 
  class PizzaItemForm(ModelForm):                                                   
      restaurant = models.ModelChoiceField(widget=ServerChoicesSelectWidget())

      class Meta:                                                                   
          model = PizzaItem                                                         
          fields = [                                                                
              "restaurant",                                                         
          ]                                                                         


DRF / React
-----------

When a DRF `Serializer` is decorated the widget that makes use of the choices is assumed to be rendered from React. This is usually done 
in conjuction with a Presto ViewModel that has been codegen'd. The codegen takes care of extracting the necessary details for the ``AsyncChocies``
definition onthe frontend. You can then use the `FormField <https://main--64894ae38875dcf46367336f.chromatic.com/?path=/docs/form-formfield--docs#async-choices>`__
component to render the widget to fetch the choices.


API Endpoint
============

Once a field has been registered the following applies:

1. :class:`~alliance_platform.server_choices.views.ServerChoicesView` will serve up the choices for this registration based on the registered name and field. 
   Permissions are checked according to the ``perm`` property. See :class:`~alliance_platform.server_choices.register.ServerChoiceFieldRegistration` for      
   more details.

2. Presto codegen will use this registration when creating the base ViewModel classes for classes decorated with
   :meth:`~codegen.presto.decorator.view_model_codegen`

In order for :class:`~alliance_platform.server_choices.views.ServerChoicesView` to know what to return a unique name is
generated as part of the registration for the class being registered. This is hashed to avoid exposing application
structure to the frontend. This name, along with the specific field name on that class, is passed when calling
:class:`~alliance_platform.server_choices.views.ServerChoicesView` which it then uses to look up in the global registry to
get the relevant registration instance.
