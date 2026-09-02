import os
import sys
import json
import getpass
import pandas as pd
import httpx
from pathlib import Path

BASE_URL = "https://tmsv2.volksenergie.in/api/v1"
EXCEL_PATH = r"C:\Users\Asus\Desktop\Tender_Volks\main\pqr_documents_cleaned.xlsx"
OUTPUT_DIR = r"C:\Users\Asus\Desktop\Tender_Volks\main\pqr_matched_files"

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

def get_auth_client(token: str = None, email: str = None, password: str = None):
    client = httpx.Client(timeout=30.0, follow_redirects=True)
    
    if token:
        client.cookies.set("access_token", token)
        # Also set Bearer header just in case
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    if email and password:
        print(f"Logging in to {BASE_URL} as {email}...")
        resp = client.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            print(f"Login failed ({resp.status_code}): {resp.text}")
            return None
        print("Login successful! Session established.")
        return client

    return None

def main():
    print("=" * 65)
    print(" TMS PQR DOCUMENT DOWNLOADER")
    print("=" * 65)
    print(f"Target Excel: {EXCEL_PATH}")
    print(f"Output Directory: {OUTPUT_DIR}\n")

    if not os.path.exists(EXCEL_PATH):
        print(f"ERROR: Excel file not found at {EXCEL_PATH}")
        sys.exit(1)

    df = pd.read_excel(EXCEL_PATH)
    all_refs = []
    for _, row in df.iterrows():
        for col in DOC_COLUMNS:
            if col in df.columns:
                for ref in parse_file_entries(row[col]):
                    all_refs.append(ref.replace("\\", "/").strip())

    unique_refs = sorted(list(set(all_refs)))
    print(f"Loaded {len(unique_refs)} unique PQR files to download.\n")

    # Check for token or prompt login
    token = os.getenv("TMS_ACCESS_TOKEN")
    client = None

    if token:
        client = get_auth_client(token=token)
    else:
        print("Choose authentication method:")
        print(" 1) Enter access_token cookie (from browser DevTools)")
        print(" 2) Login with TMS Email and Password")
        choice = input("Select [1 or 2]: ").strip()

        if choice == "1":
            token = input("Paste 'access_token' value: ").strip()
            client = get_auth_client(token=token)
        else:
            email = input("TMS Email: ").strip()
            password = getpass.getpass("TMS Password: ").strip()
            client = get_auth_client(email=email, password=password)

    if not client:
        print("ERROR: Authentication could not be completed.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    success_count = 0
    fail_count = 0
    failed_items = []

    print(f"\nStarting download of {len(unique_refs)} files...")

    for i, ref in enumerate(unique_refs, 1):
        target_url = f"{BASE_URL}/files/serve/{ref}"
        dest_path = os.path.join(OUTPUT_DIR, ref.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            print(f"[{i}/{len(unique_refs)}] Already exists: {ref}")
            success_count += 1
            continue

        try:
            r = client.get(target_url)
            if r.status_code == 200:
                with open(dest_path, "wb") as f:
                    f.write(r.content)
                size_kb = len(r.content) / 1024
                print(f"[{i}/{len(unique_refs)}] Downloaded: {ref} ({size_kb:.1f} KB)")
                success_count += 1
            else:
                print(f"[{i}/{len(unique_refs)}] FAILED ({r.status_code}): {ref}")
                fail_count += 1
                failed_items.append((ref, r.status_code))
        except Exception as e:
            print(f"[{i}/{len(unique_refs)}] ERROR: {ref} -> {e}")
            fail_count += 1
            failed_items.append((ref, str(e)))

    print("\n" + "=" * 65)
    print("DOWNLOAD COMPLETE")
    print("=" * 65)
    print(f"Successfully downloaded: {success_count} / {len(unique_refs)}")
    print(f"Failed:                  {fail_count} / {len(unique_refs)}")
    if fail_count > 0:
        print("\nFailed files sample:")
        for item in failed_items[:10]:
            print(f"  - {item[0]}: {item[1]}")

if __name__ == "__main__":
    main()
