from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import subprocess

import requests

logger = logging.getLogger("alliance-platform-py")


@dataclass
class Package:
    path: Path
    name: str
    version: str


def is_published(package: Package):
    response = requests.get(f"https://pypi.org/pypi/{package.name}/{package.version}/json")
    return response.status_code == 200


def get_packages(base_dir: Path):
    for package_dir in base_dir.iterdir():
        if package_dir.is_dir():
            package_json_path = package_dir / "package.json"
            if package_json_path.exists():
                package_data = json.loads(package_json_path.read_text())
                package_name = package_data.get("name")
                package_version = package_data.get("version")
                yield Package(package_dir, package_name, package_version)
            else:
                logger.warning(f"{package_dir} does not have a package.json")


def publish(repository: str | None = None):
    root = Path(__file__).parent.parent
    for package in get_packages(root / "packages"):
        if not is_published(package):
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
            result = subprocess.run(args)
            if result.returncode != 0:
                logger.error(f"Failed to build {package.name}@{package.version}")
                continue
            version_str = f"{package.name}@{package.version}"
            subprocess.run(["git", "tag", version_str, "-m", version_str])
            # This output is needed by changesets to detect a new version was published:
            # https://github.com/changesets/action/blob/c62ef9792fd0502c89479ed856efe28575010472/src/run.ts#L139
            print(f"New tag: {version_str}")


if __name__ == "__main__":
    repository = os.environ.get("PYPI_PUBLISH_REPO")
    publish(repository)
