from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Iterator
from typing import TypeVar
from typing import cast

from django.template import Context

_RENDER_STATE_KEY = "alliance_platform_ui_render_state"

T = TypeVar("T")


@dataclass(frozen=True)
class ChildReport:
    """Structured facts published by a rendered component to its direct parent."""

    component: str
    html: str
    slot: str | None = None
    plain_text: str | None = None


@dataclass
class RenderFrame:
    """One component or inherited-default scope in the current document render."""

    component: str | None = None
    payload: object | None = None
    slots: dict[str, dict[str, Any]] | None = None
    collect_child_reports: bool = False
    child_reports: list[ChildReport] = field(default_factory=list)


@dataclass
class DocumentRenderState:
    frames: list[RenderFrame] = field(default_factory=list)
    id_counter: int = 0
    id_claims: dict[str, int] = field(default_factory=dict)


def get_document_render_context(context: Context) -> dict[str, Any]:
    """Return the render-context layer shared by the root template and isolated includes."""

    return cast(dict[str, Any], context.render_context.dicts[0])


def get_document_render_state(context: Context) -> DocumentRenderState:
    document_context = get_document_render_context(context)
    state = document_context.get(_RENDER_STATE_KEY)
    if state is None:
        state = DocumentRenderState()
        document_context[_RENDER_STATE_KEY] = state
    return cast(DocumentRenderState, state)


@contextmanager
def push_render_frame(context: Context, frame: RenderFrame) -> Iterator[RenderFrame]:
    frames = get_document_render_state(context).frames
    frames.append(frame)
    try:
        yield frame
    finally:
        popped = frames.pop()
        assert popped is frame


def get_current_component_frame(context: Context) -> RenderFrame | None:
    for frame in reversed(get_document_render_state(context).frames):
        if frame.component is not None:
            return frame
    return None


def find_render_payload(context: Context, payload_type: type[T]) -> T | None:
    """Return the nearest typed parent payload in the render frame stack."""

    for frame in reversed(get_document_render_state(context).frames):
        if isinstance(frame.payload, payload_type):
            return frame.payload
    return None


@contextmanager
def collect_child_reports(context: Context) -> Iterator[list[ChildReport]]:
    frame = get_current_component_frame(context)
    if frame is None:
        raise RuntimeError("Child reports can only be collected while rendering a component")
    previous_collect = frame.collect_child_reports
    previous_reports = frame.child_reports
    reports: list[ChildReport] = []
    frame.collect_child_reports = True
    frame.child_reports = reports
    try:
        yield reports
    finally:
        frame.child_reports = previous_reports
        frame.child_reports.extend(reports)
        frame.collect_child_reports = previous_collect


def report_child(context: Context, report: ChildReport):
    """Publish to a collecting direct component parent.

    Non-component frames (such as slot scopes) are transparent. The first component frame is a
    hard boundary, which prevents reports leaking through an intermediate component.
    """

    frame = get_current_component_frame(context)
    if frame is not None and frame.collect_child_reports:
        frame.child_reports.append(report)


def generate_html_id(context: Context, prefix: str) -> str:
    state = get_document_render_state(context)
    state.id_counter += 1
    return f"{prefix}-{state.id_counter}"


def claim_html_id(context: Context, preferred_id: str) -> str:
    state = get_document_render_state(context)
    count = state.id_claims.get(preferred_id, 0) + 1
    state.id_claims[preferred_id] = count
    return preferred_id if count == 1 else f"{preferred_id}-{count}"
