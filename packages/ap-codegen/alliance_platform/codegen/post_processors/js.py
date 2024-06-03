import json
import logging
from pathlib import Path
import subprocess

from alliance_platform.codegen.registry import ArtifactPostProcessor

logger = logging.getLogger("alliance_platform.frontend")


class JsPostProcessor(ArtifactPostProcessor):
    """Base class for post processors that run on JS files.

    Args:
       node_path: Path to node executable
       node_modules_dir: Path to the node modules directory
    """

    #: Path to the node executable
    node_path: Path
    #: Path to the node_modules directory
    node_modules_dir: Path

    def __init__(self, node_path: Path | str, node_modules_dir: Path | str):
        self.node_path = Path(node_path)
        self.node_modules_dir = Path(node_modules_dir)


class PrettierPostProcessor(JsPostProcessor):
    """Post processor that runs prettier on typescript, JS and JSON files.

    Args:
       node_path: Path to node executable
       node_modules_dir: Path to the node modules directory
       prettier_config: The path to a prettier config file
    """

    file_extensions = [".js", ".ts", ".tsx", ".jsx", ".json"]

    def __init__(
        self,
        node_path: Path | str,
        node_modules_dir: Path | str,
        *,
        prettier_config: Path | str | None = None,
    ):
        super().__init__(node_path, node_modules_dir)
        self.prettier_config = Path(prettier_config) if prettier_config else None

    def post_process(self, paths):
        def run_prettier():
            return subprocess.run(
                [
                    str(self.node_path),
                    str(self.node_modules_dir / ".bin/prettier"),
                    *paths,
                    *(["--config", str(self.prettier_config)] if self.prettier_config else []),
                    "--write",
                    "--log-level",
                    "warn",
                ],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        prettier = run_prettier()
        if prettier.returncode != 0:
            # On a rare occasion prettier will fail to run with an error about being unable
            # to open the file. In all my testing the file always exists so it's not clear
            # why this happen. Re-running prettier immediately after seems to always work (or
            # at least I'm yet to have it fail)
            prettier = run_prettier()
            if prettier.returncode != 0:
                logger.error("Prettier Failed:")
                logger.error(prettier.stderr.decode())
                logger.error(
                    "This could be because of issues writing files out to the default temporary location. "
                    "You can try setting 'ALLIANCE_PLATFORM['CODEGEN']['TEMP_DIR']=/private/tmp'"
                )
                return False
        return True


class EslintFixPostProcessor(JsPostProcessor):
    """Post processor that runs eslint --fix on typescript, JS, TSX and JSX files.

    Args:
        node_path: Path to node executable
        node_modules_dir: Path to the node modules directory
        plugins: Any eslint plugins to use
        rules: Any eslint rules to apply
    """

    file_extensions = [".js", ".ts", ".tsx", ".jsx"]

    #: List of eslint plugins to use
    plugins: list[str]
    #: Any eslint rules to apply
    rules: dict | None

    def __init__(
        self,
        node_path: Path | str,
        node_modules_dir: Path | str,
        *,
        plugins: list[str] | None = None,
        rules: dict | None,
    ):
        super().__init__(node_path, node_modules_dir)
        self.plugins = plugins or []
        self.rules = rules

    def post_process(self, paths):
        plugins = []
        for plugin in self.plugins:
            plugins += ["--plugin", plugin]
        rules = []
        if self.rules:
            rules = ["--rule", json.dumps(self.rules)]
        eslint = subprocess.run(
            [
                str(self.node_path),
                str(self.node_modules_dir / ".bin/eslint"),
                *paths,
                "--parser",
                "@typescript-eslint/parser",
                *plugins,
                *rules,
                "--fix",
            ],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if eslint.returncode != 0:
            logger.error("eslint --fix failed:")
            logger.error(eslint.stderr.decode())
            return False
