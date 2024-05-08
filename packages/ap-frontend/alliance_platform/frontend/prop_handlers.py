from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING
from typing import Any

from alliance_platform.codegen.typescript import ArrayLiteralExpression
from alliance_platform.codegen.typescript import Identifier
from alliance_platform.codegen.typescript import ImportSpecifier
from alliance_platform.codegen.typescript import NewExpression
from alliance_platform.codegen.typescript import convert_to_node
from django.template import Context
from django.utils.timezone import is_aware

from .bundler.ssr import SSRCustomFormatSerializable
from .bundler.ssr import SSRSerializerContext

if TYPE_CHECKING:
    from .templatetags.react import ComponentNode
    from .templatetags.react import ComponentSourceCodeGenerator


class CodeGeneratorNode:
    def generate_code(self, generator: ComponentSourceCodeGenerator):
        raise NotImplementedError()

    def convert_unknown(self, value, generator: ComponentSourceCodeGenerator):
        if isinstance(value, CodeGeneratorNode):
            return value.generate_code(generator)

    def convert_to_node(self, value, generator: ComponentSourceCodeGenerator):
        return convert_to_node(value, convert_unknown=lambda value: self.convert_unknown(value, generator))


class ComponentProp(SSRCustomFormatSerializable, CodeGeneratorNode):
    """
    Represents a prop that requires special conversion to generate the code and perform server side rendering.

    Simple props like strings, numbers, lists and dicts can all be converted automatically to the corresponding
    types in javascript. This works automatically as a) the code generator knows how to convert these types and
    b) they are JSON serializable so can be sent to the SSR server without any extra processing.

    Anything more complex than this needs to be handled by a custom prop handler. There are two parts to this:

    1) Implement ``generate_code`` to generate the typescript code that will be embedded in a <script> tag when
       ``ComponentNode`` is rendered.

    2) Implement ``get_tag`` and ``get_representation`` to return a JSON serializable representation of the prop that
       can then be revived on the frontend.

    A concrete example is ``DateProp``. This will generate code like::

        new Date("2020-01-01")

    such that the prop passed to the component is a ``Date`` instance. The ``get_representation`` method will return
    the string representation `"2020-01-01"` and ``get_tag`` returns ``"Date"``. This gets serialized to
    ``["@@CUSTOM", "Date", "2020-01-01"]``. The ``@@CUSTOM`` tag is used to indicate that the prop needs special "reviving"
    on the frontend which is detected by ``processSSRRequest`` in ``ssr.ts``, and will call the appropriate "reviver"
    defined in ``ssrJsonRevivers.tsx``.
    """

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        """Return ``True`` if this prop handler should be used for the given value."""
        raise NotImplementedError(f"should_apply not implemented for {cls.__name__}")

    def __init__(self, value: Any, node: ComponentNode, context: Context):
        """Intentionally blank; each implementation can handle this differently."""
        pass


class DateProp(ComponentProp):
    """Convert a python date or datetime to a js Date"""

    value: datetime.date

    def __init__(self, value, *args, **kwargs):
        super().__init__(value, *args, **kwargs)
        self.value = value
        self.js_args = [self.value.year, self.value.month, self.value.day]

    def get_tag(self):
        return "Date"

    def get_representation(self, context):
        return self.js_args

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        calendar_date = generator.resolve_prop_import(
            "frontend/src/re-exports.tsx", ImportSpecifier("CalendarDate")
        )
        return NewExpression(calendar_date, self.js_args)

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)


class DateTimeProp(ComponentProp):
    """Convert a python datetime"""

    value: datetime.datetime

    def __init__(self, value, *args, **kwargs):
        super().__init__(value, *args, **kwargs)
        self.value = value
        self.js_args = [
            self.value.year,
            self.value.month,
            self.value.day,
            self.value.hour,
            self.value.minute,
            self.value.second,
            self.value.microsecond,
        ]

    def get_tag(self):
        return "DateTime"

    def get_representation(self, context):
        return self.js_args

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        calendar_date = generator.resolve_prop_import(
            "frontend/src/re-exports.tsx", ImportSpecifier("CalendarDateTime")
        )
        return NewExpression(
            calendar_date,
            self.js_args,
        )

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        return isinstance(value, datetime.datetime) and not is_aware(value)


class ZonedDateTimeProp(ComponentProp):
    """Convert a python datetime"""

    value: datetime.datetime
    js_args: list[int | str]

    def __init__(self, value, *args, **kwargs):
        super().__init__(value, *args, **kwargs)
        offset = value.utcoffset()
        if offset is None:
            raise ValueError("ZonedDateTimeProp should only be used with aware datetimes")
        self.value = value
        self.js_args = [
            self.value.year,
            self.value.month,
            self.value.day,
            # e.g. Australia/Melbourne
            str(self.value.tzinfo),
            int(offset.total_seconds() * 1000),
            self.value.hour,
            self.value.minute,
            self.value.second,
            self.value.microsecond,
        ]

    def get_tag(self):
        return "ZonedDateTime"

    def get_representation(self, context):
        return self.js_args

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        calendar_date = generator.resolve_prop_import(
            "frontend/src/re-exports.tsx", ImportSpecifier("ZonedDateTime")
        )
        return NewExpression(
            calendar_date,
            self.js_args,
        )

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        return isinstance(value, datetime.datetime) and is_aware(value)


class TimeProp(ComponentProp):
    """Convert a python time to a @internationalized/date time"""

    value: datetime.time

    def __init__(self, value, *args, **kwargs):
        super().__init__(value, *args, **kwargs)
        self.value = value
        self.js_args = [self.value.hour, self.value.minute, self.value.second, self.value.microsecond]

    def get_tag(self):
        return "Time"

    def get_representation(self, context):
        return self.js_args

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        calendar_date = generator.resolve_prop_import("frontend/src/re-exports.tsx", ImportSpecifier("Time"))
        return NewExpression(calendar_date, self.js_args)

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        return isinstance(value, datetime.time)


class SetProp(ComponentProp):
    """Handles passing a python ``set`` to a JS ``Set``"""

    value: set

    def get_tag(self):
        return "Set"

    def get_representation(self, context: SSRSerializerContext) -> list:
        return list(self.value)

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        return NewExpression(
            Identifier("Set"),
            [ArrayLiteralExpression([self.convert_to_node(value, generator) for value in self.value])],
        )

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        return isinstance(value, set)

    def __init__(self, value: set, node: ComponentNode, context: Context):
        super().__init__(value, node, context)
        self.value = set({node.resolve_prop(element, context) for element in value})


class SpecialNumeric(ComponentProp):
    """Special prop that indicates a prop should be passed as NaN or Infinity/-Infinity

    This is used whenever a math.inf or math.nan / float("nan") is passed as a prop.
    """

    value: float

    def __init__(self, value: float, node: ComponentNode, context: Context):
        super().__init__(value, node, context)
        self.value = value

    def get_tag(self):
        return "SpecialNumeric"

    def generate_code(self, generator: ComponentSourceCodeGenerator):
        if math.isinf(self.value):
            return Identifier("Infinity" if self.value > 0 else "-Infinity")
        return Identifier("NaN")

    def get_representation(self, context: SSRSerializerContext) -> dict | str | list:
        if math.isinf(self.value):
            return "Infinity" if self.value > 0 else "-Infinity"
        return "NaN"

    @classmethod
    def should_apply(cls, value: Any, node: ComponentNode, context: Context):
        return isinstance(value, float) and (math.isinf(value) or math.isnan(value))


default_prop_handlers = [DateProp, DateTimeProp, ZonedDateTimeProp, TimeProp, SetProp, SpecialNumeric]
