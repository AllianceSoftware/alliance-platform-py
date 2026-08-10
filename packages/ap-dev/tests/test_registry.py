from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from alliance_platform.dev.config import load_config
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.identity import legacy_database_name
from alliance_platform.dev.identity import resolve_identity
from alliance_platform.dev.registry import RegistryStore
from alliance_platform.dev.registry import registry_root

from tests.helpers import init_git
from tests.helpers import make_repo


class RegistryStoreTests(unittest.TestCase):
    def make_store(self, root: Path) -> RegistryStore:
        repo = make_repo(root / "repo")
        init_git(repo, "feature/registry")
        config = load_config(repo, environ={"XDG_CONFIG_HOME": str(root / "config")})
        identity = resolve_identity(repo, config)
        return RegistryStore(
            repo,
            config,
            identity,
            environ={
                "HOME": str(root / "home"),
                "XDG_STATE_HOME": str(root / "state"),
                "ALLIANCE_DEV_OWNER_KIND": "agent",
                "ALLIANCE_DEV_OWNER_ID": "task-123",
                "ALLIANCE_DEV_LEASE_EXPIRES_AT": "2026-07-21T00:00:00Z",
            },
        )

    def test_registry_root_uses_xdg_state_home_with_home_fallback(self) -> None:
        self.assertEqual(
            registry_root({"XDG_STATE_HOME": "/state", "HOME": "/home"}),
            Path("/state/alliance/dev/registry/v1"),
        )
        self.assertEqual(
            registry_root({"HOME": "/home"}),
            Path("/home/.local/state/alliance/dev/registry/v1"),
        )

    def test_entry_tracks_database_process_and_agent_lifecycle(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = self.make_store(root)

            registered = store.register()
            setup = store.database_setup_started()
            ready = store.database_ready(created=True)
            running = store.started(django_port=8004, vite_port=5177)
            stopped = store.stopped(database_present=True)

            self.assertEqual(store.path.parent, root / "state/alliance/dev/registry/v1/demo-project")
            self.assertEqual(registered.owner_kind, "agent")
            self.assertEqual(registered.owner_id, "task-123")
            self.assertEqual(registered.lease_expires_at, "2026-07-21T00:00:00Z")
            self.assertTrue(setup.database_owned)
            self.assertTrue(setup.database_setup_pending)
            self.assertIsNotNone(setup.database_ownership_token)
            self.assertEqual(ready.database_ownership_token, setup.database_ownership_token)
            self.assertTrue(ready.database_present)
            self.assertIsNotNone(ready.database_created_at)
            self.assertEqual((running.django_port, running.vite_port), (8004, 5177))
            self.assertEqual(stopped.last_action, "stopped")
            self.assertTrue(stopped.database_present)
            self.assertEqual(store.load(), stopped)
            self.assertEqual(store.list_project(), (stopped,))
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.path.parent.stat().st_mode & 0o777, 0o700)

            value = json.loads(store.path.read_text())
            self.assertEqual(value["schemaVersion"], 1)
            self.assertEqual(value["environmentId"], stopped.worktree_id)
            self.assertEqual(value["resources"]["database"]["name"], stopped.database_name)

    def test_preexisting_database_is_registered_without_claiming_ownership(self) -> None:
        with TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))

            store.register()
            entry = store.database_ready(created=False)

            self.assertTrue(entry.database_present)
            self.assertFalse(entry.database_owned)
            self.assertIsNone(entry.database_ownership_token)

    def test_invalid_entry_is_rejected_and_remove_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            store.path.parent.mkdir(parents=True)
            store.path.write_text('{"schemaVersion": 99}\n')

            with self.assertRaisesRegex(DevError, "Invalid dev registry entry"):
                store.load()
            with self.assertRaisesRegex(DevError, "Invalid dev registry entry"):
                store.list_project()

            store.remove()
            store.remove()
            self.assertFalse(store.path.exists())

    def test_legacy_long_database_identity_requires_explicit_environment_cleanup(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            repo = make_repo(
                root / "cleanbins-bin-dev-long-worktree-name",
                config='project_id = "clean-bins-waste-comp-platform"\n',
            )
            init_git(repo, "feature/registry")
            config = load_config(repo, environ={"XDG_CONFIG_HOME": str(root / "config")})
            identity = resolve_identity(repo, config)
            store = RegistryStore(repo, config, identity, root=root / "state")
            current = store.register()
            stem, _, path_hash = identity.worktree_id.rpartition("-")
            legacy_name = legacy_database_name(config.project_slug, stem, path_hash)
            self.assertNotEqual(legacy_name, identity.database_name)
            store.save_project_entry(replace(current, database_name=legacy_name))

            with self.assertRaisesRegex(
                DevError,
                rf"previous naming limit.*env remove {identity.worktree_id}.*then run.*up",
            ):
                store.load()

    def test_atomic_save_leaves_no_temporary_files(self) -> None:
        with TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))

            store.register()
            store.started(django_port=8000, vite_port=5173)

            self.assertEqual([path.name for path in store.path.parent.iterdir()], [store.path.name])

    def test_cleanup_transitions_are_durable_before_registry_removal(self) -> None:
        with TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            store.register()
            owned = store.database_setup_started()
            ready = store.database_ready(created=True)

            pending = store.cleanup_started(ready, session_stopped=True)
            removed = store.database_removed(pending)

            self.assertEqual(pending.last_action, "cleanupPending")
            self.assertEqual(pending.database_ownership_token, owned.database_ownership_token)
            self.assertEqual(removed.last_action, "databaseRemoved")
            self.assertFalse(removed.database_present)
            self.assertFalse(removed.database_setup_pending)

            store.remove_project_entry(removed.worktree_id)
            self.assertIsNone(store.load_project_entry(removed.worktree_id))

    def test_registry_environment_ids_cannot_escape_the_project_directory(self) -> None:
        with TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))

            with self.assertRaisesRegex(DevError, "Invalid registry environment ID"):
                store.remove_project_entry("../another-project/entry")

    def test_registry_filename_must_match_the_stored_environment_id(self) -> None:
        with TemporaryDirectory() as directory:
            store = self.make_store(Path(directory))
            store.register()
            mismatched = store.path.with_name("different-0123456789.json")
            store.path.replace(mismatched)

            with self.assertRaisesRegex(DevError, "filename does not match"):
                store.list_project()


if __name__ == "__main__":
    unittest.main()
