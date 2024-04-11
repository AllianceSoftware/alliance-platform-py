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

.. automodule:: alliance_platform.codegen.typescript
    :members:

Printer & Source File Writer
----------------------------

.. autoclass:: alliance_platform.codegen.printer.TypescriptPrinter
    :members:

.. autoclass:: alliance_platform.codegen.printer.TypescriptSourceFileWriter
    :members:

