import os
import sys
from urllib.parse import urlparse
import psycopg2
import redis
from minio import Minio

# Include project root in python search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set dummy env vars for local host testing since internal compose dns hostnames (e.g. postgres, redis, minio)
# resolve only inside the compose network, but this script runs on the host machine.
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/tender_db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

from backend.app.core.config import settings

def test_connections():
    print("=========================================================="
          "\nIntegration Test: Checking Backend Connectivity"
          "\n==========================================================")
    
    # 1. Check PostgreSQL
    print("1. Connecting to PostgreSQL...")
    try:
        conn = psycopg2.connect(settings.database_url, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            print(f"   [OK] PostgreSQL version: {version}")
        conn.close()
    except Exception as e:
        print(f"   [FAILED] PostgreSQL connection failed: {e}")
        
    # 2. Check Redis
    print("2. Connecting to Redis...")
    try:
        r = redis.Redis.from_url(settings.redis_url, socket_timeout=3)
        if r.ping():
            print("   [OK] Redis ping: SUCCESS")
        else:
            print("   [FAILED] Redis did not respond to ping.")
    except Exception as e:
        print(f"   [FAILED] Redis connection failed: {e}")
        
    # 3. Check MinIO and upload test file
    print("3. Connecting to MinIO S3 & Uploading file...")
    try:
        endpoint = settings.minio_endpoint
        if "://" in endpoint:
            parsed = urlparse(endpoint)
            endpoint = parsed.netloc or parsed.path
            
        client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False
        )
        
        # Ensure raw bucket exists
        bucket = settings.minio_bucket_raw
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            print(f"   Created bucket '{bucket}'")
            
        # Upload dummy tender document content
        test_file = "test_tender.txt"
        test_content = b"VolksEnergies Tender OCR Integration Test Document Content."
        
        import io
        data_stream = io.BytesIO(test_content)
        client.put_object(
            bucket,
            test_file,
            data_stream,
            length=len(test_content),
            content_type="text/plain"
        )
        print(f"   [OK] Uploaded '{test_file}' to bucket '{bucket}'")
        
        # Read it back to verify
        response = client.get_object(bucket, test_file)
        retrieved_content = response.read()
        response.close()
        response.release_conn()
        
        if retrieved_content == test_content:
            print("   [OK] Retrieve content match verification: SUCCESS")
        else:
            print("   [FAILED] Retrieved content mismatch!")
            
    except Exception as e:
        print(f"   [FAILED] MinIO operations failed: {e}")
        
if __name__ == "__main__":
    test_connections()
