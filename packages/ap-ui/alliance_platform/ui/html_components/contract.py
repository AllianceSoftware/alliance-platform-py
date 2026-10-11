"""The versions of the npm packages' static contract that the static renderers support.

The static renderers emit markup for a DOM and CSS contract defined by ``@alliancesoftware/ui`` and
``@alliancesoftware/icons``: the data attributes and part classes their styles and runtimes key off,
the runtime tokens and the layout of the static SVG icons. Each package records the version of its
side of the contract as an integer ``version`` in ``static-contract.json`` at its root, bumped only
when that contract changes; it is not the npm version.
:func:`~alliance_platform.ui.checks.check_static_contract` compares the installed packages' versions
with :data:`SUPPORTED_STATIC_CONTRACT_VERSIONS`.
"""

#: The file at the root of each package that holds its static contract version
STATIC_CONTRACT_FILE = "static-contract.json"

#: The static contract version of each npm package that the static renderers are written for
SUPPORTED_STATIC_CONTRACT_VERSIONS = {"@alliancesoftware/ui": 1, "@alliancesoftware/icons": 1}
