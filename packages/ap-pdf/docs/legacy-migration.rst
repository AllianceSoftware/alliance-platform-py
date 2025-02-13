Legacy Migration
----------------

These instructions can be used to migrate a project using the legacy ``common_pdf`` package to ``alliance_platform_pdf``.

The structure of the package has not been changed, so to migrate simply:

* Find and replace all imports from ``common_pdf`` to ``alliance_platform.pdf``

* Set :py:attr:`~alliance_platform.pdf.settings.AlliancePlatformPDFSettingsType.WHITELIST_DOMAINS`
  to the current value for ``COMMON_PDF_WHITELIST_DOMAINS``, and remove the latter environmental variable.
