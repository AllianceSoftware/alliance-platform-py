from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Literal

from alliance_platform.ui.templatetags.alliance_platform.html_components.base import (
    BaseHtmlUIComponentRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.registry import built_in_registry
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.template import TemplateSyntaxError
from django.template.base import Lexer
from django.template.base import TokenType
from django.utils.text import unescape_string_literal

MigrationStatus = Literal["ready", "review", "native", "no-static-equivalent"]


@dataclass(frozen=True)
class LegacyComponentMigration:
    """Migration metadata shared by named and generic Alliance UI component calls."""

    static_renderer: str | None
    named_tag: bool = False
    literal_props: frozenset[str] = frozenset()
    positional_icon_name: bool = False


# This is the single extension point for legacy component coverage. ``named_tag`` identifies tags
# registered by ``alliance_platform.ui``; every entry can also be matched when used through the
# generic ``component "@alliancesoftware/ui" ...`` syntax.
LEGACY_COMPONENT_MIGRATIONS: dict[str, LegacyComponentMigration] = {
    "Button": LegacyComponentMigration("button", named_tag=True),
    "ButtonGroup": LegacyComponentMigration("button_group", named_tag=True),
    "Icon": LegacyComponentMigration("icon", named_tag=True, positional_icon_name=True),
    "TextInput": LegacyComponentMigration("text_input"),
    "NumberInput": LegacyComponentMigration("number_input"),
    "TextArea": LegacyComponentMigration("text_area"),
    "Table": LegacyComponentMigration("table", named_tag=True),
    "TableHeader": LegacyComponentMigration("table_header", named_tag=True),
    "TableBody": LegacyComponentMigration("table_body", named_tag=True),
    "Column": LegacyComponentMigration("table_column", named_tag=True),
    "Row": LegacyComponentMigration("table_row", named_tag=True),
    "Cell": LegacyComponentMigration("table_cell", named_tag=True),
    "Menubar": LegacyComponentMigration("menubar", named_tag=True),
    "Menubar.Item": LegacyComponentMigration("menubar_item", named_tag=True),
    "Menubar.SubMenu": LegacyComponentMigration(
        "menubar_submenu",
        named_tag=True,
        literal_props=frozenset({"icon"}),
    ),
    "Menubar.Section": LegacyComponentMigration(
        "menubar_section",
        named_tag=True,
        literal_props=frozenset({"icon"}),
    ),
    "ColumnHeaderLink": LegacyComponentMigration(None, named_tag=True),
    "DatePicker": LegacyComponentMigration(None, named_tag=True),
    "Fragment": LegacyComponentMigration(None, named_tag=True),
    "InlineAlert": LegacyComponentMigration("inline_alert", named_tag=True),
    "LabeledInput": LegacyComponentMigration(None, named_tag=True),
    "Pagination": LegacyComponentMigration("pagination", named_tag=True),
    "TimeInput": LegacyComponentMigration(None, named_tag=True),
}

DEFAULT_EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "static",
        "staticfiles",
        "venv",
    }
)

_KWARG_NAME_RE = re.compile(r"^(?:\w+|(?:\w+-)+\w+|(?:\w+:)\w+|(?:\w+:)(?:\w+-)+\w+)$")
_DEFERRED_URL_FILTER_RE = re.compile(r"\|(?:url_with_perm|url)(?::|\||$)")


@dataclass(frozen=True)
class MigrationFinding:
    path: Path
    line: int
    component: str
    source: str
    status: MigrationStatus
    suggestion: str
    notes: tuple[str, ...] = ()


def _static_string(token: str) -> str | None:
    if len(token) < 2 or token[0] not in {'"', "'"} or token[-1] != token[0]:
        return None
    try:
        return unescape_string_literal(token)
    except ValueError:
        return None


def _parse_arguments(bits: list[str]) -> tuple[list[str], dict[str, str]]:
    positional: list[str] = []
    props: dict[str, str] = {}
    for index, bit in enumerate(bits):
        if bit == "as" and index + 1 < len(bits):
            break
        key, separator, value = bit.partition("=")
        if separator and _KWARG_NAME_RE.fullmatch(key):
            props[key] = value
        else:
            positional.append(bit)
    return positional, props


def _is_intrinsic_component(name: str) -> bool:
    # Keep this aligned with parse_component_tag(): one lowercase alphabetic source (or heading)
    # is treated as a common/intrinsic element rather than a module path.
    return name.isalpha() and name.islower() or name in {"h1", "h2", "h3", "h4", "h5", "h6"}


