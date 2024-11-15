Installation
------------

Install the ``alliance_platform.audit`` package:

.. code-block:: bash
    poetry add alliance_platform.audit

Add ``pgtrigger``, ``pghistory``, and ``alliance_platform.audit`` to your ``INSTALLED_APPS``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'pgtrigger',
        'pghistory',
        'alliance_platform.audit',
        ...
    ]

* Add :class:`alliance_platform.audit.middleware.AuditMiddleware` to :setting:`MIDDLEWARE`

* In ``urls.py``, add paths for :class:`alliance_platform.audit.api.AuditLogView` and :class:`alliance_platform.audit.api.AuditUserChoicesView`.

Audit Template Tags
~~~~~~~~~~~~~~~~~~~

To use the audit list templatetags, you need to install `alliance_platform.frontend <http://127.0.0.1:56676/>`__ and add it to ``INSTALLED_APPS``.

You will also need to ensure that the ``AUDIT_LOG_COMPONENT_PATH`` setting points to a React component that will render
the audit log that accepts the args expected in the :func:`~alliance_platform.audit.templatetags.audit.render_audit_list`
templatetag. By default, this will expect the component to be defined in ``audit/AuditLog``.


Other settings
~~~~~~~~~~~~~~

All settings are optional, so you can omit this if the defaults are satisfactory.

In the settings file:

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.audit.settings import AlliancePlatformAuditSettingsType

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        AUDIT: AlliancePlatformAuditSettingsType
        # Any other settings for alliance_platform packages, e.g. FRONTEND

    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "AUDIT": {
            "LIST_PERM_ACTION": "audit",
            "TRACK_IP_ADDRESS": True,
        },
    }
