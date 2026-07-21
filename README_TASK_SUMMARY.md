All tasks have been completed:
1. Fixed the type error in tenders.py by using str(col) when setting attributes on db_info.
2. Updated the TenderInformation model to include all columns from CSV_COLUMNS (including tender_name, tender_fee, estimated_cost, etc.) while retaining existing columns for backward compatibility.
3. The CSV export now uses the model attributes directly via getattr, which match the CSV_COLUMNS list.

The system should now correctly export tender information to CSV without type errors.