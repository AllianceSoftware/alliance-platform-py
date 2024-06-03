API
=============================================

Javascript Post Processors
**************************

.. _js-post-processors:

To specify the post processors in settings, see the :ref:`codegen configuration section <codegen-configuration>`.

Here is an example of how to use the Prettier and Eslint post processors:

.. code-block:: python

    from alliance_platform.frontend.util import guess_node_path
    from django.conf import settings

    PROJECT_DIR = settings.PROJECT_DIR
    NODE_PATH = guess_node_path(PROJECT_DIR / ".nvmrc") or "node"
    NODE_MODULES_DIR = PROJECT_DIR / "node_modules"

    post_processors = [
        PrettierPostProcessor(
            NODE_PATH,
            NODE_MODULES_DIR,
            prettier_config=PROJECT_DIR / "config/prettier.config.js",
        ),
        EslintFixPostProcessor(
            NODE_PATH,
            NODE_MODULES_DIR,
            plugins=["simple-import-sort"],
            rules={
                "simple-import-sort/imports": [
                    "error",
                    {
                        # Keep in sync with config/eslintrc.cjs.
                        "groups": [
                            ["^\\u0000[^.]"],
                            ["^@?\\w"],
                            ["^"],
                            ["^\\."],
                            ["^.+\\.less$"],
                        ],
                    },
                ],
            },
        ),
    ]

.. automodule:: alliance_platform.codegen.post_processors.js
    :members:
    :member-order: bysource

Typescript Codegen
******************

These modules provide support for generating Typescript sourcecode in
a declarative way.

For example::

    printer = TypescriptPrinter()
    printer.print(
        FunctionDeclaration(
            Identifier("renderButton"),
            [Parameter(Identifier("container")), Parameter(Identifier("props"))],
            [VariableDeclaration([VariableDeclarator(Identifier("name"), "Gandalf")], "const")],
            [ExportKeyword(is_default=True), AsyncKeyword()],
        )
    )

    > export default async function renderButton(container, props) {
    >   const name = "Gandalf";
    > }

Nodes
-----

.. _typescript-nodes:

.. automodule:: alliance_platform.codegen.typescript
    :members:

Printer & Source File Writer
----------------------------

.. autoclass:: alliance_platform.codegen.printer.TypescriptPrinter
    :members:

.. autoclass:: alliance_platform.codegen.printer.TypescriptSourceFileWriter
    :members:

