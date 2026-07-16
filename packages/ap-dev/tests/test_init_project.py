from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from alliance_platform.dev.init_project import update_project_identity


class ProjectInitialisationTests(unittest.TestCase):
    def test_template_name_is_replaced_with_a_valid_normalised_repository_name(self) -> None:
        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "config").mkdir()
            pyproject = repo / "pyproject.toml"
            pyproject.write_text('[project]\nname = "template-django"\n')
            config = repo / "config" / "dev.toml"
            config.write_text('project_id = "template-django"\nstartup_timeout = 60\n')

            changed = update_project_identity(repo, "__My.Project++")

            self.assertEqual(changed, (True, True))
            self.assertEqual(pyproject.read_text(), '[project]\nname = "my-project"\n')
            self.assertEqual(
                config.read_text(),
                'project_id = "my-project"\nstartup_timeout = 60\n',
            )

    def test_custom_project_name_is_preserved(self) -> None:
        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "config").mkdir()
            pyproject = repo / "pyproject.toml"
            pyproject.write_text('[project]\nname = "already-custom"\n')
            config = repo / "config" / "dev.toml"
            config.write_text('project_id = "already-custom"\n')

            changed = update_project_identity(repo, "ignored-repository-name")

            self.assertEqual(changed, (False, False))
            self.assertEqual(pyproject.read_text(), '[project]\nname = "already-custom"\n')
            self.assertEqual(config.read_text(), 'project_id = "already-custom"\n')

    def test_existing_package_identity_is_used_when_adding_project_id(self) -> None:
        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "config").mkdir()
            pyproject = repo / "pyproject.toml"
            pyproject.write_text('[project]\nname = "Existing.Package"\n')
            config = repo / "config" / "dev.toml"
            config.write_text("startup_timeout = 60\n")

            changed = update_project_identity(repo, "different-origin-name")

            self.assertEqual(changed, (False, True))
            self.assertEqual(pyproject.read_text(), '[project]\nname = "Existing.Package"\n')
            self.assertEqual(
                config.read_text(),
                'project_id = "existing-package"\n\nstartup_timeout = 60\n',
            )

    def test_invalid_repository_name_does_not_modify_the_template(self) -> None:
        with TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "config").mkdir()
            pyproject = repo / "pyproject.toml"
            original = '[project]\nname = "template-django"\n'
            pyproject.write_text(original)
            config = repo / "config" / "dev.toml"
            original_config = 'project_id = "template-django"\n'
            config.write_text(original_config)

            with self.assertRaisesRegex(ValueError, "Could not derive"):
                update_project_identity(repo, "___")

            self.assertEqual(pyproject.read_text(), original)
            self.assertEqual(config.read_text(), original_config)


if __name__ == "__main__":
    unittest.main()
