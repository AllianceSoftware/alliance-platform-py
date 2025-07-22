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


.. warning::

  Only ``psycopg`` is supported - if you are using ``psycopg2`` you will need to upgrade.

Settings
~~~~~~~~

The ordered model package has no settings.

Usage
~~~~~

For usage see the :class:`~alliance_platform.ordered_model.models.OrderedModel` documentation.