def _renderer_for(spec: LegacyComponentMigration) -> type[BaseHtmlUIComponentRenderer] | None:
    if spec.static_renderer is None:
        return None
    return built_in_registry.get(spec.static_renderer)


def _static_finding(
    *,
    path: Path,
    line: int,
    component: str,
    source: str,
    spec: LegacyComponentMigration,
    positional: list[str],
    props: dict[str, str],
) -> MigrationFinding:
    if spec.static_renderer is None:
        return MigrationFinding(
            path=path,
            line=line,
            component=component,
            source=source,
            status="no-static-equivalent",
            suggestion="no static equivalent yet",
        )

    renderer = _renderer_for(spec)
    if renderer is None:
        return MigrationFinding(
            path=path,
            line=line,
            component=component,
            source=source,
            status="no-static-equivalent",
            suggestion="no static equivalent yet",
            notes=(f"configured renderer '{spec.static_renderer}' is not registered",),
        )

    notes: list[str] = []
    unsupported_props: set[str] = set()
    unsupported_prop_reasons: dict[str, str] = {}
    legacy_options: set[str] = set()
    for raw_name in props:
        if raw_name == "props":
            notes.append("bulk props= requires review because its keys are not statically known")
            continue
        if ":" in raw_name:
            legacy_options.add(raw_name)
            continue
        if not renderer.supports_prop_name(raw_name):
            canonical_name = renderer.canonical_prop_name(raw_name)
            unsupported_props.add(canonical_name)
            reason = renderer.unsupported_prop_reasons.get(canonical_name)
            if reason:
                unsupported_prop_reasons[canonical_name] = reason

    if unsupported_props:
        notes.append(f"unsupported props: {', '.join(sorted(unsupported_props))}")
    for prop_name, reason in sorted(unsupported_prop_reasons.items()):
        notes.append(f"{prop_name}: {reason}")
    if legacy_options:
        notes.append(f"legacy rendering options require review: {', '.join(sorted(legacy_options))}")

    if spec.positional_icon_name:
        icon_name = positional[0] if positional else props.get("name")
        if icon_name is None or _static_string(icon_name) is None:
            notes.append("icon name must be a static string literal")
    elif positional:
        notes.append("positional arguments require review")

    for literal_prop in spec.literal_props:
        raw_value = props.get(literal_prop)
        if raw_value is not None and _static_string(raw_value) is None:
            notes.append(f"{literal_prop} must be a static string literal")

    return MigrationFinding(
        path=path,
        line=line,
        component=component,
        source=source,
        status="review" if notes else "ready",
        suggestion=f'{{% ui "{spec.static_renderer}" %}}',
        notes=tuple(notes),
    )


def _native_finding(
    *,
    path: Path,
    line: int,
    element: str,
    source: str,
    props: dict[str, str],
) -> MigrationFinding:
    notes: list[str] = []
    if "props" in props:
        notes.append("bulk props= requires review before converting to native attributes")
    deferred_props = sorted(name for name, value in props.items() if _DEFERRED_URL_FILTER_RE.search(value))
    if deferred_props:
        notes.append(
            "deferred url/url_with_perm props require review; native HTML does not automatically "
            f"preserve component omission ({', '.join(deferred_props)})"
        )
    return MigrationFinding(
        path=path,
        line=line,
        component=element,
        source=source,
        status="review" if notes else "native",
        suggestion=f"native <{element}> HTML",
        notes=tuple(notes),
    )


def scan_template(path: Path, source_text: str) -> list[MigrationFinding]:
    findings: list[MigrationFinding] = []
    for token in Lexer(source_text).tokenize():
        if token.token_type is not TokenType.BLOCK:
            continue
        try:
            bits = token.split_contents()
        except TemplateSyntaxError:
            continue
        if not bits:
            continue

        tag_name = bits[0]
        line = token.lineno or 1
        named_spec = LEGACY_COMPONENT_MIGRATIONS.get(tag_name)
        if named_spec is not None and named_spec.named_tag:
            positional, props = _parse_arguments(bits[1:])
            findings.append(
                _static_finding(
                    path=path,
                    line=line,
                    component=tag_name,
                    source=f"tag {tag_name}",
                    spec=named_spec,
                    positional=positional,
                    props=props,
                )
            )
            continue

        if tag_name != "component":
            continue
        positional, props = _parse_arguments(bits[1:])
        if not positional:
            continue
        source_name = _static_string(positional[0])
        if source_name is None:
            continue

        if len(positional) == 1 and _is_intrinsic_component(source_name):
            findings.append(
                _native_finding(
                    path=path,
                    line=line,
                    element=source_name,
                    source=f'component "{source_name}"',
                    props=props,
                )
            )
            continue

        if source_name != "@alliancesoftware/ui" or len(positional) < 2:
            continue
        component_name = _static_string(positional[1])
        if component_name is None:
            continue
        spec = LEGACY_COMPONENT_MIGRATIONS.get(
            component_name,
            LegacyComponentMigration(static_renderer=None),
        )
        findings.append(
            _static_finding(
                path=path,
                line=line,
                component=component_name,
                source=f'component "@alliancesoftware/ui" "{component_name}"',
                spec=spec,
                positional=positional[2:],
                props=props,
            )
        )
    return findings


