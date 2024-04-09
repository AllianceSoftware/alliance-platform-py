from dataclasses import dataclass
import json
import logging
from pathlib import Path

import requests

logger = logging.getLogger("alliance-platform-py")


@dataclass
class Package:
    path: Path
    name: str
    version: str


def is_published(package: Package, is_test=False):
    response = requests.get(
        f"https://{'test.' if is_test else ''}pypi.org/pypi/{package.name}/{package.version}/json"
    )
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
