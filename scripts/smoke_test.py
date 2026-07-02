import httpx
import time
import sys

def run_smoke_test():
    url = "http://localhost:8000"
    
    # 1. Upload
    print("Uploading sample_digital.pdf...")
    with open("tests/fixtures/sample_digital.pdf", "rb") as f:
        files = {"file": ("sample_digital.pdf", f, "application/pdf")}
        res = httpx.post(f"{url}/upload", files=files, timeout=10.0)
        
    if res.status_code != 201:
        print(f"Upload failed: {res.status_code} - {res.text}")
        sys.exit(1)
        
    data = res.json()
    job_id = data["job_id"]
    print(f"Job created successfully: {job_id}")
    
    # 2. Poll status
    print("Polling job status...")
    for _ in range(30):
        res = httpx.get(f"{url}/job/{job_id}/status")
        if res.status_code != 200:
            print(f"Status check failed: {res.status_code} - {res.text}")
            sys.exit(1)
        job = res.json()
        status = job["status"]
        print(f"Current status: {status}")
        if status == "completed":
            print("Job completed successfully!")
            break
        elif status == "failed":
            print(f"Job failed: {job.get('error_message')}")
            sys.exit(1)
        time.sleep(2)
    else:
        print("Job timed out")
        sys.exit(1)
        
    # 3. Get results
    print("Fetching results...")
    res = httpx.get(f"{url}/job/{job_id}/result")
    if res.status_code != 200:
        print(f"Result fetch failed: {res.status_code} - {res.text}")
        sys.exit(1)
    
    result_data = res.json()
    print("Smoke test passed! Result preview:")
    import json
    print(json.dumps(result_data, indent=2))

if __name__ == "__main__":
    run_smoke_test()
