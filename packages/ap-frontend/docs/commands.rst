Management commands
===================

``extract_frontend_resources``
----------------------------

.. django-manage:: extract_frontend_resources

Extracts the resources used in any template.

This works with any template nodes that extend :class:`~alliance_platform.frontend.bundler.context.BundlerAsset`. All templates
in the system are loaded to gather all used resources. You can exclude specific directories by setting
:data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.EXTRACT_ASSETS_EXCLUDE_DIRS`
to either a :class:`pathlib.Path` or ``re.Pattern``.

Outputs a valid JSON dump with the following keys:

- ``resources`` - a list of resources used in templates. The exact shape depends on the specific resource :class:`~alliance_platform.frontend.bundler.frontend_resource.FrontendResource.serialize`
  method. Examples are shown below.
- ``breakdown`` - a breakdown of where each resource was found. This is useful when debugging.
- ``breakdown.registry`` - a list of all the resources that were added via the :class:`~alliance_platform.frontend.bundler.resource_registry.FrontendResourceRegistry`.
- ``breakdown.templates`` - An object, where each key is a path to a template, and the value the list of resource paths found
  in that template.

.. code-block:: json

    {
        "resources": [
            {
                "type": "esmodule",
                "path": "@internationalized/date",
                "importName": "CalendarDate",
                "isDefaultImport": false
            },
            {
                "type": "esmodule",
                "path": "/path/to/project/frontend/src/auth/SessionExpiredModal.tsx",
                "importName": "SessionExpiredModal",
                "isDefaultImport": true
            },
            {
                "type": "css",
                "path": "/path/to/project/styles/admin/crud.css.ts"
            },
            {
                "type": "image",
                "path": "/path/to/project/logo.png"
            },
        ]
        "breakdown": {
            "registry": [
                "/path/to/project/frontend/src/models/AuthUser.ts",
                "/path/to/project/node_modules/@internationalized/date",
                "/path/to/project/node_modules/@prestojs/viewmodel"
            ],
            "templates": {
                "/Users/dave/Development/internal/alliance-platform/alliance-platform-py/packages/ap-frontend/alliance_platform/frontend/templates/alliance_platform/ui/labeled_input_base.html": [
                    "/path/to/project/node_modules/@alliancesoftware/ui"
                ],
                "/path/to/project/django-root/common_crud/templates/breadcrumbs.html": [
                    "/path/to/project/styles/admin/breadcrumbs.css.ts"
                ],
           }
        }
    }


.. django-manage-option:: --output FILE_PATH

Path to write JSON output to. If not provided, output is written to stdout.

.. django-manage-option:: --quiet

Don't output anything

``extract_frontend_assets``
----------------------------

.. django-manage:: extract_frontend_assets

.. warning:: Deprecated in favour of :djmanage:`extract_frontend_resources`

Works like :djmanage:`extract_frontend_resources`, but only outputs the file paths used without any
details. For example, ES Module usage would give you only the file path, and not the specific imports
used which means the bundler cannot optimise usage.
