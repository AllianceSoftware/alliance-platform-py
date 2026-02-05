from __future__ import annotations

from pathlib import Path
import tempfile

from alliance_platform.codegen.registry import CodegenArtifact
from alliance_platform.codegen.registry import CodegenRegistration
from alliance_platform.codegen.registry import CodegenRegistry
from django.core.management import CommandError
from django.core.management import call_command
from django.test import SimpleTestCase
from django.test import override_settings


class SimpleCodegenRegistration(CodegenRegistration):
    """Simple registration for testing that generates a single file."""

    def __init__(self, path: Path, contents: str):
        self.path = path
        self.contents = contents

    def generate_artifacts(self):
        return CodegenArtifact(path=self.path, contents=self.contents)


class SampleRegistration(CodegenRegistration):
    def __init__(self, target_path: Path, dependency: Path):
        self._target_path = target_path
        self._dependency = dependency

    def generate_artifacts(self) -> CodegenArtifact | list[CodegenArtifact]:
        return CodegenArtifact(self._target_path, "console.log('hello');\n")

    def get_cache_key(self):
        return {
            "registration_id": "sample",
            "dependency_files": [self._dependency],
        }


class CodegenRegistryDryRunTestCase(SimpleTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_registry(self):
        registry = CodegenRegistry()
        registry.cache_path = self.test_dir / "codegen-cache.json"
        registry.cache = {"version": 1, "entries": {}}
        return registry

    def test_dry_run_detects_new_file(self):
        target_path = self.test_dir / "output" / "new_file.txt"
        registry = self._create_registry()
        registry.register(SimpleCodegenRegistration(target_path, "new content"))

        stats = registry.run_codegen(dry_run=True)

        self.assertEqual(stats.files_pending, [target_path])
        self.assertEqual(stats.files_written, [])
        self.assertFalse(target_path.exists())

    def test_dry_run_detects_changed_file(self):
        target_path = self.test_dir / "output" / "existing_file.txt"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("old content", "utf8")

        registry = self._create_registry()
        registry.register(SimpleCodegenRegistration(target_path, "new content"))

        stats = registry.run_codegen(dry_run=True)

        self.assertEqual(stats.files_pending, [target_path])
        self.assertEqual(stats.files_written, [])
        self.assertEqual(target_path.read_text("utf8"), "old content")

    def test_dry_run_no_change_when_same(self):
        target_path = self.test_dir / "output" / "same_file.txt"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("same content", "utf8")

        registry = self._create_registry()
        registry.register(SimpleCodegenRegistration(target_path, "same content"))

        stats = registry.run_codegen(dry_run=True)

        self.assertEqual(stats.files_pending, [])
        self.assertEqual(stats.files_written, [])

    def test_normal_run_writes_files(self):
        target_path = self.test_dir / "output" / "written_file.txt"
        registry = self._create_registry()
        registry.register(SimpleCodegenRegistration(target_path, "written content"))

        stats = registry.run_codegen(dry_run=False)

        self.assertEqual(stats.files_pending, [])
        self.assertEqual(stats.files_written, [target_path])
        self.assertTrue(target_path.exists())
        self.assertEqual(target_path.read_text("utf8"), "written content")

    def test_dry_run_multiple_files(self):
        new_file = self.test_dir / "output" / "new.txt"

        changed_file = self.test_dir / "output" / "changed.txt"
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.write_text("old", "utf8")

        same_file = self.test_dir / "output" / "same.txt"
        same_file.write_text("same", "utf8")

        registry = self._create_registry()
        registry.register(SimpleCodegenRegistration(new_file, "new content"))
        registry.register(SimpleCodegenRegistration(changed_file, "new"))
        registry.register(SimpleCodegenRegistration(same_file, "same"))

        stats = registry.run_codegen(dry_run=True)

        self.assertIn(new_file, stats.files_pending)
        self.assertIn(changed_file, stats.files_pending)
        self.assertNotIn(same_file, stats.files_pending)
        self.assertEqual(len(stats.files_pending), 2)
        self.assertEqual(stats.files_written, [])

        self.assertFalse(new_file.exists())
        self.assertEqual(changed_file.read_text("utf8"), "old")


class TestCodegenRegistry(SimpleTestCase):
    def test_run_codegen_dry_run_does_not_write_or_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            cache_dir = base_dir / "cache"
            output_dir = base_dir / "out"
            dependency = base_dir / "dep.txt"
            dependency.write_text("data", "utf8")
            target_path = output_dir / "generated.ts"

            alliance_platform_settings = {
                "CORE": {
                    "PROJECT_DIR": base_dir,
                    "CACHE_DIR": cache_dir,
                },
                "CODEGEN": {
                    "JS_ROOT_DIR": base_dir,
                    "TEMP_DIR": base_dir,
                },
            }

            with override_settings(ALLIANCE_PLATFORM=alliance_platform_settings):
                registry = CodegenRegistry()
                registry.register(SampleRegistration(target_path, dependency))
                stats = registry.run_codegen(dry_run=True)

            self.assertIn(target_path, stats.files_pending)
            self.assertFalse(target_path.exists())
            self.assertFalse((cache_dir / "codegen-artifact-cache.json").exists())


_TEST_STATE: dict[str, Path] = {}


def get_test_registry() -> CodegenRegistry:
    target_path = _TEST_STATE["target_path"]
    dependency = _TEST_STATE["dependency"]
    registry = CodegenRegistry()
    registry.register(SampleRegistration(target_path, dependency))
    return registry


class TestCodegenCommand(SimpleTestCase):
    def test_command_check_errors_when_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            cache_dir = base_dir / "cache"
            output_dir = base_dir / "out"
            dependency = base_dir / "dep.txt"
            dependency.write_text("data", "utf8")
            target_path = output_dir / "generated.ts"

            _TEST_STATE["target_path"] = target_path
            _TEST_STATE["dependency"] = dependency

            alliance_platform_settings = {
                "CORE": {
                    "PROJECT_DIR": base_dir,
                    "CACHE_DIR": cache_dir,
                },
                "CODEGEN": {
                    "JS_ROOT_DIR": base_dir,
                    "TEMP_DIR": base_dir,
                    "REGISTRY": "tests.test_codegen.get_test_registry",
                },
            }

            with override_settings(ALLIANCE_PLATFORM=alliance_platform_settings):
                with self.assertRaises(CommandError):
                    call_command("codegen", check=True)

            self.assertFalse(target_path.exists())
