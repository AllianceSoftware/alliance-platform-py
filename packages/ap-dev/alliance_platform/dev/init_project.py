from __future__ import annotations

from pathlib import Path
import re
import sys
import tomllib

TEMPLATE_PROJECT_ID = "template-django"


def normalise_project_name(repository_name: str) -> str:
    project_name = re.sub(r"[^a-z0-9]+", "-", repository_name.lower()).strip("-")
    if not project_name:
        raise ValueError(f"Could not derive a project name from {repository_name!r}")
    return project_name


def _project_name(contents: str) -> str:
    value = tomllib.loads(contents)
    project = value.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(name, str) or not name:
        raise ValueError("pyproject.toml must define [project].name")
    return name


def update_project_identity(repo: Path, repository_name: str) -> tuple[bool, bool]:
    pyproject_path = repo / "pyproject.toml"
    config_path = repo / "config" / "dev.toml"
    pyproject_contents = pyproject_path.read_text()
    config_contents = config_path.read_text()
    current_project_name = _project_name(pyproject_contents)

    if current_project_name == TEMPLATE_PROJECT_ID:
        project_name = normalise_project_name(repository_name)
        updated_pyproject = re.sub(
            r'(?m)^name\s*=\s*"template-django"[ \t]*$',
            f'name = "{project_name}"',
            pyproject_contents,
            count=1,
        )
    else:
        project_name = normalise_project_name(current_project_name)
        updated_pyproject = pyproject_contents

    config = tomllib.loads(config_contents)
    current_project_id = config.get("project_id")
    if current_project_id in {None, TEMPLATE_PROJECT_ID}:
        assignment = f'project_id = "{project_name}"'
        if current_project_id is None:
            updated_config = f"{assignment}\n\n{config_contents.lstrip()}"
        else:
            updated_config = re.sub(
                r"(?m)^project_id\s*=.*$",
                assignment,
                config_contents,
                count=1,
            )
    else:
        updated_config = config_contents

    pyproject_changed = updated_pyproject != pyproject_contents
    config_changed = updated_config != config_contents
    if pyproject_changed:
        pyproject_path.write_text(updated_pyproject)
    if config_changed:
        config_path.write_text(updated_config)
    return pyproject_changed, config_changed


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: python -m alliance_platform.dev.init_project <repository-name>", file=sys.stderr)
        return 2
    try:
        update_project_identity(Path.cwd(), argv[0])
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
