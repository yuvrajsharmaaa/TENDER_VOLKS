---
name: Verify the app actually boots before trusting architecture docs
description: Lesson — the described/documented architecture may be incomplete or broken; always confirm boot first.
---

## Rule
Before trusting any existing documentation, README, or inline comments about how the project works, run the app and confirm it boots without errors. Only then read the architecture docs as authoritative.

**Why:** This project's `backend/app/models/` package was described in comments and imports throughout the codebase but did not exist in git history at all — the app could not even import, let alone boot. Spending time understanding the "architecture" before discovering this would have been wasted. A failed boot is the fastest signal that the foundation needs to be built before anything else.

**How to apply:** First action when inheriting an unfamiliar project: start the server, check logs, confirm it reaches "Application startup complete." before doing any other investigation.
