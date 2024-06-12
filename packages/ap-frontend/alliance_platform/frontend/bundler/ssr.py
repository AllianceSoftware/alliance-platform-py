from __future__ import annotations

from dataclasses import dataclass
import json
from json import JSONDecodeError
import logging
from pathlib import Path
import uuid

from allianceutils.util import camelize
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
import requests

from . import get_bundler
from .base import BaseBundler

logger = logging.getLogger("alliance_platform.frontend")

SSR_FAILURE_PLACEHOLDER = "<!-- SSR_FAILED -->"


class SSRJsonEncoder(DjangoJSONEncoder):
    """Custom encoder that handles ``SSRSerializable`` objects

    Any :class:`~alliance_platform.frontend.bundler.ssr.SSRSerializable` object will be serialized using
    :meth:`~alliance_platform.frontend.bundler.ssr.SSRSerializable.serialize`, and will
    have access to the :class:`~alliance_platform.frontend.bundler.ssr.SSRSerializerContext`` object.
    """

    ssr_context: SSRSerializerContext

    def __init__(self, ssr_context: SSRSerializerContext, **kwargs):
        self.ssr_context = ssr_context
        super().__init__(**kwargs)

    def default(self, o):
        if isinstance(o, SSRSerializable):
            return o.serialize(self.ssr_context)
        return super().default(o)


class SSRSerializerContext:
    """Context available to :class:`~alliance_platform.frontend.bundler.ssr.SSRSerializable` objects during serialization"""

    required_imports: dict[ImportDefinition, tuple[str, dict]]
    bundler: BaseBundler

    def __init__(self, bundler: BaseBundler):
        self.required_imports = {}
        self.prefix = uuid.uuid4().hex
        self.bundler = bundler

    def add_import(self, definition: ImportDefinition) -> str:
        """Add the specified import to the list of required imports and return the cache key

        This allows us to collect all the imports that are required for a given SSR request
        and load them all up front, then assign them as part of the JSON parsing.

        For example, an import will be serialized as:

            ['@@CUSTOM', 'ModuleImport', 'abc123']

        ``abc123`` is the key returned by ``add_import``. In ``processSSRRequest``, the required
        imports will be loaded first, then the JSON will be parsed with a custom reviver. This
        reviver will replace any ``['@@CUSTOM', 'ModuleImport', 'abc123']`` with the actual resolved
        import.

        This turns out to be a lot faster than traversing the object after JSON parsing and loading any
        encountered imports.
        """
        if definition not in self.required_imports:
            cache_key = f"{self.prefix}__{len(self.required_imports)}"
            path = definition.path
            self.required_imports[definition] = (
                cache_key,
                {
                    "path": str(
                        self.bundler.resolve_ssr_import_path(
                            self.bundler.validate_path(path, resolve_extensions=[".ts", ".tsx"])
                        )
                    ),
                    "import_name": definition.import_name,
                    "is_default_import": definition.is_default_import,
                },
            )
        return self.required_imports[definition][0]

    def get_required_imports(self) -> dict[str, dict]:
        return {key: camelize(definition) for key, definition in self.required_imports.values()}


