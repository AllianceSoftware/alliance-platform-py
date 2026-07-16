from __future__ import annotations

from importlib import metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class DistributionTests(unittest.TestCase):
    def test_distribution_metadata_and_console_entry_point_are_installed(self) -> None:
        self.assertTrue(metadata.version("alliance-platform-dev"))
        entry_points = metadata.entry_points(group="console_scripts", name="alliance-dev")
        self.assertEqual(
            [entry_point.value for entry_point in entry_points],
            ["alliance_platform.dev.cli:main"],
        )

    def test_console_and_module_report_version_without_a_consumer_project(self) -> None:
        console = shutil.which("alliance-dev")
        self.assertIsNotNone(console)
        with TemporaryDirectory() as temporary:
            environment = dict(os.environ)
            environment.pop("ALLIANCE_DEV_PROJECT_DIR", None)
            commands = (
                [str(console), "--version"],
                [sys.executable, "-m", "alliance_platform.dev", "--version"],
            )
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(
                        command,
                        cwd=Path(temporary),
                        env=environment,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("alliance-platform-dev", result.stdout)
                    self.assertIn("protocol 1", result.stdout)


if __name__ == "__main__":
    unittest.main()
