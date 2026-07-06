import io
import os
import uuid
import logging
import tempfile
from pathlib import Path
from backend.app.core.config import settings
from backend.app.core.minio import minio_client
from backend.app.core.logging import get_logger

logger = get_logger(__name__)

class StorageError(Exception):
    """Raised when S3/MinIO storage operations fail."""
    pass

def upload_file_to_minio(
    file_bytes: bytes,
    content_type: str,
    original_filename: str,
    custom_key: str = None
) -> str:
    """
    Uploads a file to MinIO object storage.
    
    Generates a unique file_id, uploads the file bytes stream, and logs details.
    Raises StorageError if upload fails.
    """
    try:
        if custom_key:
            object_key = custom_key
            parts = custom_key.split("/")
            if len(parts) >= 2:
                file_id = parts[-2]
            else:
                file_id = str(uuid.uuid4())
        else:
            file_id = str(uuid.uuid4())
            object_key = f"{file_id}/{original_filename}"
            
        bucket_name = settings.MINIO_BUCKET
        file_size = len(file_bytes)
        
        # Upload object using raw bytes stream
        minio_client.put_object(
            bucket_name=bucket_name,
            object_name=object_key,
            data=io.BytesIO(file_bytes),
            length=file_size,
            content_type=content_type
        )
        
        # Log metadata as requested
        logger.info(
            "File successfully uploaded to MinIO",
            extra={
                "custom_fields": {
                    "file_id": file_id,
                    "original_filename": original_filename,
                    "bucket_name": bucket_name,
                    "object_key": object_key,
                    "file_size": file_size,
                    "file_size_bytes": file_size
                }
            }
        )
        return file_id
    except Exception as e:
        logger.error(
            f"Failed to upload file to MinIO: {e}",
            exc_info=True,
            extra={
                "custom_fields": {
                    "original_filename": original_filename,
                    "content_type": content_type
                }
            }
        )
        raise StorageError(f"Upload failed: {e}") from e

def download_file_from_minio(file_id: str) -> str:
    """
    Downloads a file from MinIO S3 bucket to a local temp file.
    
    Finds the S3 object key starting with the prefix `{file_id}/` or containing
    `/{file_id}/` inside `project/`, downloads it preserving the original file extension,
    and logs details.
    Raises StorageError if the object is not found or download fails.
    """
    bucket_name = settings.MINIO_BUCKET
    try:
        # 1. Find matched object by prefix
        prefix = f"{file_id}/"
        objects = minio_client.list_objects(bucket_name, prefix=prefix, recursive=True)
        matched_objects = list(objects)
        
        if not matched_objects:
            # Fallback: List objects under prefix "project/" and search for containing folder /{file_id}/
            objects = minio_client.list_objects(bucket_name, prefix="project/", recursive=True)
            for obj in objects:
                if f"/documents/{file_id}/" in obj.object_name or f"/{file_id}/" in obj.object_name:
                    matched_objects = [obj]
                    break
        
        if not matched_objects:
            raise StorageError(f"No object found matching prefix or containing ID: {file_id}")
            
        object_key = matched_objects[0].object_name
        
        # 2. Extract suffix to preserve extension
        suffix = Path(object_key).suffix
        
        # 3. Define local temporary file path
        temp_dir = tempfile.gettempdir()
        temp_filename = f"{file_id}{suffix}"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        # 4. Download S3 object to local file
        minio_client.fget_object(bucket_name, object_key, temp_path)
        
        # 5. Log download details
        logger.info(
            "Successfully downloaded file from MinIO",
            extra={
                "custom_fields": {
                    "file_id": file_id,
                    "bucket": bucket_name,
                    "matched_object_key": object_key,
                    "local_temp_path": temp_path
                }
            }
        )
        return temp_path
        
    except StorageError:
        # Re-raise custom StorageError directly
        raise
    except Exception as e:
        logger.error(
            f"Failed to download file {file_id} from MinIO: {e}",
            exc_info=True,
            extra={
                "custom_fields": {
                    "file_id": file_id,
                    "bucket": bucket_name
                }
            }
        )
        raise StorageError(f"Download failed: {e}") from e
