from __future__ import annotations

from collections.abc import Collection
import re

_DJID_HTML_RE = re.compile(r'data-djid="[^"]+"')
_DJID_SELECTOR_RE = re.compile(r"\[data-djid='[^']+'\]")
_OPENING_TAG_RE = re.compile(r"<([a-zA-Z][\w:-]*)(\s[^<>]*?)?>")
_ATTR_RE = re.compile(r'([^\s=]+)(?:="([^"]*)")?')
_TAG_GAP_RE = re.compile(r">\s+<")
_WHITESPACE_RE = re.compile(r"\s+")
_CLASS_ATTR_RE = re.compile(r'\sclass="([^"]*)"')
_STYLE_ATTR_RE = re.compile(r'\sstyle="([^"]*)"')
_CSS_VAR_HASH_RE = re.compile(r"(--[\w-]+)__[a-z0-9]+\s*:\s*")


def _dedupe_tokens(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            deduped.append(token)
    return deduped


def normalize_class_tokens(
    class_value: str | None,
    allowed_prefixes: Collection[str],
    keep_class_tokens: Collection[str] = (),
) -> list[str]:
    """Port of ``normalizeClassTokens`` in ``scripts/parity_cases/_helpers.mjs``.

    The fixture generator applies it to React's output, so static output must go through it too
    before the two are compared: ``__hash`` suffixes are stripped, hashed tokens whose scope prefix
    is not in ``allowed_prefixes`` are dropped (unhashed tokens, such as consumer class names, are
    kept), duplicates are removed, and a token is dropped when a more specific child token
    (``<token>_...``) is present, or when it ends in ``Base`` and a token for its root
    (``<root>_...``) is present. Tokens in ``keep_class_tokens`` are never dropped by those last
    two rules.
    """
    normalized: list[str] = []
    for original_token in re.split(r"\s+", (class_value or "").strip()):
        if not original_token:
            continue
        hash_index = original_token.rfind("__")
        had_hash = hash_index != -1
        token = original_token[:hash_index] if had_hash else original_token
        if not token:
            continue
        if "_" in token:
            prefix = token.split("_", 1)[0]
            if had_hash and prefix not in allowed_prefixes:
                continue
        elif had_hash and token not in allowed_prefixes:
            continue
        normalized.append(token)

    deduped = _dedupe_tokens(normalized)

    def keep(token: str) -> bool:
        if token in keep_class_tokens:
            return True
        if any(other != token and other.startswith(f"{token}_") for other in deduped):
            return False
        if token.endswith("Base"):
            root = token[: -len("Base")]
            if any(other != token and other.startswith(f"{root}_") for other in deduped):
                return False
        return True

    return [token for token in deduped if keep(token)]


def normalize_class_attributes(
    html: str,
    allowed_prefixes: Collection[str],
    keep_class_tokens: Collection[str] = (),
) -> str:
    """Apply :func:`normalize_class_tokens` to every ``class`` attribute in ``html``.

    Matches the generator: an attribute left with no tokens is removed.
    """

    def _replace_attr(match: re.Match[str]) -> str:
        tokens = normalize_class_tokens(match.group(1), allowed_prefixes, keep_class_tokens)
        return f' class="{" ".join(tokens)}"' if tokens else ""

    def _replace_tag(match: re.Match[str]) -> str:
        return _CLASS_ATTR_RE.sub(_replace_attr, match.group(0))

    return _OPENING_TAG_RE.sub(_replace_tag, html)


def _normalize_tag_attributes(value: str, ignored_attributes: frozenset[str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        tag_name = match.group(1)
        attrs_part = (match.group(2) or "").strip()
        if not attrs_part:
            return f"<{tag_name}>"

        attrs: list[tuple[str, str | None]] = []
        for attr_match in _ATTR_RE.finditer(attrs_part):
            if attr_match.group(1) in ignored_attributes:
                continue
            attrs.append((attr_match.group(1), attr_match.group(2)))
        attrs.sort(key=lambda item: item[0])

        rendered_attrs = []
        for name, attr_value in attrs:
            # An attribute with an empty value is equivalent to a bare boolean attribute in HTML
            # (React SSR renders boolean attributes as `disabled=""`, the Python renderer as `disabled`).
            if attr_value is None or attr_value == "":
                rendered_attrs.append(f" {name}")
            else:
                rendered_attrs.append(f' {name}="{attr_value}"')
        return f"<{tag_name}{''.join(rendered_attrs)}>"

    return _OPENING_TAG_RE.sub(_replace, value)


def normalize_css_var_hashes(html: str) -> str:
    """Port of ``normalizeCssVarHashes`` in ``scripts/parity_cases/_helpers.mjs``.

    Strips the hash from custom property names set in ``style`` attributes (``--level__1a2b3c: 1``
    becomes ``--level: 1``), as the generator does for the components whose React output sets
    theme vars inline. Unlike the generator it also collapses the space after the colon: React
    writes ``--level__1a2b3c:1``, the static renderers ``--level__1a2b3c: 1``.
    """

    def _replace_attr(match: re.Match[str]) -> str:
        style = _CSS_VAR_HASH_RE.sub(r"\1: ", match.group(1))
        return f' style="{style}"'

    def _replace_tag(match: re.Match[str]) -> str:
        return _STYLE_ATTR_RE.sub(_replace_attr, match.group(0))

    return _OPENING_TAG_RE.sub(_replace_tag, html)


def normalize_html_fragment(
    value: str,
    *,
    ignored_attributes: frozenset[str] = frozenset(),
) -> str:
    normalized = value.strip()
    normalized = _DJID_HTML_RE.sub('data-djid="__DJID__"', normalized)
    normalized = _DJID_SELECTOR_RE.sub("[data-djid='__DJID__']", normalized)
    normalized = _normalize_tag_attributes(normalized, ignored_attributes)
    normalized = _TAG_GAP_RE.sub("><", normalized)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip()
