from dataclasses import dataclass
from dataclasses import field
from functools import lru_cache
import json
import logging
from pathlib import Path
import tempfile
import time
import traceback
from typing import Callable
from typing import TypedDict

from alliance_platform.codegen.settings import ap_codegen_settings
from alliance_platform.core.settings import ap_core_settings

logger = logging.getLogger("alliance_platform.codegen")


@dataclass
class CodegenArtifact:
    """A data class representing a code generation artifact."""

    #: The output path for the artifact
    path: Path
    #: The contents of the artifact to be written to ``path``
    contents: str


class CodegenRegistrationCacheKey(TypedDict):
    """A TypedDict representing a cache key for a code generation registration."""

    #: The ID of the registration.
    registration_id: str
    #: A list of file paths that the code generation depends on.
    dependency_files: list[Path | str]


class CodegenRegistration:
    """
    A base class for code generation registrations.

    Subclasses should implement the `generate_artifacts` method.

    Optionally, ``get_cache_key`` can be used
    """

    def generate_artifacts(self) -> CodegenArtifact | list[CodegenArtifact]:
        """
        Generate the artifacts for this registration.

        Returns:
            CodegenArtifact | list[CodegenArtifact]: The generated artifacts.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def get_cache_key(self) -> None | CodegenRegistrationCacheKey:
        """
        Returns an identifier and a  list of file paths that this code generation depends on. The code generation should
        be re-triggered if any of these files change.

        If the code generation should always run, return ``None``.

        Note that caching is local to your machine.

        .. warning::

            Use this sparingly, as it can lead to cases where code generation does not run when it should. In particular,
            if details used in the code generation depend on state not captured in the ``cache`` key the cache won't
            be invalidated when it should be. For example, if you generated code for a specific class that was part
            of the cache key, but used details from a base class in a different file and that file changed then the
            cache would not be invalidated.
        """
        return None


@dataclass
class IntermediateArtifact:
    """
    A data class representing an intermediate artifact during code generation.

    Used internally.
    """

    #: The temporary file path of the artifact.
    temp_file_path: Path
    #: The final output path of the artifact.
    target_path: Path


class ArtifactPostProcessor:
    """
    A base class for post processors of code generation artifacts.

    Subclasses should implement the `post_process` method and provide a list of file extensions for the `file_extensions` attribute.
    """

    #: File extensions that this post processor should run on
    file_extensions: list[str]

    @lru_cache()
    def _validated_file_extensions(self):
        """
        Get the validated file extensions for this post processor.

        Returns:
            list[str]: The validated file extensions.
        """
        return [f".{ext}" if not ext.startswith(".") else ext for ext in self.file_extensions]

    def does_apply(self, path: Path):
        """
        Check if this post processor applies to a given path.

        Args:
            path (Path): The path to check.

        Returns:
            bool: True if this post processor applies to the path, False otherwise.
        """
        return path.suffix in self._validated_file_extensions()

    def post_process(self, paths: list[Path]):
        """
        Post process a list of paths.

        You can assume any path passed to this method will have already been filtered by the `does_apply` method.

        This method has no return value - all changes should be made in place.

        Args:
            paths (list[Path]): The paths to post process.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError


def post_process_artifacts(paths: list[Path]):
    """
    Post process a list of artifact paths.

    .. warning::
       This process happens in place and modifies the files on disk.

    Args:
        paths (list[Path]): The paths to post process.
    """
    for post_processor in ap_codegen_settings.POST_PROCESSORS:
        try:
            post_processor.post_process([p for p in paths if post_processor.does_apply(p)])
        except Exception:
            logger.exception(f"Error running post processor {post_processor}")


@dataclass
class CodegenStats:
    registration_count: int
    time_taken: float = 0
    aborted: bool = False
    abort_reason: None | str = None
    warnings: list[str] = field(default_factory=list)
    files_written: list[Path] = field(default_factory=list)

    def add_warning(self, warning: str):
        self.warnings.append(warning)


