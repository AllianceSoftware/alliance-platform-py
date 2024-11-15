Alliance Platform Audit
=============================================

This package introduces support for auditing models using postgres triggers. Trigger support and history tracking is
provided by `django-pgtrigger <https://django-pgtrigger.readthedocs.io/en/latest/>`_ and `django-pghistory <https://django-pghistory.readthedocs.io/en/latest/>`_.
:meth:`~alliance_platform.audit.audit.create_audit_model_base` extends this to provide better handling of many to many fields and
extended models as well as hooks for rendering the UI for viewing data (including permission checks). Because triggers
are used changes that occur from anywhere (including postgres directly) are automatically tracked.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   settings
   legacy-migration
   usage
   api

.. include:: ../../ap-core/docs/_sidebar.rst.inc
