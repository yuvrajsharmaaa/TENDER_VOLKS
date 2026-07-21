import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('backend/app/storage/jobs/35580348-246b-49f7-86a0-175c1bfd64ca/tender_detail.json', encoding='utf-8', errors='replace') as f:
    td = json.load(f)

print('=== OLD (pre-fix, job 35580348, InfoSheet generated 2026-07-16 16:56:44) ===')
print()
print('Top-level resolved fields:')
for k in ['title', 'authorityName', 'deadline', 'tenderValue', 'emdAmount', 'tenderFee', 'location']:
    print(f"  {k}: {repr(td.get(k))}")

print()
print('InfoSheet sections (fields):')
for sec in td.get('infoSheetSections', []):
    print(f"  --- {sec.get('title')} ---")
    for field in sec.get('fields', []):
        label = field.get('label', '')
        val = field.get('value', '')
        status = field.get('status', '')
        if val and val != 'NA':
            print(f"    {label}: {repr(val)} (status={status})")
        else:
            print(f"    {label}: NA")
