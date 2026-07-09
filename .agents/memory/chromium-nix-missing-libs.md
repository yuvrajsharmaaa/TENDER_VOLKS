---
name: Headless Chromium in Nix environment
description: Playwright headless Chromium fails at launch due to missing system shared library in this Nix env.
---

## Rule
Do not attempt Playwright / headless-Chromium E2E testing in this Replit environment. Use curl-based E2E verification against the running dev server instead.

**Why:** `libglib-2.0.so.0` (and likely other glib/nss shared libs) are not present in the Nix shell PATH that the Chromium binary expects. Chromium fails to launch immediately regardless of which browser channel is installed. Chasing the dependency chain is not worth it for an MVP — the library graph is deep and Replit's Nix environment does not expose the full system lib path Chromium needs.

**How to apply:** For browser-level contract verification, use `curl` through the Vite dev proxy (port 5000) to confirm API forwarding, and take a static screenshot with the agent screenshot tool to confirm the page renders. Reserve full interactive E2E for a CI environment with a proper Linux image.
