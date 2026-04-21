from __future__ import annotations

import re

_DJID_HTML_RE = re.compile(r'data-djid="[^"]+"')
_DJID_SELECTOR_RE = re.compile(r"\[data-djid='[^']+'\]")
_OPENING_TAG_RE = re.compile(r"<([a-zA-Z][\w:-]*)(\s[^<>]*?)?>")
_ATTR_RE = re.compile(r'([^\s=]+)(?:="([^"]*)")?')
_TAG_GAP_RE = re.compile(r">\s+<")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_tag_attributes(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        tag_name = match.group(1)
        attrs_part = (match.group(2) or "").strip()
        if not attrs_part:
            return f"<{tag_name}>"

        attrs: list[tuple[str, str | None]] = []
        for attr_match in _ATTR_RE.finditer(attrs_part):
            attrs.append((attr_match.group(1), attr_match.group(2)))
        attrs.sort(key=lambda item: item[0])

        rendered_attrs = []
        for name, attr_value in attrs:
            if attr_value is None:
                rendered_attrs.append(f" {name}")
            else:
                rendered_attrs.append(f' {name}="{attr_value}"')
        return f"<{tag_name}{''.join(rendered_attrs)}>"

    return _OPENING_TAG_RE.sub(_replace, value)


def normalize_html_fragment(value: str) -> str:
    normalized = value.strip()
    normalized = _DJID_HTML_RE.sub('data-djid="__DJID__"', normalized)
    normalized = _DJID_SELECTOR_RE.sub("[data-djid='__DJID__']", normalized)
    normalized = _normalize_tag_attributes(normalized)
    normalized = _TAG_GAP_RE.sub("><", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()
