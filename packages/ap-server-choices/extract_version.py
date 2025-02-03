import json
from pathlib import Path


def get_version():
    return json.loads(Path("./package.json").read_text())["version"]
