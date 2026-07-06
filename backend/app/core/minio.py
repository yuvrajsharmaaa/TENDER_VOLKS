from urllib.parse import urlparse
from minio import Minio
from backend.app.core.config import settings

# Strip scheme if present (Minio client requires host:port format)
endpoint = settings.minio_endpoint
if "://" in endpoint:
    parsed = urlparse(endpoint)
    endpoint = parsed.netloc or parsed.path

# Initialize shared client
minio_client = Minio(
    endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False
)