class CodegenRegistry:
    registration: list[CodegenRegistration]

    def __init__(self):
        self.registrations = []
        self.cache_path = ap_core_settings.CACHE_DIR / "codegen-artifact-cache.json"
        self.cache = json.loads(self.cache_path.read_text("utf8")) if self.cache_path.exists() else {}
        if not list(self.cache.keys()) == ["version", "entries"]:
            self.cache = {"version": 1, "entries": {}}
        if not isinstance(self.cache["entries"], dict):
            self.cache["entries"] = {}

    def register(self, registration: CodegenRegistration):
        self.registrations.append(registration)

    def invalidate_cache(self, registration: CodegenRegistration):
        cache_key = registration.get_cache_key()
        if not cache_key:
            return True
        registration_id = self._get_cache_registration_id(registration)
        if registration_id in self.cache["entries"]:
            del self.cache["entries"][registration_id]
            self.cache_path.write_text(json.dumps(self.cache, indent=2))

    def _get_cache_registration_id(self, registration: CodegenRegistration) -> str:
        cache_key = registration.get_cache_key()
        if not cache_key:
            raise ValueError("Registration has no cache key")
        class_id = f"{registration.__class__.__module__}.{registration.__class__.__qualname__}"
        return f'{class_id}.{cache_key["registration_id"]}'

    def has_dependencies_changed(self, registration: CodegenRegistration, stats: CodegenStats) -> bool:
        cache_key = registration.get_cache_key()
        if not cache_key:
            return True
        if not cache_key["dependency_files"]:
            stats.add_warning(
                f"Codegen registration {registration} `get_cache_key` lists no files; will always run"
            )
            return True
        registration_id = self._get_cache_registration_id(registration)
        entry = self.cache["entries"].get(registration_id, {})
        timestamps = {}
        for dependency in cache_key["dependency_files"]:
            dependency = Path(dependency)
            if not dependency.exists():
                stats.add_warning(f"Dependency file {dependency} does not exist")
                return True
            mtime = dependency.stat().st_mtime
            timestamps[str(dependency)] = mtime
        if entry != timestamps:
            self.cache["entries"][registration_id] = timestamps
            self.cache_path.write_text(json.dumps(self.cache, indent=2))
            return True
        return False

    def run_codegen(self, should_abort: Callable[[], str | bool] | None = None):
        start = time.time()
        if should_abort is None:

            def should_abort():
                return False

        files_to_write = []
        stats = CodegenStats(len(self.registrations))
        for registration in self.registrations:
            if not self.has_dependencies_changed(registration, stats):
                continue
            try:
                artifacts = registration.generate_artifacts()
            except Exception:
                stats.add_warning(f"Error generating artifacts for {registration}: {traceback.format_exc()}")
                self.invalidate_cache(registration)
                continue
            else:
                if not isinstance(artifacts, list):
                    artifacts = [artifacts]
                for artifact in artifacts:
                    suffix = Path(artifact.path).suffix
                    temp = tempfile.NamedTemporaryFile(
                        "w",
                        suffix=suffix,
                        delete=False,
                        dir=ap_codegen_settings.TEMP_DIR,
                    )
                    temp.write(artifact.contents)
                    temp.close()
                    files_to_write.append(IntermediateArtifact(Path(temp.name), artifact.path))

        def cleanup():
            for intermediate_file in files_to_write:
                intermediate_file.temp_file_path.unlink(missing_ok=True)

        abort_reason = should_abort()
        if abort_reason:
            if isinstance(abort_reason, str):
                stats.abort_reason = abort_reason
            stats.aborted = True
            cleanup()
            return stats

        if files_to_write:
            post_process_artifacts([f.temp_file_path for f in files_to_write])

        for intermediate_file in files_to_write:
            contents = intermediate_file.temp_file_path.read_text("utf8")
            if (
                not intermediate_file.target_path.exists()
                or intermediate_file.target_path.read_text("utf8") != contents
            ):
                intermediate_file.target_path.parent.mkdir(parents=True, exist_ok=True)
                intermediate_file.target_path.write_text(contents, "utf8")
                stats.files_written.append(intermediate_file.target_path)
        cleanup()
        stats.time_taken = time.time() - start
        return stats
