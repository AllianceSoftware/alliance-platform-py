Usage
#####

To add audit tracking to a model, add the :func:`~alliance_platform.audit.with_audit_model` decorator to the model class:

.. code-block:: python

    @with_audit_model()
    class Foo(models.Model):
        class Meta(NoDefaultPermissionsMeta):
            db_table = "xenopus_frog_foo"

At a lower level, this will create a new model called :code:`FooAuditEvent` that inherits from a base audit class
(generated using :meth:`~alliance_platform.audit.create_audit_model_base`). The :code:`AuditEvent` model has a copy of
every field that is being audited and is written to automatically whenever the source model changes.
The event model itself has migrations as it is just a standard django model. The triggers are handled
by :code:`pgtrigger` and will be updated automatically whenever :code:`migrate` is run.

If you need more control over the generated audit model, you can use
:func:`~alliance_platform.audit.create_audit_model_base` directly to generate the base class, and manually create the
audit event model as a separate model definition, e.g.:

.. code-block:: python

    class Foo(models.Model):
        class Meta(NoDefaultPermissionsMeta):
            db_table = "xenopus_frog_foo"


    class FooAuditEventTracker(create_audit_model_base(Foo)):
        class Meta:
            db_table = "xenopus_frog_foo_auditeventtracker"


Arguments to the :func:`~alliance_platform.audit.with_audit_model` decorator are passed through to
:func:`~alliance_platform.audit.create_audit_model_base`, so the following example will create an
audit model for :code:`User` that excludes two fields from tracking, and registers 2 manual events.

.. code-block:: python

    @with_audit_model(
        exclude=["password", "last_login"],
        manual_events=["LOGIN", "LOGOUT"]
    )
    class User(BaseUser):
        ...

To use the manual events call :func:`~alliance_platform.audit.create_audit_event`:

.. code-block:: python

    def track_login(sender, user, **kwargs):
        create_audit_event(user, "LOGIN")

Any audit events that occur within a non-GET request will automatically be wrapped in pghistory :external:class:`~pghistory.context`. :code:`GET`
requests shouldn't generally modify anything and so the default :class:`~alliance_platform.audit.middleware.AuditMiddleware` doesn't
wrap these in :code:`context`. You can do it manually however:

.. code-block:: python

    def track_logout(sender, user, **kwargs):
        with pghistory.context(user=user.pk):
            create_audit_event(user, "LOGOUT")

You can also add extra context by nesting :code:`context` calls - they get merged together:

.. code-block:: python

    with pghistory.context(job="Cron"):
        with pghistory.context(foo="bar"):
            record.save()
    # Context will be saved with:
    # {'foo': 'bar', 'job': 'Cron'}

The :ttag:`render_audit_list` can be used to render the audit log React
component defined by the :data:`~alliance_platform.audit.settings.AlliancePlatformAuditSettingsType.AUDIT_LOG_COMPONENT_PATH` setting.

.. code-block:: html

    {% load alliance_platform.audit %}
    {% render_audit_list object=record view_type="modal" %}

The above should render a button that opens a modal and shows audit activity for the specified record.

.. code-block:: html

    {% render_audit_list model="all" limit_to_user=user.pk title="User Activity" %}

This should show all audit activity (for any model), but limited to events triggered by the specified user.

Implementation Details & Limitations
####################################

Model Changes
=============

* If fields change on the source model then they will also change in the audit event model. For example if you remove the field :code:`address1` from the :code:`Address` model then it will also be removed from the audit event :code:`AddressEvent` meaning any historical values for that record will be lost.
* Renaming a field will rename on both the source model and destination model; this is the standard behaviour of django migrations so make sure it's doing what you expect (eg. renaming instead of removing and adding the new field).
* If you add a new field to a model that requires a one off default in a migration you will also need to do the same for the audit event change (:code:`makemigrations` will prompt you for both individually).

Deleting Models with Many to Many Relations
===========================================

When deleting a model that has an audited many-to-many field you must do it in two steps:

1) Delete the many-to-many field first and run ``make_migrations``
2) Delete the model and run ``make_migrations`` again

If the migration is created as single step then you will see an error when running migrate that looks like::

    django.db.migrations.exceptions.InvalidBasesError: Cannot resolve bases for [<ModelState: '<proxy model name>'>]

You can optionally concatenate the two migrations into a single migration file so long as the order is
preserved.

Multi-table inheritance
=======================

For models with multi-table inheritance (eg. :code:`AdminProfile` inherits from :code:`User`) you must audit each model
individually. For example if :code:`AdminProfile` wants to audit :code:`email` which is defined on :code:`User` then
:meth:`~alliance_platform.audit.create_audit_model_base` will throw an error if that field isn't audited on :code:`User`.

Under the hood changes to each model are tracked individually. So if a save would write to both tables then there will
be 2 events written. The provided UI will show events from both tables when you call :ttag:`render_audit_list`
on the descendant model.

Caution: while Audit module allows you to add the same manual event to multi table inheritance models, you should be
careful on which instance to supply to :meth:`~alliance_platform.audit.create_audit_event`. By default the instance supplied will always take the highest
priority, then one of its parents will catch the event and log it there: there's no propagation.

Managing Triggers
=================

The postgres triggers are automatically installed and kept up to date when you run migrations. Note that triggers
are not included in your migration files - they are always sync'd whenever the migration command is run.

You can run ``./manage.py pgtrigger ls`` at any time to see the status of all triggers.
