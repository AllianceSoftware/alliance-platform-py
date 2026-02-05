from __future__ import annotations

from pathlib import Path

from alliance_platform.codegen.registry import CodegenRegistry
from alliance_platform.codegen.settings import ap_codegen_settings
from alliance_platform.core.settings import ap_core_settings
from django.core.management import BaseCommand
from django.core.management import CommandError
from django.utils.module_loading import import_string


def _resolve_registry(registry_path: str | None) -> CodegenRegistry:
    registry_value = registry_path or ap_codegen_settings.REGISTRY
    if registry_value is None:
        raise CommandError(
            "No codegen registry configured. Provide --registry or set ALLIANCE_PLATFORM['CODEGEN']['REGISTRY']."
        )

    registry = import_string(registry_value) if isinstance(registry_value, str) else registry_value
    if isinstance(registry, CodegenRegistry):
        return registry
    if callable(registry):
        registry = registry()
    if not isinstance(registry, CodegenRegistry):
        raise CommandError(
            "Resolved registry is not a CodegenRegistry. Provide a CodegenRegistry instance or a callable that returns one."
        )
    return registry


class Command(BaseCommand):
    help = "Run Alliance Platform code generation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--registry",
            help=(
                "Dotted path to a CodegenRegistry instance or a callable that returns one. "
                "Defaults to ALLIANCE_PLATFORM['CODEGEN']['REGISTRY']."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Generate artifacts without writing any files.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit with non-zero status if codegen would write any files (implies --dry-run).",
        )

    def handle(self, *args, registry=None, dry_run=False, check=False, **kwargs):
        if check:
            dry_run = True
        codegen_registry = _resolve_registry(registry)
        stats = codegen_registry.run_codegen(dry_run=dry_run)

        if stats.warnings:
            for warning in stats.warnings:
                self.stderr.write(self.style.WARNING(warning))

        if stats.aborted:
            raise CommandError(stats.abort_reason or "Codegen aborted")

        project_dir = ap_core_settings.PROJECT_DIR

        def display_path(path: Path) -> str:
            try:
                return str(path.relative_to(project_dir))
            except ValueError:
                return str(path)

        files_changed = stats.files_pending if dry_run else stats.files_written
        if files_changed:
            header = "Codegen changes:" if dry_run else "Codegen wrote files:"
            self.stdout.write(header)
            for path in files_changed:
                self.stdout.write(f"- {display_path(path)}")
        else:
            self.stdout.write("Codegen: no changes")

        self.stdout.write(f"Registrations: {stats.registration_count}")
        self.stdout.write(f"Time: {stats.time_taken:.2f}s")

        if check and files_changed:
            raise CommandError("Codegen changes detected")
