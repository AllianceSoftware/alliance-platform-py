import logging
import os
from pathlib import Path
import subprocess
import sys

from ap_scripts.utils import get_packages
from ap_scripts.utils import is_published

logger = logging.getLogger("alliance-platform-py")


def publish(repository: str | None = None, verbose=False):
    root = Path(__file__).parent.parent
    build_dir = root / "build_artifacts"
    build_dir.mkdir(exist_ok=True)
    success = True
    for package in get_packages(root / "packages"):
        if not is_published(package, repository == "testpypi"):
            # Build step
            build_args = [
                "uv",
                "build",
                "--package",
                package.name,
                "--out-dir",
                str(build_dir),
            ]
            logger.info(f"Building {package.name}@{package.version}")
            result = subprocess.run(build_args)
            if result.returncode != 0:
                success = False
                logger.error(f"Failed to build {package.name}@{package.version}")
                continue

            # Publish step
            name_upper = package.name.replace("-", "_").upper()
            token = os.environ.get(f"{name_upper}_TOKEN")
            if not token:
                logger.error(
                    f"Missing token for {package.name}. Set the environment variable {name_upper}_TOKEN."
                )
                continue

            # Find the built artifacts
            version = package.version.replace("+", ".")  # Handle local version identifiers
            wheel_pattern = f"{package.name.replace('-', '_')}-{version}*.whl"
            tarball_pattern = f"{package.name.replace('-', '_')}-{version}*.tar.gz"

            publish_args = [
                "uv",
                "publish",
                "--token",
                token,
            ]
            if repository:
                if repository == "testpypi":
                    publish_args += ["--publish-url", "https://test.pypi.org/legacy/"]
                else:
                    publish_args += ["--publish-url", "https://upload.pypi.org/legacy/"]

            # Add artifact files
            import glob

            artifacts = glob.glob(str(build_dir / wheel_pattern)) + glob.glob(
                str(build_dir / tarball_pattern)
            )
            if not artifacts:
                logger.error(f"No build artifacts found for {package.name}@{package.version}")
                success = False
                continue

            publish_args.extend(artifacts)

            if verbose:
                publish_args.append("--verbose")

            logger.info(f"Publishing {package.name}@{package.version}")
            result = subprocess.run(publish_args)
            if result.returncode != 0:
                success = False
                logger.error(f"Failed to publish {package.name}@{package.version}")
                continue
            version_str = f"{package.name}@{package.version}"
            subprocess.run(["git", "tag", version_str, "-m", version_str])
            # This output is needed by changesets to detect a new version was published:
            # https://github.com/changesets/action/blob/c62ef9792fd0502c89479ed856efe28575010472/src/run.ts#L139
            print(f"New tag: {version_str}")
    return success


if __name__ == "__main__":
    repository = os.environ.get("PYPI_PUBLISH_REPO")
    exit_code = 0 if publish(repository, os.environ.get("VERBOSE", 0) == "1") else 1
    sys.exit(exit_code)
