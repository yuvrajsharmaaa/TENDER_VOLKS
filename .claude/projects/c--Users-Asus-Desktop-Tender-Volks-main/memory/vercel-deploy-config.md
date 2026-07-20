---
name: vercel-deploy-config
description: Added Vercel deployment configuration for FastAPI backend
metadata:
  type: project
---

Added Vercel deployment configuration to enable deployment of the FastAPI backend on Vercel platform.

Changes made:
1. Created pyproject.toml with project metadata and Vercel configuration specifying entrypoint as "backend.app.main:app"
2. Created vercel.json with routing configuration to direct all API routes to the FastAPI application

The configuration allows the FastAPI application in backend/app/main.py to be deployed on Vercel serverless functions.

Related to: Tender OCR backend deployment
---