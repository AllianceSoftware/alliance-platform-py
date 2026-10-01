from .dispatcher import parse_ui_tag
from .registry import HtmlUIComponentRegistry
from .registry import built_in_registry
from .registry import register_component

__all__ = [
    "HtmlUIComponentRegistry",
    "built_in_registry",
    "parse_ui_tag",
    "register_component",
]
