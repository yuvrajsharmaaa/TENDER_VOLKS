from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union
import os

class Settings(BaseSettings):
    app_name: str = "VolksEnergies Tender OCR"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"
    
    # Databases
    database_url: str
    redis_url: str
    
    # MinIO S3
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket_raw: str = "tender-raw"
    minio_bucket_processed: str = "tender-processed"
    
    # Day 3 uppercase MinIO settings
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "tender-pdfs"
    MINIO_USE_SSL: bool = False
    
    # Third party integrations
    gemini_api_key: Union[str, None] = None
    
    # CORS Origins
    allowed_origins: Union[str, List[str]] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    model_config = SettingsConfigDict(
        # Allow loading config from a file specified via environment variable
        env_file=os.getenv("ENV_FILE", ".env.dev"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate settings to trigger validation on import
settings = Settings()
