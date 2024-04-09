import logging
import os
from pathlib import Path
import re
import subprocess
import sys

from ap_scripts.utils import get_packages
from ap_scripts.utils import is_published

logger = logging.getLogger("alliance-platform-py")


def build_required(output_dir: Path, repository: str | None = None, verbose=False):
    """Build all packages that are not published yet. Return True if all packages were built successfully.

    All wheels are copied to the output_dir.
    """

    output_dir.mkdir(exist_ok=True, parents=True)
    root = Path(__file__).parent.parent
    success = True
    for package in get_packages(root / "packages"):
        if not is_published(package, repository == "testpypi"):
            args = [
                "pdm",
                "build",
                "-p",
                str(package.path.relative_to(root)),
            ]
            if verbose:
                args.append("-vv")
            result = subprocess.run(args, capture_output=True)
            if result.returncode != 0:
                success = False
                logger.error(f"Failed to build {package.name}@{package.version}")
                continue
            output = result.stdout.decode("utf8")
            try:
                wheel_file = Path(re.findall(r".*Built wheel at (.*.whl)", output)[0])
                (output_dir / wheel_file.name).write_bytes(wheel_file.read_bytes())
            except IndexError:
                logger.warning(f"Failed to find wheel file in output:\n{output}")
    return success


if __name__ == "__main__":
    repository = os.environ.get("PYPI_PUBLISH_REPO")
    output_dir = Path("build_artifacts")
    exit_code = 0 if build_required(output_dir, repository, os.environ.get("PDM_VERBOSE", 0) == "1") else 1
    sys.exit(exit_code)
