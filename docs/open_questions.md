# Open Architecture Questions

This document tracks unresolved decisions and design parameters.

---

## 1. TMS Integration Model: Push-Based vs. Pull-Based
- **Push-Based:** The extraction engine (`TENDER_VOLKS`) directly hits a callback URL on the TMS backend when a document finishes processing, pushing the final structured payload.
  - *Pros:* Near real-time sync, lightweight polling overhead.
  - *Cons:* Requires the extraction service to know TMS endpoint routes and manage network retries/failure recovery.
- **Pull-Based:** The TMS backend polls the `TENDER_VOLKS` status endpoints (e.g. `/job/{id}/status`) periodically until status transitions to `completed`, then fetches results via `/job/{id}/extracted-fields`.
  - *Pros:* Simplifies the extraction service interface, keeps concerns isolated.
  - *Cons:* Adds database query overhead on TMS during high-concurrency periods.
- *Current Status:* Standardized on the pull-based REST polling API for the initial MVP release.

---

## 2. Real-Time Ingestion SLAs and Processing Latency
- Should the system support a synchronous extraction route for small single-page documents?
- *Current Status:* All documents default to asynchronous queueing to avoid locking API gateways during long PDF rasterization phases. A fast-path queue could be configured for documents under 2 MB.

---

## 3. LLM API Cost and Usage Ceilings
- How do we calculate and enforce usage caps for the enterprise LLM API fallback layer?
- Should low-confidence fields default to "Not Found" if LLM usage limits have been exhausted for the current billing cycle?
- *Current Status:* Set a static toggle in config to disable LLM fallbacks entirely, defaulting to regex/NER outputs.
