Installation
------------

Install the ``alliance_platform_ordered_model`` package:

.. code-block:: bash
    poetry add alliance_platform.ordered_model

Add ``pgtrigger`` and ``alliance_platform.ordered_model`` to your ``INSTALLED_APPS``. If migrating from ``common_lib``, ``pgtrigger`` will already
be in ``installed_apps``.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.ordered_model',
        'pgtrigger',
        ...
    ]


Settings
~~~~~~~~

The ordered model package has no settings.