class Command(BaseCommand):
    help = "Report legacy Alliance UI template components that can migrate to static {% ui %} renderers."

    def add_arguments(self, parser):
        parser.add_argument(
            "paths",
            nargs="*",
            help="Optional HTML template files or directories (defaults to settings.BASE_DIR).",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit nonzero when any migration findings are present.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR).resolve()
        files = self._resolve_files(options["paths"], base_dir)
        findings: list[MigrationFinding] = []
        for path in files:
            try:
                source_text = path.read_text()
            except (OSError, UnicodeError) as exc:
                raise CommandError(f"Could not read template '{path}': {exc}") from exc
            findings.extend(scan_template(path, source_text))

        findings.sort(key=lambda item: (self._display_path(item.path, base_dir), item.line))
        for finding in findings:
            display_path = self._display_path(finding.path, base_dir)
            details = f"; {'; '.join(finding.notes)}" if finding.notes else ""
            self.stdout.write(
                f"{display_path}:{finding.line}: [{finding.status.upper()}] "
                f"{finding.source} -> {finding.suggestion}{details}"
            )

        self._write_summary(findings)
        if options["strict"] and findings:
            raise CommandError(f"UI migration check found {len(findings)} legacy usage(s).")

    def _resolve_files(self, raw_paths: list[str], base_dir: Path) -> list[Path]:
        candidates = raw_paths or [str(base_dir)]
        files: set[Path] = set()
        for raw_path in candidates:
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = (Path.cwd() / candidate).resolve()
            else:
                candidate = candidate.resolve()
            if not candidate.exists():
                raise CommandError(f"Template path does not exist: {raw_path}")
            if candidate.is_file():
                if candidate.suffix.lower() != ".html":
                    raise CommandError(f"Template file must use the .html extension: {raw_path}")
                files.add(candidate)
                continue
            if not candidate.is_dir():
                raise CommandError(f"Template path is not a file or directory: {raw_path}")
            files.update(self._walk_directory(candidate))
        return sorted(files)

    def _walk_directory(self, root: Path) -> set[Path]:
        files: set[Path] = set()
        walk_errors: list[OSError] = []
        for directory, directory_names, file_names in os.walk(
            root,
            followlinks=False,
            onerror=walk_errors.append,
        ):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not name.startswith(".") and name not in DEFAULT_EXCLUDED_DIRECTORY_NAMES
            )
            for file_name in sorted(file_names):
                if not file_name.lower().endswith(".html"):
                    continue
                path = Path(directory) / file_name
                if not path.is_symlink():
                    files.add(path.resolve())
        if walk_errors:
            error = walk_errors[0]
            raise CommandError(f"Could not scan template directory '{root}': {error}") from error
        return files

    def _display_path(self, path: Path, base_dir: Path) -> str:
        try:
            return path.relative_to(base_dir).as_posix()
        except ValueError:
            return Path(os.path.relpath(path, Path.cwd())).as_posix()

    def _write_summary(self, findings: list[MigrationFinding]) -> None:
        self.stdout.write("")
        self.stdout.write("Summary:")
        if not findings:
            self.stdout.write("  No legacy Alliance UI template usages found.")
            return
        counts = Counter((finding.component, finding.status) for finding in findings)
        statuses: tuple[MigrationStatus, ...] = (
            "ready",
            "review",
            "native",
            "no-static-equivalent",
        )
        for component in sorted({finding.component for finding in findings}, key=str.casefold):
            parts = [
                f"{status}={counts[component, status]}" for status in statuses if counts[component, status]
            ]
            self.stdout.write(f"  {component}: {', '.join(parts)}")
        self.stdout.write(f"  Total: {len(findings)}")
