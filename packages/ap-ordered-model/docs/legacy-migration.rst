Legacy Migration
----------------

These instructions can be used to migrate a project using the legacy ``common_lib.ordered_model`` package to ``alliance_platform_ordered_model``.

All that should be required is to replace any imports from ``common_lib.models`` with imports from ``alliance_platform.ordered_model.models``.

.. note::

    At present the ``ordered_model`` package has no settings, and does not depend on any other Alliance Platform packages.
