from typing import Any


def add_auto_attach_marker(root_attrs: dict[str, Any], runtime_name: str) -> None:
    """Mark a static component root for its collected external auto-attach runtime.

    The value is a token list so a root can opt into more than one small runtime without one
    renderer overwriting another marker.
    """

    tokens = str(root_attrs.get("data-apui-attach") or "").split()
    if runtime_name not in tokens:
        tokens.append(runtime_name)
    root_attrs["data-apui-attach"] = " ".join(tokens)
