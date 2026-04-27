import shutil
from pathlib import Path
from uuid import uuid4

TEST_TMPDIR = Path(".tmp-test") / "tempdir"
TEST_TMPDIR.mkdir(parents=True, exist_ok=True)


class WorkspaceTemporaryDirectory:
    """Workspace-local TemporaryDirectory replacement for sandboxed test runs."""

    def __init__(self, root: Path | None = None):
        self._root = root or TEST_TMPDIR
        path = self._root / uuid4().hex
        path.mkdir(parents=True, exist_ok=False)
        self._path = path.resolve()
        self.name = str(self._path)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        if self._path is None:
            return
        shutil.rmtree(self._path, ignore_errors=True)
        self._path = None
