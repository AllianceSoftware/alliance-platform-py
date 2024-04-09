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
    success = True
    for package in get_packages(root / "packages"):
        if not is_published(package, repository == "testpypi"):
            name_upper = package.name.replace("-", "_").upper()
            token = os.environ.get(f"{name_upper}_TOKEN")
            if not token:
                logger.error(
                    f"Missing token for {package.name}. Set the environment variable {name_upper}_TOKEN."
                )
                continue
            args = [
                "pdm",
                "publish",
                "-p",
                str(package.path.relative_to(root)),
                "--username",
                "__token__",
                "--password",
                token,
            ]
            if repository:
                args += ["--repository", repository]
            if verbose:
                args.append("-vv")
            result = subprocess.run(args)
            if result.returncode != 0:
                success = False
                logger.error(f"Failed to build {package.name}@{package.version}")
                continue
            version_str = f"{package.name}@{package.version}"
            subprocess.run(["git", "tag", version_str, "-m", version_str])
            # This output is needed by changesets to detect a new version was published:
            # https://github.com/changesets/action/blob/c62ef9792fd0502c89479ed856efe28575010472/src/run.ts#L139
            print(f"New tag: {version_str}")
    return success


if __name__ == "__main__":
    repository = os.environ.get("PYPI_PUBLISH_REPO")
    exit_code = 0 if publish(repository, os.environ.get("PDM_VERBOSE", 0) == "1") else 1
    sys.exit(exit_code)
