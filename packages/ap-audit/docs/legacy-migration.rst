Legacy Migration
----------------

These instructions can be used to migrate a project using the legacy ``common_audit`` package to ``alliance_platform_audit``.

The only structural change to the repository is that the :ttag:`render_audit_list`
templatetag has been namespaced under ``alliance_platform.audit``.

Install the ``alliance_platform_audit`` package as per the :doc:`installation instructions <installation>`.

.. note::

    If this is an older project that is not using the published ``alliance_platform`` packages at all you will need to
    add the following to ``settings/base.py`` (at minimum) if no ``ALLIANCE_PLATFORM`` setting already exists::

        ALLIANCE_PLATFORM = {
            "CORE": {"PROJECT_DIR": PROJECT_DIR},
        }

Follow these steps:

* Delete the ``common_audit`` app entirely from ``django-root``, and remove it from ``INSTALLED_APPS``.
* Replace any imports from ``common_audit.templatetags.audit`` with imports from ``alliance_platform.audit.templatetags.alliance_platform.audit``.
* Replace all other imports from ``common_audit`` with imports from ``alliance_platform.audit``.
* Replace instances of ``{% load audit %}`` in Django templates with ``{% load alliance_platform.audit %}``
* Replace ``common_audit`` with ``alliance_platform_audit`` in ``PermissionMatrix.csv``

Frontend
~~~~~~~~

The :ttag:`render_audit_list` templatetag is designed to be used with the ``@alliancesoftware/ui-audit/AuditLog``
component by default. However, the ``audit/AuditLog.tsx`` component is (as of writing) still compatible
with the templatetag. If you wish to continue using the audit log component defined in your project,
make sure to set the :data:`~alliance_platform.audit.settings.AlliancePlatformAuditSettingsType.AUDIT_LOG_COMPONENT_PATH` to ``"audit/AuditLog"`` so the templatetag will
continue to render your project-specific audit log component.

You can also import ``useAuditEndpoint`` from ``@alliancesoftware/ui-audit`` to write your own audit
component, or integrate it into your existing audit component.
