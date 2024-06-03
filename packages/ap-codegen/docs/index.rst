Alliance Platform Codegen
=============================================

This package provides tools to generate code, currently only TypeScript, but eventually may include Python.

The purpose is to provide the tools to generate code in a safe and consistent manner, avoiding manually constructing strings
which can be error-prone and difficult to maintain.

It can be used at runtime, for generating small amounts of code, for example to provide an entry point for rendering
a component in a template. This is used by the :ttag:`component` tag.

It can also be used at build time (e.g. while developing) to generate larger amounts of code, for example to generate
some typescript code that should always be in sync with the server-side code.

TODO: Artifacts / codegen registry documentation


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   codegen_registry
   settings
   api

.. include:: ../../ap-core/docs/_sidebar.rst.inc
