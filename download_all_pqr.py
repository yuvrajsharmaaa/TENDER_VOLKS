import os
import sys
import json
import time
import asyncio
import pandas as pd
import httpx
from pathlib import Path

BASE_URL = "https://tmsv2.volksenergie.in/api/v1"
EXCEL_PATH = r"C:\Users\Asus\Desktop\Tender_Volks\main\pqr_documents_cleaned.xlsx"
OUTPUT_DIR = r"C:\Users\Asus\Desktop\Tender_Volks\main\pqr_matched_files"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6OTQsInN1YiI6OTQsImVtYWlsIjoieXV2cmFqc2hhcm1hYTIwMjJAZ21haWwuY29tIiwicm9sZSI6IlN1cGVyIFVzZXIiLCJyb2xlSWQiOjEsInRlYW1JZCI6IjIiLCJkYXRhU2NvcGUiOiJhbGwiLCJjYW5Td2l0Y2hUZWFtcyI6dHJ1ZSwicGVybWlzc2lvbnMiOlsiaW5mby1zaGVldHM6dXBkYXRlIl0sImlhdCI6MTc4Nzg0OTY5NywiZXhwIjoxNzg4NDU0NDk3fQ.hItuaZF5Ulk3g_ZShEUzU7a9AF-7hoNcdXc6dlkm04Y"

DOC_COLUMNS = [
    "po_document",
    "sap_gem_po_document",
    "completion_document",
    "performance_certificate"
]

def parse_file_entries(raw_val):
    if pd.isna(raw_val) or raw_val is None:
        return []
    val_str = str(raw_val).strip()
    if not val_str or val_str.lower() in ["nan", "none", "[]"]:
        return []
    if val_str.startswith("[") and val_str.endswith("]"):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass
    if "," in val_str:
        return [part.strip().strip("'\"") for part in val_str.split(",") if part.strip()]
    return [val_str.strip("'\"")]

async def download_file(sem, client, ref, index, total):
    target_url = f"{BASE_URL}/files/serve/{ref}"
    dest_path = os.path.join(OUTPUT_DIR, ref.replace("/", os.sep))
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        size_kb = os.path.getsize(dest_path) / 1024
        print(f"[{index}/{total}] Already cached: {ref} ({size_kb:.1f} KB)", flush=True)
        return {"ref": ref, "status": "cached", "size": os.path.getsize(dest_path)}

    async with sem:
        for attempt in range(3):
            try:
                r = await client.get(target_url)
                if r.status_code == 200 and len(r.content) > 0:
                    with open(dest_path, "wb") as f:
                        f.write(r.content)
                    size_kb = len(r.content) / 1024
                    print(f"[{index}/{total}] SUCCESS: {ref} ({size_kb:.1f} KB)", flush=True)
                    return {"ref": ref, "status": "success", "size": len(r.content)}
                elif r.status_code == 404:
                    print(f"[{index}/{total}] NOT FOUND (404): {ref}", flush=True)
                    return {"ref": ref, "status": "not_found", "code": 404}
                elif r.status_code == 401:
                    print(f"[{index}/{total}] UNAUTHORIZED (401): {ref}", flush=True)
                    return {"ref": ref, "status": "unauthorized", "code": 401}
                else:
                    print(f"[{index}/{total}] HTTP {r.status_code} (attempt {attempt+1}): {ref}", flush=True)
                    await asyncio.sleep(1.0)
            except Exception as e:
                if attempt == 2:
                    print(f"[{index}/{total}] ERROR on {ref}: {e}", flush=True)
                    return {"ref": ref, "status": "error", "error": str(e)}
                await asyncio.sleep(1.5)

    return {"ref": ref, "status": "failed"}

async def main_async():
    start_time = time.time()
    print("=" * 70)
    print(" BATCH DOWNLOADING ALL PQR DOCUMENTS FROM TMS SERVER")
    print("=" * 70)
    print(f"Target Excel:     {EXCEL_PATH}")
    print(f"Output Directory: {OUTPUT_DIR}\n")

    df = pd.read_excel(EXCEL_PATH)
    all_refs = []
    for _, row in df.iterrows():
        for col in DOC_COLUMNS:
            if col in df.columns:
                for ref in parse_file_entries(row[col]):
                    all_refs.append(ref.replace("\\", "/").strip())

    unique_refs = sorted(list(set(all_refs)))
    print(f"Loaded {len(unique_refs)} unique files referenced in Excel.")

    sem = asyncio.Semaphore(8)
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Cookie": f"access_token={TOKEN}; sidebar_state=false",
        "User-Agent": "TenderVolks-Downloader/1.0"
    }

    async with httpx.AsyncClient(timeout=45.0, headers=headers, follow_redirects=True) as client:
        tasks = [
            download_file(sem, client, ref, i + 1, len(unique_refs))
            for i, ref in enumerate(unique_refs)
        ]
        results = await asyncio.gather(*tasks)

    # Analyze results
    success_count = sum(1 for r in results if r["status"] in ["success", "cached"])
    cached_count = sum(1 for r in results if r["status"] == "cached")
    new_download_count = sum(1 for r in results if r["status"] == "success")
    not_found_count = sum(1 for r in results if r["status"] == "not_found")
    error_count = sum(1 for r in results if r["status"] in ["error", "failed", "unauthorized"])
    total_bytes = sum(r.get("size", 0) for r in results if "size" in r)
    total_mb = total_bytes / (1024 * 1024)
    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print(" DOWNLOAD SUMMARY REPORT")
    print("=" * 70)
    print(f"Total files referenced in Excel: {len(unique_refs)}")
    print(f"Successfully retrieved:          {success_count} ({new_download_count} new, {cached_count} cached)")
    print(f"Not Found on server (404):       {not_found_count}")
    print(f"Errors / Failed:                 {error_count}")
    print(f"Total data volume:               {total_mb:.2f} MB")
    print(f"Time taken:                      {elapsed:.2f} seconds")
    print("=" * 70)

    if not_found_count > 0:
        print("\nFiles marked 404 (uploaded path referenced in DB, but missing from server disk):")
        nf_list = [r["ref"] for r in results if r["status"] == "not_found"]
        for item in nf_list[:15]:
            print(f"  - {item}")
        if len(nf_list) > 15:
            print(f"  ... and {len(nf_list) - 15} more.")

if __name__ == "__main__":
    asyncio.run(main_async())
