# Universal Tender Processor — PowerShell Self-Test Guide

This guide details how to verify the automated page-aware tender document extraction, database mapping, and CSV exporting pipeline locally on Windows using PowerShell commands.

---

## 1. Prerequisites & Storage Cleanup

Before starting a clean test run, you can optionally clean up old files and database logs:

```powershell
# 1. Clean up generated local jobs files
Remove-Item -Path "C:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\*" -Recurse -Force -ErrorAction SilentlyContinue

# 2. Reset local SQLite job logs
sqlite3.exe "C:\Users\Asus\Desktop\Tender_Volks\main\backend\app\data\tender.db" "DELETE FROM jobs;"

# 3. Truncate PostgreSQL tender information records
psql -U postgres -d tender_db -c "TRUNCATE TABLE tender_information CASCADE;"
```

---

## 2. Infrastructure Checks

Verify that the local containers and the FastAPI backend are up and listening:

```powershell
# Verify Docker containers are running (Postgres, MinIO, MailHog)
docker ps

# Verify backend health check
curl.exe http://localhost:8000/health
```

**Expected Health Output:**
`{"status":"success","redis":"ping_ok","postgres":"connected"}`

---

## 3. Step-by-Step PowerShell API Verification

### Step 1: Upload a Raw Tender PDF
Choose a target PDF (e.g. `C:\Users\Asus\Desktop\Tender_Volks\main\storage\jobs\5.pdf`) and upload it to get a `job_id`.

**PowerShell Command:**
```powershell
$res = curl.exe -X POST -F "file=@C:\Users\Asus\Desktop\Tender_Volks\main\storage\jobs\5.pdf" http://localhost:8000/tenders/upload | ConvertFrom-Json
$jobId = $res.job_id
$res
```

**Expected Response:**
```json
{
  "job_id": "f03ff3ba-4064-454a-8c08-d844b7efd437",
  "status": "pending",
  "message": "Upload complete. Trigger processing via POST /tenders/process."
}
```

---

### Step 2: Trigger Page-Aware Processing
To prevent JSON quote-stripping issues in PowerShell, write the body payload to a temporary JSON file and post it using the `@` reference.

**PowerShell Command:**
```powershell
# 1. Define recipient and payload
$body = @{
  job_id = $jobId
  email_recipient = "yuvrajsharmaa2022@gmail.com"
  tender_id = 99
} | ConvertTo-Json

# 2. Save body payload to temp file
$body | Out-File -FilePath temp_body.json -Encoding utf8

# 3. POST process trigger
curl.exe -X POST "http://localhost:8000/tenders/process" -H "Content-Type: application/json" -d "@temp_body.json"

# 4. Remove temp body file
Remove-Item -Path temp_body.json
```

**Expected Response:**
```json
{
  "job_id": "f03ff3ba-4064-454a-8c08-d844b7efd437",
  "status": "processing"
}
```

---

### Step 3: Poll Job Status
Check the status of the job until the task completes:

**PowerShell Command:**
```powershell
curl.exe http://localhost:8000/jobs/$jobId
```

*   **While processing:** `"status": "processing"`
*   **Finished:** `"status": "completed"`

---

### Step 4: Download CSV Reports
After a `"completed"` status, download the generated CSV files:

**Summary Sheet (Layer 1):**
```powershell
curl.exe -o summary_report.csv "http://localhost:8000/jobs/$jobId/download?format=summary"
```

**Evidence Log (Layer 2):**
```powershell
curl.exe -o evidence_log.csv "http://localhost:8000/jobs/$jobId/download?format=evidence"
```

---

## 4. Verification Checkpoints

### 1. Database Table
Verify PostgreSQL records are populated correctly:
```powershell
psql -U postgres -d tender_db -c "SELECT tender_value, emd_required, emd_amount, source_page_evidence_summary FROM tender_information WHERE tender_id = 99;"
```

### 2. Local Files
Confirm reports are written to the workspace storage:
```powershell
Get-ChildItem -Path "C:\Users\Asus\Desktop\Tender_Volks\main\backend\app\storage\jobs\$jobId"
```

### 3. Email Alerts
1. Open MailHog Web Portal at `http://localhost:8025/`.
2. Verify that an email was sent to `yuvrajsharmaa2022@gmail.com` with subjects: *"Processed Tender results for ID: 99"*.
3. Verify both `tender_99_export.csv` and `tender_99_evidence.csv` are attached.
