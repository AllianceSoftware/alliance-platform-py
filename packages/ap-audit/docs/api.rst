API
=============================================


Audit decorator
***************

.. autofunction:: alliance_platform.audit.create_audit_model_base
.. autofunction:: alliance_platform.audit.with_audit_model

Events
******

.. autoclass:: alliance_platform.audit.events.PatchedEvent
.. autoclass:: alliance_platform.audit.events.AuditSnapshot
.. autofunction:: alliance_platform.audit.events.create_event
.. autofunction:: alliance_platform.audit.create_audit_event

Views
*****

.. autoclass:: alliance_platform.audit.api.AuditLogView

    .. automethod:: get_single_queryset
    .. automethod:: get_multiple_queryset
    .. automethod:: get_queryset

.. autoclass:: alliance_platform.audit.api.AuditUserChoicesView

.. autoclass:: alliance_platform.audit.api.EventUnion
    :members:

Registry
********

.. autoclass:: alliance_platform.audit.registry.AuditRegistry
    :members:

Search
******

.. autofunction:: alliance_platform.audit.search.search_audit_by_context

Middleware
**********

.. autoclass:: alliance_platform.audit.middleware.AuditMiddleware


Templatetags
************

.. templatetag:: render_audit_list

``render_audit_list``
---------------------

Renders an audit log list in one of three modes:

- supply :code:`model` but not :code:`pk`, and model is not :code:`all`:

  renders a table that lists all events related to all instances of ``model``

- supply :code:`model="all"`:

  renders a table that lists all changes accessible by user across all audited models

- supply :code:`model` with :code:`pk`, or :code:`object`:

  renders a table that lists only events recorded for that object

Requires ``alliance_platform.frontend`` to be installed, and the :data:`~alliance_platform.audit.settings.AlliancePlatformAuditSettingsType.AUDIT_LOG_COMPONENT_PATH` to
point to a react component in your frontend source folder that renders the audit log component.


================= =============================================================
Argument          Description
================= =============================================================
``context``       django context for the purpose of accessing user. provided by default.
``model``         the string name of a model either being "all" or in the format of ``app.model`` eg ``admin.user``
``object``        an instance of object being audited, if you have one,
``pk``            or the object's pk (use in conjuration with ``model``) if you don't have the instance
``registry``      registry to use. you most likely don't need to touch this one.
``limit_to_user`` restrict events to only those made by the user, where supplied user is either the actor or hijacker
``**kwargs``      Any other props to pass through to the audit component
================= =============================================================
