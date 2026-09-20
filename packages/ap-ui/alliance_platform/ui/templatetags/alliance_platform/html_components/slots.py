from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from typing import Iterator
from typing import cast

from django.template import Context

from .constants import UI_SLOT_CONTEXT_KEY

SlotProps = dict[str, Any]
SlotContext = dict[str, SlotProps]


def get_slot_context(context: Context) -> SlotContext:
    value = context.get(UI_SLOT_CONTEXT_KEY, {})
    if not isinstance(value, dict):
        return {}
    return cast(SlotContext, value)


def merge_slot_props(slot_props: SlotProps | None, child_props: SlotProps) -> SlotProps:
    slot_props = slot_props or {}
    merged = {**slot_props, **child_props}

    slot_class_name = slot_props.get("className")
    child_class_name = child_props.get("className")
    if slot_class_name and child_class_name:
        merged["className"] = f"{slot_class_name} {child_class_name}"

    return merged


@contextmanager
def push_slot_scope(context: Context, slots: SlotContext) -> Iterator[None]:
    existing = get_slot_context(context)
    next_slots = {**existing, **slots}
    with context.push(**{UI_SLOT_CONTEXT_KEY: next_slots}):
        yield
