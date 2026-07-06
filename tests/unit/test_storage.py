import pytest
from unittest.mock import MagicMock, patch
from backend.app.services.storage import (
    upload_file_to_minio,
    download_file_from_minio,
    StorageError
)

from backend.app.core.config import settings

def test_download_file_from_minio_success():
    """
    Verifies that download_file_from_minio resolves the matched S3 object,
    downloads it locally preserving the extension, and returns the path.
    """
    mock_object = MagicMock()
    mock_object.object_name = "test-file-id/tender_goa_2026.pdf"
    
    with patch("backend.app.services.storage.minio_client") as mock_client:
        mock_client.list_objects.return_value = [mock_object]
        mock_client.fget_object = MagicMock()
        
        file_id = "test-file-id"
        temp_path = download_file_from_minio(file_id)
        
        assert isinstance(temp_path, str)
        assert temp_path.endswith(f"{file_id}.pdf")
        
        # Verify minio calls
        mock_client.list_objects.assert_called_once_with(
            settings.MINIO_BUCKET, prefix=f"{file_id}/", recursive=True
        )
        mock_client.fget_object.assert_called_once_with(
            settings.MINIO_BUCKET, mock_object.object_name, temp_path
        )

def test_download_file_from_minio_not_found():
    """
    Verifies that download_file_from_minio raises StorageError when no object matches prefix.
    """
    with patch("backend.app.services.storage.minio_client") as mock_client:
        mock_client.list_objects.return_value = []
        
        file_id = "nonexistent-file-id"
        with pytest.raises(StorageError) as exc_info:
            download_file_from_minio(file_id)
            
        assert "No object found matching prefix" in str(exc_info.value)

def test_download_file_from_minio_failure():
    """
    Verifies that exceptions during downloading (fget_object) are wrapped in StorageError.
    """
    mock_object = MagicMock()
    mock_object.object_name = "test-file-id/tender_goa_2026.pdf"
    
    with patch("backend.app.services.storage.minio_client") as mock_client:
        mock_client.list_objects.return_value = [mock_object]
        mock_client.fget_object.side_effect = Exception("Disk Write Permission Error")
        
        file_id = "test-file-id"
        with pytest.raises(StorageError) as exc_info:
            download_file_from_minio(file_id)
            
        assert "Download failed" in str(exc_info.value)

def test_upload_file_to_minio_success():
    """
    Verifies that upload_file_to_minio generates a unique ID, builds the correct S3 key,
    calls put_object with the expected arguments, and returns the file_id.
    """
    with patch("backend.app.services.storage.minio_client") as mock_client:
        mock_client.put_object = MagicMock()
        
        file_bytes = b"Tender PDF Document Content Placeholder"
        content_type = "application/pdf"
        original_filename = "tender_goa_2026.pdf"
        
        file_id = upload_file_to_minio(file_bytes, content_type, original_filename)
        
        assert isinstance(file_id, str)
        assert len(file_id) > 0
        
        # Verify minio_client.put_object was called with correct arguments
        mock_client.put_object.assert_called_once()
        kwargs = mock_client.put_object.call_args[1]
        
        assert kwargs["bucket_name"] == settings.MINIO_BUCKET
        assert kwargs["content_type"] == content_type
        assert kwargs["length"] == len(file_bytes)
        assert kwargs["object_name"] == f"{file_id}/{original_filename}"

def test_upload_file_to_minio_failure():
    """
    Verifies that any upload exception from the MinIO client is wrapped and raised
    as a custom StorageError.
    """
    with patch("backend.app.services.storage.minio_client") as mock_client:
        mock_client.put_object.side_effect = Exception("Network Connection Refused by S3 Endpoint")
        
        file_bytes = b"Corrupted or Interrupted Content"
        content_type = "application/pdf"
        original_filename = "failed_upload.pdf"
        
        with pytest.raises(StorageError) as exc_info:
            upload_file_to_minio(file_bytes, content_type, original_filename)
            
        assert "Upload failed" in str(exc_info.value)
