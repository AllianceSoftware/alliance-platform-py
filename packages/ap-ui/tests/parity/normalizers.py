from __future__ import annotations

import re

_DJID_HTML_RE = re.compile(r'data-djid="[^"]+"')
_DJID_SELECTOR_RE = re.compile(r"\[data-djid='[^']+'\]")
_TAG_GAP_RE = re.compile(r">\s+<")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_html_fragment(value: str) -> str:
    normalized = value.strip()
    normalized = _DJID_HTML_RE.sub('data-djid="__DJID__"', normalized)
    normalized = _DJID_SELECTOR_RE.sub("[data-djid='__DJID__']", normalized)
    normalized = _TAG_GAP_RE.sub("><", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()
