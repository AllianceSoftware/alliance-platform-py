from __future__ import annotations

import json
from typing import Any

from django.utils.html import format_html
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource


def attach_module_script(module_resource: FrontendResource, root_attrs: dict[str, Any]) -> str:
    """Attach a runtime module to a rendered root element using a generated ``data-djid`` selector."""

    asset_context = BundlerAssetContext.get_current()
    component_id = asset_context.generate_id()
    root_attrs["data-djid"] = component_id

    bundler = get_bundler()
    import_url = bundler.get_url(module_resource.path)
    selector = f"[data-djid='{component_id}']"
    code = (
        f"import attach from {json.dumps(str(import_url))};\n"
        f"const el = document.querySelector({json.dumps(selector)});\n"
        "if (el) { attach(el); }"
    )
    return str(format_html('<script type="module">\n{}\n</script>', mark_safe(code)))
