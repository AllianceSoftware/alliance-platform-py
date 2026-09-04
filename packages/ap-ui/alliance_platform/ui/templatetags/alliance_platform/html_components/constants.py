from __future__ import annotations

ALLOWED_COMPONENTS_KWARG = "allowed_components"

#: Kwarg accepting a dict of props to apply in bulk, e.g. ``{% ui "text_input" props=widget.attrs %}``
BULK_PROPS_KWARG = "props"

RESERVED_DISPATCHER_KWARGS = frozenset({ALLOWED_COMPONENTS_KWARG, BULK_PROPS_KWARG})
