import os
import re
import json
import pandas as pd
from collections import defaultdict, Counter

def main():
    docs_dir = 'tender-documents'
    excel_dir = os.path.join(docs_dir, 'excel')
    
    # 1. Inspect directory structure and files
    all_entries = os.listdir(docs_dir)
    subdirs = [e for e in all_entries if os.path.isdir(os.path.join(docs_dir, e))]
    files = sorted([e for e in all_entries if os.path.isfile(os.path.join(docs_dir, e))])
    
    print(f"Total entries in {docs_dir}: {len(all_entries)}")
    print(f"Subdirectories ({len(subdirs)}): {subdirs}")
    print(f"Direct files count: {len(files)}")
    
    # 2. Load Step 1 Reference Table from outcome_labels_review.xlsx
    ref_excel = 'outcome_labels_review.xlsx'
    xl = pd.ExcelFile(ref_excel)
    clean_df = xl.parse('Clean Consolidated')
    conflicts_df = xl.parse('Conflicts - NEEDS DECISION')
    
    ambiguous_tender_nos = set(conflicts_df['tender_no'].dropna().astype(str).str.strip().unique())
    print(f"Clean Consolidated rows: {len(clean_df)}")
    print(f"Ambiguous tender_nos count (from Conflicts): {len(ambiguous_tender_nos)}")
    
    # Map reference tenders and their associated files
    known_tenders = {}
    known_file_to_tender = {}
    
    # Process Clean Consolidated (unambiguous)
    for _, r in clean_df.iterrows():
        t_no = str(r['tender_no']).strip()
        outcome = str(r['outcome']).strip()
        t_name = str(r.get('tender_name', '')).strip()
        docs_raw = str(r.get('documents', ''))
        
        doc_files = []
        if docs_raw and docs_raw != 'nan':
            try:
                doc_list = json.loads(docs_raw) if docs_raw.startswith('[') else [docs_raw]
                for d in doc_list:
                    fname = os.path.basename(str(d))
                    doc_files.append(fname)
                    known_file_to_tender[fname] = t_no
            except Exception:
                pass
                
        # Format status
        raw_out = outcome.lower()
        if raw_out == 'won':
            status = 'Won'
        elif raw_out == 'lost':
            status = 'Lost'
        elif raw_out in ('do_not_bid', 'do not bid'):
            status = 'Do Not Bid'
        else:
            status = 'Unclassified'
            
        known_tenders[t_no] = {
            'tender_no': t_no,
            'tender_name': t_name,
            'status': status,
            'source_files': doc_files
        }
        
    # Process Conflicts sheet (ambiguous)
    for t_no in ambiguous_tender_nos:
        rows = conflicts_df[conflicts_df['tender_no'] == t_no]
        combined_docs = []
        names = []
        for _, r in rows.iterrows():
            t_name = str(r.get('tender_name', '')).strip()
            if t_name and t_name not in names:
                names.append(t_name)
            docs_raw = str(r.get('documents', ''))
            if docs_raw and docs_raw != 'nan':
                try:
                    doc_list = json.loads(docs_raw) if docs_raw.startswith('[') else [docs_raw]
                    for d in doc_list:
                        fname = os.path.basename(str(d))
                        if fname not in combined_docs:
                            combined_docs.append(fname)
                        known_file_to_tender[fname] = t_no
                except Exception:
                    pass
        
        known_tenders[t_no] = {
            'tender_no': t_no,
            'tender_name': " / ".join(names) if names else "Ambiguous Tender",
            'status': 'Needs Manual Review (ambiguous tender_no)',
            'source_files': combined_docs
        }
        
    print(f"Total reference tenders (Clean + Conflicts): {len(known_tenders)}")
    print(f"Files mapped to reference tenders: {len(known_file_to_tender)}")
    
    # 3. Analyze unmapped files in tender-documents
    unmapped_files = [f for f in files if f not in known_file_to_tender]
    print(f"Unmapped files in directory: {len(unmapped_files)}")
    
    gem_bids = defaultdict(list)
    cppp_tenders = defaultdict(list)
    ms_ts_groups = defaultdict(list)
    sec_ts_groups = defaultdict(list)
    pure_ts_groups = defaultdict(list)
    unmatched_files_list = []
    
    for f in unmapped_files:
        m_gem = re.search(r'GeM-Bidding-(?:Corr-)?(\d+)', f, re.I)
        m_cppp = re.search(r'(\d{4}_[A-Z0-9]+_\d+(_\d+)?)', f)
        m_ms = re.match(r'^(\d{13})_', f)
        m_sec = re.search(r'_(\d{10})_\d+\.', f)
        m_pure = re.match(r'^(\d{10})\.', f)
        
        if m_gem:
            gem_bids[f"GEM/BID/{m_gem.group(1)}"].append(f)
        elif m_cppp:
            cppp_tenders[m_cppp.group(1)].append(f)
        elif m_ms:
            ts_bucket = int(m_ms.group(1)) // 5000
            ms_ts_groups[f"TS_BATCH_MS_{ts_bucket}"].append(f)
        elif m_sec:
            sec_ts_groups[f"TS_BATCH_SEC_{m_sec.group(1)}"].append(f)
        elif m_pure:
            pure_ts_groups[f"TS_DOC_{m_pure.group(1)}"].append(f)
        else:
            unmatched_files_list.append(f)
            
    print(f"\nUnmapped groupings breakdown:")
    print(f"  GeM Bids: {len(gem_bids)} groups ({sum(len(v) for v in gem_bids.values())} files)")
    print(f"  CPPP Tenders: {len(cppp_tenders)} groups ({sum(len(v) for v in cppp_tenders.values())} files)")
    print(f"  MS Timestamp batches: {len(ms_ts_groups)} groups ({sum(len(v) for v in ms_ts_groups.values())} files)")
    print(f"  Sec Timestamp batches: {len(sec_ts_groups)} groups ({sum(len(v) for v in sec_ts_groups.values())} files)")
    print(f"  Single Doc Timestamps: {len(pure_ts_groups)} groups ({sum(len(v) for v in pure_ts_groups.values())} files)")
    print(f"  Unmatched files: {len(unmatched_files_list)} files")
    
    # 4. Build Master Tender List
    master_rows = []
    
    # Add known tenders (Won / Lost / Do Not Bid / Needs Manual Review)
    for t_no, data in known_tenders.items():
        doc_count = len(data['source_files'])
        doc_str = json.dumps(data['source_files']) if doc_count > 0 else ""
        master_rows.append({
            'tender_no': t_no,
            'tender_name': data['tender_name'],
            'source_files': doc_str,
            'source_files_count': doc_count,
            'folder_path': 'tender-documents',
            'status': data['status']
        })
        
    # Add unmapped tender groups (Unclassified)
    for group_dict, prefix_label in [
        (gem_bids, 'GeM Bid'),
        (cppp_tenders, 'CPPP'),
        (ms_ts_groups, 'Timestamp Batch (ms)'),
        (sec_ts_groups, 'Timestamp Batch (sec)'),
        (pure_ts_groups, 'Single Doc Timestamp')
    ]:
        for group_id, group_files in group_dict.items():
            master_rows.append({
                'tender_no': group_id,
                'tender_name': f"Unclassified {prefix_label} ({len(group_files)} files)",
                'source_files': json.dumps(group_files),
                'source_files_count': len(group_files),
                'folder_path': 'tender-documents',
                'status': 'Unclassified'
            })
            
    # Add any individual unmatched files as Unclassified
    for f in unmatched_files_list:
        master_rows.append({
            'tender_no': f"FILE_{os.path.splitext(f)[0]}",
            'tender_name': f"Unclassified Document: {f}",
            'source_files': json.dumps([f]),
            'source_files_count': 1,
            'folder_path': 'tender-documents',
            'status': 'Unclassified'
        })
        
    master_df = pd.DataFrame(master_rows)
    print(f"\nTotal Master Tender Records: {len(master_df)}")
    
    # Save master-tenders.csv
    csv_out = master_df[['tender_no', 'source_files', 'folder_path']]
    csv_out.to_csv('master-tenders.csv', index=False)
    print("Saved master-tenders.csv successfully.")
    
    # 5. Build classified-tenders.xlsx
    all_tenders_sheet = master_df[['tender_no', 'tender_name', 'folder_path', 'source_files_count', 'source_files', 'status']]
    
    # Summary Table
    status_order = ['Won', 'Lost', 'Do Not Bid', 'Needs Manual Review (ambiguous tender_no)', 'Unclassified']
    status_counts = master_df['status'].value_counts()
    
    summary_rows = []
    for s in status_order:
        cnt = status_counts.get(s, 0)
        summary_rows.append({
            'Status': s,
            'Count': cnt,
            'Percentage': f"{(cnt / len(master_df) * 100):.2f}%"
        })
    summary_df = pd.DataFrame(summary_rows)
    
    # Unclassified Sheet
    unclassified_sheet = master_df[master_df['status'] == 'Unclassified'][['tender_no', 'tender_name', 'source_files_count', 'source_files', 'folder_path']]
    
    # Needs Manual Review Sheet
    manual_review_sheet = master_df[master_df['status'] == 'Needs Manual Review (ambiguous tender_no)'][['tender_no', 'tender_name', 'source_files_count', 'source_files', 'folder_path']]
    
    # Unmatched Filenames Sheet
    unmatched_df = pd.DataFrame({
        'filename': unmatched_files_list,
        'extension': [os.path.splitext(f)[1] for f in unmatched_files_list],
        'folder_path': 'tender-documents'
    })
    
    xlsx_out = 'classified-tenders.xlsx'
    with pd.ExcelWriter(xlsx_out, engine='openpyxl') as writer:
        all_tenders_sheet.to_excel(writer, sheet_name='All Tenders', index=False)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        unclassified_sheet.to_excel(writer, sheet_name='Unclassified', index=False)
        manual_review_sheet.to_excel(writer, sheet_name='Needs Manual Review', index=False)
        unmatched_df.to_excel(writer, sheet_name='Unmatched Filenames', index=False)
        
    print(f"Saved {xlsx_out} successfully.")
    
    # Print summary
    print("\n=== FINAL CLASSIFICATION SUMMARY ===")
    print(summary_df.to_string(index=False))

if __name__ == '__main__':
    main()
