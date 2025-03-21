Installation
------------

Install the ``alliance_platform.audit`` package:

.. code-block:: bash
    poetry add alliance_platform.audit

Add ``pgtrigger``, ``pghistory``, and ``alliance_platform.audit`` to your ``INSTALLED_APPS``. If migrating from ``common_audit``, ``pgtrigger`` and
``pghistory`` will already be in ``installed_apps``, and ``alliance_platform.audit`` should replace ``common_audit``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'pgtrigger',
        'pghistory',
        'alliance_platform.audit',
        ...
    ]

* Add :class:`alliance_platform.audit.middleware.AuditMiddleware` to ``MIDDLEWARE``

* In ``urls.py``, add paths for :class:`alliance_platform.audit.api.AuditLogView` and :class:`alliance_platform.audit.api.AuditUserChoicesView`.

Frontend
~~~~~~~~

If you want to use the pre-made audit log component (built off of ``@alliancesoftware/ui``), you will need
to add ``@alliancesoftware/ui-audit`` to your ``package.json``. By default, the :ttag:`render_audit_list`
templatetag looks in this package to import the audit log component to display.

If you want to write your own audit log component, you can use the ``useAuditEndpoint`` hook from
``@alliancesoftware/ui-audit`` to help interface between your component and the audit log endpoint.
This will work out of the box with the props passed from the :ttag:`render_audit_list` template tag.

Audit Template Tags
~~~~~~~~~~~~~~~~~~~

To use the audit list templatetags, you need to install :doc:`alliance_platform.frontend <alliance-platform-frontend:installation>` and add it to ``INSTALLED_APPS``.

You will also need to ensure that the :data:`~alliance_platform.audit.settings.AlliancePlatformAuditSettingsType.AUDIT_LOG_COMPONENT_PATH` setting points to a React component that will render
the audit log that accepts the args expected in the :ttag:`render_audit_list`
templatetag. By default, this will assume you have the ``@alliancesoftware/ui-audit`` package installed, and will
render ``@alliancesoftware/ui-audit/AuditLog``.

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
