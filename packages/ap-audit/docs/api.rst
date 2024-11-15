API
=============================================


Audit decorator
***************

.. autofunction:: alliance_platform.audit.create_audit_model_base

Events
******

.. autoclass:: alliance_platform.audit.events.PatchedEvent
.. autoclass:: alliance_platform.audit.events.AuditSnapshot
.. autofunction:: alliance_platform.audit.events.create_event

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

.. autofunction:: alliance_platform.audit.templatetags.alliance_platform.audit.render_audit_list
