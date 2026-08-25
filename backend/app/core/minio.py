"""
Local-disk object storage shim.

Re-implements the subset of the `minio.Minio` client surface used by the application,
backed by files on disk under STORAGE_ROOT/objects/<bucket>/<key>.
"""
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, List, Optional

try:
    from minio import Minio
except ImportError:
    Minio = None  # type: ignore

from backend.app.core.config import settings
from backend.app.core.constants import STORAGE_ROOT

logger = logging.getLogger(__name__)

# Dynamic objects root evaluated from constants.STORAGE_ROOT
def get_objects_root() -> Path:
    return STORAGE_ROOT / "objects"

OBJECTS_ROOT = get_objects_root()


@dataclass
class _ObjectInfo:
    object_name: str


class LocalObjectStore:
    """Drop-in, disk-backed replacement for the subset of minio.Minio used here."""

    def __init__(self, root: Optional[Path] = None):
        self._custom_root = root

    @property
    def root(self) -> Path:
        if self._custom_root is not None:
            return self._custom_root
        return get_objects_root()

    def _ensure_root(self) -> None:
        """Safely creates the root storage directory on demand."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Unable to create storage root directory {self.root}: {e}")

    def _bucket_dir(self, bucket_name: str) -> Path:
        if not bucket_name or "/" in bucket_name or "\\" in bucket_name or bucket_name in (".", "..") or bucket_name.startswith("."):
            raise ValueError(f"Invalid bucket name: {bucket_name!r}")
        return self.root / bucket_name

    def _safe_object_path(self, bucket_name: str, object_name: str) -> Path:
        """
        Resolves an object key to a path under the bucket directory, rejecting
        any key that would escape it (absolute paths, `..` traversal, etc.).
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
        self._ensure_root()
        try:
            self._bucket_dir(bucket_name).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning(f"Unable to create bucket directory {bucket_name}: {e}")

    def list_buckets(self) -> List[str]:
        if not self.root.exists():
            return []
        try:
            return [p.name for p in self.root.iterdir() if p.is_dir()]
        except OSError:
            return []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: Optional[str] = None,
    ) -> None:
        self._ensure_root()
        dest = self._safe_object_path(bucket_name, object_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            if length is not None and length > 0:
                f.write(data.read(length))
            else:
                f.write(data.read())


    def list_objects(self, bucket_name: str, prefix: str = "", recursive: bool = True) -> Iterable[_ObjectInfo]:
        bucket_dir = self._bucket_dir(bucket_name)
        if not bucket_dir.exists():
            return []
        results = []
        try:
            for path in bucket_dir.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(bucket_dir).as_posix()
                    if rel.startswith(prefix):
                        results.append(_ObjectInfo(object_name=rel))
        except OSError:
            pass
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
            try:
                target.unlink()
            except OSError as e:
                logger.warning(f"Failed to remove object {bucket_name}/{object_name}: {e}")


class MinioObjectStore:
    """Real S3/MinIO-backed object storage implementation using official minio SDK."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: Optional[bool] = None,
        default_bucket: Optional[str] = None,
    ):
        raw_endpoint = (
            endpoint
            or os.getenv("MINIO_ENDPOINT")
            or getattr(settings, "MINIO_ENDPOINT", None)
            or getattr(settings, "minio_endpoint", "localhost:9000")
        )
        self._access_key = (
            access_key
            or os.getenv("MINIO_ACCESS_KEY")
            or getattr(settings, "MINIO_ACCESS_KEY", None)
            or getattr(settings, "minio_access_key", "minioadmin")
        )
        self._secret_key = (
            secret_key
            or os.getenv("MINIO_SECRET_KEY")
            or getattr(settings, "MINIO_SECRET_KEY", None)
            or getattr(settings, "minio_secret_key", "minioadmin")
        )

        if secure is not None:
            self._secure = secure
        else:
            sec_env = os.getenv("MINIO_SECURE") or os.getenv("MINIO_USE_SSL")
            if sec_env is not None:
                self._secure = sec_env.lower() in ("true", "1", "yes")
            else:
                self._secure = getattr(
                    settings, "MINIO_SECURE", getattr(settings, "MINIO_USE_SSL", False)
                )

        self.default_bucket = (
            default_bucket
            or os.getenv("MINIO_BUCKET")
            or getattr(settings, "MINIO_BUCKET", "tender-pdfs")
        )

        endpoint_clean = raw_endpoint
        if "://" in endpoint_clean:
            if endpoint_clean.startswith("https://"):
                self._secure = True
            endpoint_clean = endpoint_clean.split("://", 1)[1]
        self._endpoint = endpoint_clean.rstrip("/")

        from minio import Minio
        self._client = Minio(
            endpoint=self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
        )
        logger.info(
            f"Initialized MinioObjectStore client pointing to {self._endpoint} (secure={self._secure})"
        )

    def ensure_default_bucket(self) -> None:
        """Ensures the configured default bucket exists on startup (creates if missing)."""
        try:
            if self.default_bucket and not self.bucket_exists(self.default_bucket):
                self.make_bucket(self.default_bucket)
                logger.info(f"Created default MinIO bucket: {self.default_bucket}")
        except Exception as e:
            logger.warning(
                f"Could not auto-verify/create default bucket {self.default_bucket} on startup: {e}"
            )

    def bucket_exists(self, bucket_name: str) -> bool:
        return self._client.bucket_exists(bucket_name)

    def make_bucket(self, bucket_name: str) -> None:
        if not self._client.bucket_exists(bucket_name):
            self._client.make_bucket(bucket_name)

    def list_buckets(self) -> List[str]:
        buckets = self._client.list_buckets()
        return [b.name for b in buckets]

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: Optional[str] = None,
    ) -> None:
        if not self.bucket_exists(bucket_name):
            self.make_bucket(bucket_name)
        part_size = 10 * 1024 * 1024 if length is None or length < 0 else 0
        self._client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            length=length if length is not None else -1,
            part_size=part_size,
            content_type=content_type or "application/octet-stream",
        )

    def list_objects(
        self, bucket_name: str, prefix: str = "", recursive: bool = True
    ) -> Iterable[_ObjectInfo]:
        objs = self._client.list_objects(bucket_name, prefix=prefix, recursive=recursive)
        return [_ObjectInfo(object_name=obj.object_name) for obj in objs]

    def fget_object(self, bucket_name: str, object_name: str, file_path: str) -> None:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        self._client.fget_object(bucket_name, object_name, file_path)

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self._client.remove_object(bucket_name, object_name)


def get_object_store():
    """
    Returns MinioObjectStore if minio SDK is available and configured,
    otherwise falls back gracefully to LocalObjectStore.
    """
    if Minio is not None:
        try:
            return MinioObjectStore()
        except Exception as e:
            logger.warning(
                f"Failed to initialize MinioObjectStore, falling back to LocalObjectStore: {e}"
            )
            return LocalObjectStore()
    else:
        logger.warning(
            "minio Python package not installed; falling back to LocalObjectStore. "
            "Rebuild backend container with: docker compose -f infra/docker-compose.dev.yml up -d --build backend"
        )
        return LocalObjectStore()


# Default object store used across the application.
minio_client = get_object_store()
