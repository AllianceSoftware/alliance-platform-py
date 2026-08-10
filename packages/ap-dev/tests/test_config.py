from __future__ import annotations

from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest

from alliance_platform.dev.config import ensure_private_file
from alliance_platform.dev.config import load_config
from alliance_platform.dev.errors import ConfigError

from tests.helpers import make_repo


class ConfigLayeringTests(unittest.TestCase):
    def test_layers_override_scalars_and_lists_while_merging_environment(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config="""
django_port_base = 8100
vite_port_base = 5100
createdevdata_args = ["base"]

[environment]
BASE_ONLY = "base"
SHARED = "base"
""".lstrip(),
            )
            xdg = root / "xdg"
            global_path = xdg / "alliance" / "dev" / "demo-project" / "config.toml"
            global_path.parent.mkdir(parents=True)
            global_path.write_text(
                """
django_port_base = 8200
createdevdata_args = ["global", "value with spaces"]

[environment]
GLOBAL_ONLY = "global"
SHARED = "global"
""".lstrip()
            )
            local_path = repo / ".dev-server" / "config.toml"
            local_path.parent.mkdir(parents=True)
            local_path.write_text(
                """
vite_port_base = 5300
portless = "off"

[environment]
LOCAL_ONLY = "local"
SHARED = "local"
""".lstrip()
            )

            config = load_config(repo, {"XDG_CONFIG_HOME": str(xdg)})

            self.assertEqual(config.django_port_base, 8200)
            self.assertEqual(config.vite_port_base, 5300)
            self.assertEqual(config.portless, "off")
            self.assertEqual(config.database_template_strategy, "default")
            self.assertEqual(config.verification_virtualenv, ".venv")
            self.assertEqual(config.jstest_command, ())
            self.assertEqual(config.lint_command, ())
            self.assertEqual(config.check_command, ())
            self.assertEqual(config.createdevdata_args, ("global", "value with spaces"))
            self.assertEqual(
                config.environment,
                {
                    "BASE_ONLY": "base",
                    "GLOBAL_ONLY": "global",
                    "LOCAL_ONLY": "local",
                    "SHARED": "local",
                },
            )
            self.assertEqual(config.setting_sources["django_port_base"], "global")
            self.assertEqual(config.setting_sources["vite_port_base"], "worktree")
            self.assertEqual(config.setting_sources["portless"], "worktree")
            self.assertEqual(config.setting_sources["createdevdata_args"], "global")
            self.assertEqual(config.setting_sources["startup_timeout"], "default")
            self.assertEqual(
                config.environment_sources,
                {
                    "BASE_ONLY": "project",
                    "GLOBAL_ONLY": "global",
                    "LOCAL_ONLY": "worktree",
                    "SHARED": "worktree",
                },
            )
            self.assertEqual(config.paths.project, repo.resolve() / "config" / "dev.toml")
            self.assertEqual(config.paths.worktree, repo.resolve() / ".dev-server" / "config.toml")

    def test_configured_commands_remain_argument_arrays(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dangerous = "value with spaces; $(touch should-not-exist)"
            repo = make_repo(
                root / "repo",
                config=f"""
db_prepare_command = ["prepare_worktree_db", "--label", "{dangerous}"]

[[extra_processes]]
name = "worker"
command = ["uv", "run", "worker", "{dangerous}"]
cwd = "django-root"
required = false
""".lstrip(),
            )

            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

            self.assertEqual(
                config.db_prepare_command,
                ("prepare_worktree_db", "--label", dangerous),
            )
            self.assertEqual(config.extra_processes[0].command, ("uv", "run", "worker", dangerous))
            self.assertFalse(config.extra_processes[0].required)

    def test_each_layer_is_validated_before_it_can_be_overridden(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            xdg = root / "xdg"
            global_path = xdg / "alliance" / "dev" / "demo-project" / "config.toml"
            global_path.parent.mkdir(parents=True)
            global_path.write_text("django_port_base = true\n")
            local_path = repo / ".dev-server" / "config.toml"
            local_path.parent.mkdir(parents=True)
            local_path.write_text("django_port_base = 9000\n")

            with self.assertRaisesRegex(ConfigError, "django_port_base.*must be int"):
                load_config(repo, {"XDG_CONFIG_HOME": str(xdg)})

    def test_project_id_is_rejected_in_an_override(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            xdg = root / "xdg"
            global_path = xdg / "alliance" / "dev" / "demo-project" / "config.toml"
            global_path.parent.mkdir(parents=True)
            global_path.write_text('project_id = "different-project"\n')

            with self.assertRaisesRegex(ConfigError, "project_id may only be set"):
                load_config(repo, {"XDG_CONFIG_HOME": str(xdg)})

    def test_reserved_environment_variables_are_rejected_in_every_layer(self) -> None:
        for layer in ("project", "global", "worktree"):
            with self.subTest(layer=layer), TemporaryDirectory() as temporary:
                root = Path(temporary)
                repo = make_repo(root / "repo")
                xdg = root / "xdg"
                if layer == "project":
                    path = repo / "config" / "dev.toml"
                    path.write_text('project_id = "demo-project"\n[environment]\nDB_NAME = "unsafe"\n')
                elif layer == "global":
                    path = xdg / "alliance" / "dev" / "demo-project" / "config.toml"
                    path.parent.mkdir(parents=True)
                    path.write_text('[environment]\nPGDATABASE = "unsafe"\n')
                else:
                    path = repo / ".dev-server" / "config.toml"
                    path.parent.mkdir(parents=True)
                    path.write_text('[environment]\nDEV_WORKTREE_ID = "unsafe"\n')

                with self.assertRaisesRegex(ConfigError, "cannot set reserved variable"):
                    load_config(repo, {"XDG_CONFIG_HOME": str(xdg)})

    def test_virtualenv_must_use_the_dedicated_setting(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config='[environment]\nVIRTUAL_ENV = ".venv"\n',
            )

            with self.assertRaisesRegex(ConfigError, "cannot set reserved variable VIRTUAL_ENV"):
                load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})


class ConfigValidationTests(unittest.TestCase):
    def test_invalid_config_shapes_are_rejected(self) -> None:
        cases = {
            "unknown key": ("unknown_key = true\n", "Unknown config key"),
            "boolean port": ("django_port_base = true\n", "must be int"),
            "port out of range": ("vite_port_base = 65536\n", "between 1 and 65535"),
            "invalid Portless policy": ('portless = "sometimes"\n', "auto.*off.*required"),
            "invalid database template strategy": (
                'database_template_strategy = "instant"\n',
                "default.*wal_log.*file_copy",
            ),
            "empty command": ("django_command = []\n", "must not be empty"),
            "optional command string": ('check_command = "bin/check.sh"\n', "must be list"),
            "zero timeout": ("startup_timeout = 0\n", "must be a positive number"),
            "invalid environment name": (
                '[environment]\n"BAD-NAME" = "value"\n',
                "string environment variables",
            ),
            "reserved process name": (
                '[[extra_processes]]\nname = "django"\ncommand = ["worker"]\n',
                "is reserved",
            ),
            "process command string": (
                '[[extra_processes]]\nname = "worker"\ncommand = "worker --flag"\n',
                "command must be list",
            ),
            "escaping cwd": (
                '[[extra_processes]]\nname = "worker"\ncommand = ["worker"]\ncwd = ".."\n',
                "must stay inside the repository",
            ),
            "escaping verification virtualenv": (
                'verification_virtualenv = "../shared-venv"\n',
                "verification_virtualenv.*must stay inside the repository",
            ),
        }
        for label, (body, expected) in cases.items():
            with self.subTest(label=label), TemporaryDirectory() as temporary:
                root = Path(temporary)
                repo = make_repo(root / "repo", config=body)
                with self.assertRaisesRegex(ConfigError, expected):
                    load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

    def test_malformed_toml_error_identifies_the_file(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo", config="django_port_base = [\n")

            with self.assertRaises(ConfigError) as raised:
                load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

            self.assertIn(str(repo / "config" / "dev.toml"), str(raised.exception))

    def test_camel_case_aliases_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo", config="djangoPortBase = 8100\n")

            with self.assertRaisesRegex(ConfigError, "Unknown config key.*djangoPortBase"):
                load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

    def test_legacy_portless_settings_are_rejected(self) -> None:
        for setting in ("disable_portless = true\n", 'portless_name = "demo"\n'):
            with self.subTest(setting=setting), TemporaryDirectory() as temporary:
                root = Path(temporary)
                repo = make_repo(root / "repo", config=setting)

                with self.assertRaisesRegex(ConfigError, "Unknown config key"):
                    load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

    def test_project_id_requires_the_exact_slug_format(self) -> None:
        for project_id in ("Project", "project_name", "project--name", "project-"):
            with self.subTest(project_id=project_id), TemporaryDirectory() as temporary:
                root = Path(temporary)
                repo = make_repo(root / "repo", config=f'project_id = "{project_id}"\n')

                with self.assertRaisesRegex(ConfigError, "lowercase slug"):
                    load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

    def test_missing_project_id_fails_with_the_required_committed_value(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                name="Existing.Package_Name",
                include_project_id=False,
            )

            with self.assertRaisesRegex(ConfigError, 'project_id = "existing-package-name"'):
                load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

    def test_changed_package_name_cannot_reuse_the_template_project_id(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                name="customer-project",
                config='project_id = "template-django"\n',
            )

            with self.assertRaisesRegex(ConfigError, 'project_id = "customer-project"'):
                load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

    def test_private_config_creation_uses_user_only_permissions(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "xdg" / "alliance" / "dev" / "demo-project" / "config.toml"

            ensure_private_file(path)

            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            for directory in (
                root / "xdg",
                root / "xdg" / "alliance",
                root / "xdg" / "alliance" / "dev",
                path.parent,
            ):
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)


if __name__ == "__main__":
    unittest.main()
