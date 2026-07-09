---
name: LocalObjectStore path traversal guard
description: How and why object keys must be validated before filesystem ops in the disk-backed object store shim.
---

## Rule
Every method in `LocalObjectStore` that constructs a filesystem path from a caller-supplied object key **must** call `_safe_object_path()` rather than raw path concatenation (`bucket_dir / object_name`). The helper resolves both paths and calls `relative_to()` — raising `ValueError` if the resolved candidate escapes the bucket root.

**Why:** Object keys are derived from caller-controlled values (tender/project IDs, uploaded filenames). Without this check, a crafted key containing `..` segments or an absolute path can escape the storage root and read, write, or delete arbitrary files accessible to the process. This is a blocking security issue, not a style concern.

**How to apply:** Any new method added to `LocalObjectStore` that does filesystem I/O on an object key must go through `_safe_object_path(bucket_name, object_name)` first. The method is in `backend/app/core/minio.py`.
