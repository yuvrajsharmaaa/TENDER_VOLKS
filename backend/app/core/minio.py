"""
Local-disk object storage shim.

The original codebase depended on a real MinIO server (docker-compose sidecar).
Replit has no such service, and standing one up would mean running an extra
long-lived process for an MVP that just needs "save this PDF, read it back
later" — so this module keeps the exact call sites used elsewhere
(backend/app/services/storage.py, backend/app/api/routes/{tenders,health}.py,
backend/app/main.py) working unchanged by re-implementing the small subset of
the `minio.Minio` client surface they actually use, backed by files on disk
under STORAGE_ROOT/objects/<bucket>/<key>.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, List, Optional

from backend.app.core.config import settings
from backend.app.core.constants import STORAGE_ROOT

OBJECTS_ROOT = STORAGE_ROOT / "objects"


@dataclass
class _ObjectInfo:
    object_name: str


class LocalObjectStore:
    """Drop-in, disk-backed replacement for the subset of minio.Minio used here."""

    def __init__(self, root: Path = OBJECTS_ROOT):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _bucket_dir(self, bucket_name: str) -> Path:
        return self.root / bucket_name

    def _safe_object_path(self, bucket_name: str, object_name: str) -> Path:
        """
        Resolves an object key to a path under the bucket directory, rejecting
        any key that would escape it (absolute paths, `..` traversal, etc.).

        Object keys in this app are built from caller-controlled values
        (tender/project ids, uploaded filenames) and used directly as
        filesystem paths, so this check is a required guard against path
        traversal — not an optional hardening step.
        """
        bucket_dir = self._bucket_dir(bucket_name).resolve()
        candidate = (bucket_dir / object_name).resolve()
        try:
            candidate.relative_to(bucket_dir)
        except ValueError:
            raise ValueError(f"Invalid object key (escapes bucket root): {object_name!r}")
        return candidate

    def bucket_exists(self, bucket_name: str) -> bool:
        return self._bucket_dir(bucket_name).is_dir()

    def make_bucket(self, bucket_name: str) -> None:
        self._bucket_dir(bucket_name).mkdir(parents=True, exist_ok=True)

    def list_buckets(self) -> List[str]:
        if not self.root.exists():
            return []
        return [p.name for p in self.root.iterdir() if p.is_dir()]

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: Optional[str] = None,
    ) -> None:
        dest = self._safe_object_path(bucket_name, object_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data.read())

    def list_objects(self, bucket_name: str, prefix: str = "", recursive: bool = True) -> Iterable[_ObjectInfo]:
        bucket_dir = self._bucket_dir(bucket_name)
        if not bucket_dir.exists():
            return []
        results = []
        for path in bucket_dir.rglob("*"):
            if path.is_file():
                rel = path.relative_to(bucket_dir).as_posix()
                if rel.startswith(prefix):
                    results.append(_ObjectInfo(object_name=rel))
        return results

    def fget_object(self, bucket_name: str, object_name: str, file_path: str) -> None:
        src = self._safe_object_path(bucket_name, object_name)
        if not src.exists():
            raise FileNotFoundError(f"Object not found: {bucket_name}/{object_name}")
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        Path(file_path).write_bytes(src.read_bytes())

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        target = self._safe_object_path(bucket_name, object_name)
        if target.exists():
            target.unlink()


# Shared instance used throughout the backend in place of a real MinIO client.
minio_client = LocalObjectStore()
