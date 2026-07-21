from backend.app.repositories.job_store import get_all_jobs
jobs = get_all_jobs()
print("ALL JOBS:")
for j in jobs:
    print(f"Job ID: {j['job_id']} | Status: {j['status']} | Filename: {j['original_filename']} | Created: {j['created_at']} | Started: {j['started_at']} | Completed: {j['completed_at']} | Error: {j['error_message']}")
