from django import template
from django.template import Context
from django.template import Library

from ..templatetags.react import ComponentNode
from ..templatetags.react import ComponentProps
from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


class LabeledInputNode(ComponentNode):
    def resolve_props(self, context: Context) -> ComponentProps:
        values = super().resolve_props(context)
        # LabeledInput doesn't support validationState, it only handles ``isInvalid`` so convert it here
        validation_state = values.pop("validationState", "")
        if validation_state == "invalid":
            values.update({"isInvalid": True})
        return values


def labeled_input(parser: template.base.Parser, token: template.base.Token):
    """
    Render ``LabeledInput``.

    For compatability with ``form_input`` it will convert ``validationState="invalid"`` into ``isInvalid=True``.
    """
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "LabeledInput", False, parser.origin),
        node_class=LabeledInputNode,
    )


def register_labeled_input(register: Library):
    register.tag("LabeledInput")(labeled_input)
