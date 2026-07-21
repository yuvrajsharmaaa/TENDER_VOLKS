---
name: tender-volks-vercel-config
description: Configured Vercel deployment configuration for Tender Volks backend
metadata:
  type: project
---

Added pyproject.toml with project dependencies and Vercel configuration pointing to backend.app.main:app as the entrypoint.

Created vercel.json with proper routing configuration for Vercel serverless deployment, setting the build to use @vercel/python with Python 3.9 runtime and routing all requests to the backend app.

The configuration ensures Vercel will properly recognize and deploy the FastAPI application from backend/app/main.py.