class SSRSerializable:
    """Mixin for classes which can be serialized for SSR

    :class:`~alliance_platform.frontend.bundler.ssr.SSRJsonEncoder` can be used to serialize objects that implement this

    The frontend handler, currently ``processSSRRequest`` in ``ssr.ts``, will use ``JSON.parse`` with a custom reviver
    to convert the serialized objects back into their original form. If it encounters an object with the tag ``@@CUSTOM``,
    it will trigger custom conversions that allow non-standard JSON objects (e.g. a ``Date`` or ``Set``, or any arbitrary
    object you may define). See :class:`~alliance_platform.frontend.bundler.ssr.SSRCustomFormatSerializable` for a base
    class to implement custom serialization.
    """

    def serialize(self, context: SSRSerializerContext) -> dict | str | list:
        """Serialize the object for SSR

        This method should return a value that can be JSON serialized. Note that it's fine to return values
        that contain ``SSRSerializable`` objects, as these will be serialized recursively.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement serialize()")


class SSRCustomFormatSerializable(SSRSerializable):
    """Mixin for classes which can be serialized for SSR using a custom format

    ``serializer`` converting the object to the form::

        ["@@CUSTOM", <tag name>, <serialized representation>]

    For example, a date object might look like:

        ["@@CUSTOM", "date", "2023-01-01"]

    The frontend will then have a matching reviver to convert this into a date object.

    See :class:`~alliance_platform.frontend.bundler.ssr.SSRJsonEncoder` for how this is handled.
    """

    def get_tag(self):
        """Get the tag to identify the type of serializable. This is matched in nodejs for de-serialization."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement get_tag()")

    def get_representation(self, context: SSRSerializerContext) -> dict | str | list:
        """Get the representation of the object to be serialized

        This can be any JSON serializable value. The matching reviver in ``ssrJsonReviviers.tsx`` will be passed this value.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement get_representation()")

    def serialize(self, context: SSRSerializerContext) -> list:
        tag = self.get_tag()
        return ["@@CUSTOM", tag, self.get_representation(context)]


@dataclass(frozen=True)
class ImportDefinition(SSRCustomFormatSerializable):
    """Describes an import that needs to be resolved.

    This uses ``SSRSerializerContext`` to queue its import. ``BundlerAssetServerSideRenderer.process`` will then
    serialize these imports and pass them to the SSR renderer. ``processSSRRequest`` will then load the imports
    first before de-serializing the JSON for all items in the SSR. In practice, resolving each import once upfront,
    was significantly faster than resolving each import as it was encountered in the JSON.
    """

    path: Path
    import_name: str
    is_default_import: bool

    def get_tag(self):
        return "ModuleImport"

    def get_representation(self, context: SSRSerializerContext) -> str:
        return context.add_import(self)


class SSRItem:
    """
    Base class for server side rendering (SSR) items

    The ``SSRItem`` class is the base class for server side rendering items. An ``SSRItem`` is made up of a type,
    which tells the SSR JavaScript code how to handle the item, and a payload, which serializes any necessary data from
    the server to the frontend.

    For example, a React component payload would encode the details of the component (its name and where to import it from)
    and the props used to render it.

    Each concrete implementation of ``SSRItem`` needs to implement :meth:`~alliance_platform.frontend.bundler.context.SSRItem.get_ssr_type`
    and :meth:`~alliance_platform.frontend.bundler.context.SSRItem.get_ssr_payload`.

    ``SSRItems`` are queued for rendering using the :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.queue_ssr`
    method, and then rendered by :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware`.
    """

    def get_ssr_type(self):
        """Returns the type of SSR which is then interpreted by the frontend

        See ``ssr.ts`` for where this is done
        """
        raise NotImplementedError

    def get_ssr_payload(self, ssr_context: SSRSerializerContext) -> dict:
        """Return the payload required by the frontend for this item

        This should be a JSON serializable Dict
        """
        raise NotImplementedError

    def serialize(self, ssr_context: SSRSerializerContext) -> dict:
        """Serializes to a dict that can be JSON encoded and sent to the frontend

        You shouldn't need to override this method - instead implement ``get_ssr_type`` and
        ``get_ssr_payload``.

        Returns a Dict with two keys: ``ssrType`` and ``payload``.
        """
        return {
            "ssrType": self.get_ssr_type(),
            "payload": self.get_ssr_payload(ssr_context),
        }


class BundlerAssetServerSideRenderer:
    ssr_queue: dict[str, SSRItem]

    def __init__(self, ssr_queue: dict[str, SSRItem]):
        self.ssr_queue = ssr_queue

    def process_ssr(self, payload: dict) -> dict | None:
        """Process an SSR request

        This calls the endpoint specified by :meth:`~alliance_platform.frontend.bundler.base.BaseBundler.get_ssr_url`.

        For the Vite implementation this endpoint is defined in ``dev-server.ts`` for dev, or ``production-ssr-server.ts``
        in preview or production.
        """

        # If dev the rendering happens in dev-server.ts
        bundler = get_bundler()
        ssr_url = bundler.get_ssr_url()
        if not ssr_url:
            logger.error("Can not perform SSR, no SSR URL defined. Set `production_ssr_url` on the bundler.")
            return None
        try:
            json_payload = json.dumps(payload, cls=DjangoJSONEncoder)
            ssr_response = requests.post(
                ssr_url,
                data=json_payload,
                headers={"Content-Type": "application/json", **bundler.get_ssr_headers()},
                timeout=1,
            )
            if ssr_response.status_code != 200:
                try:
                    # If SSR server responds with JSON it will have an 'error' and optional 'stack' key for more info
                    data = ssr_response.json()
                    msg = f"Bad response {ssr_response.status_code} from SSR server: {data['error']}"
                    if "stack" in data:
                        msg += f"\n{data['stack']}"
                    logger.error(msg)
                except JSONDecodeError:
                    logger.error(
                        f"Bad response {ssr_response.status_code} from SSR server: {ssr_response.content.decode()}"
                    )
            else:
                # See ssr.ts ServerRenderComponentReturnValue for what this is
                try:
                    return ssr_response.json()
                except JSONDecodeError:
                    logger.error(
                        f"Failed to decode JSON from server rendering, content received: {ssr_response.content.decode()}"
                    )
        except TypeError:
            logger.exception(f"Failed to encode JSON for server rendering. Payload was: {payload}")
        except requests.exceptions.Timeout:
            logger.error("Timed out connecting to SSR server for rendering")
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to SSR server for rendering - is it running?")
        return None

    def process(self, content: str | bytes, global_context: dict):
        if not self.ssr_queue:
            return content
        ssr_context = SSRSerializerContext(get_bundler())
        # items are serialized first so that `ssr_context` can be populated with the required imports
        serialized_items = {
            placeholder: ssr_item.serialize(ssr_context) for placeholder, ssr_item in self.ssr_queue.items()
        }
        items = json.dumps(
            serialized_items,
            ssr_context=ssr_context,
            cls=SSRJsonEncoder,
        )
        # This should match `ServerRenderRequest` in `ssr.ts`
        payload = {
            "itemsJson": items,
            "requiredImports": ssr_context.get_required_imports(),
            "globalContext": global_context,
        }
        # See ssr.ts `renderItems` for more details on what the return value is
        # All requested items will be in either the `renderedItems` Dict or the `errors` Dict.
        # Example return:
        # {
        #    renderedItems: {
        #      "___SSR_PLACEHOLDER_0___": {
        #        "html": "<div>Test</div>",
        #        "renderErrors": ["some error that didn't stop SSR"],
        #      }
        #    },
        #    errors: {},
        #  }
        data = self.process_ssr(payload)
        is_bytes = isinstance(content, bytes)

        def replace_content(placeholder, value):
            if is_bytes:
                return content.replace(placeholder.encode(), value.encode())
            return content.replace(placeholder, value)

        if data:
            for placeholder, value in data["renderedItems"].items():
                content = replace_content(placeholder, value["html"])
                if value.get("renderErrors"):
                    try:
                        debug_component_name = (
                            serialized_items[placeholder]["payload"]["component"].import_name
                            + f' (HTML placeholder="{placeholder}")'
                        )
                    except (KeyError, AttributeError):
                        debug_component_name = f'HTML placeholder="{placeholder}"'
                        pass
                    if settings.DEBUG:
                        # Outputting the errors here is very difficult to read - direct the user to the console instead
                        logger.warning(
                            f"SSR succeeded with errors for item {debug_component_name}. See `yarn dev` console for details."
                        )
                    else:
                        logger.warning(
                            f"SSR succeeded with errors for item {debug_component_name}: {value['renderErrors']}"
                        )
            for placeholder, value in data["errors"].items():
                logger.error(f"Server rendering failed for {self.ssr_queue[placeholder]}: {value}")
                content = replace_content(placeholder, SSR_FAILURE_PLACEHOLDER)
        else:
            for placeholder in serialized_items.keys():
                content = replace_content(placeholder, SSR_FAILURE_PLACEHOLDER)

        return content
