# VolksEnergies Tender OCR

A FastAPI + React application for uploading Indian GeM tender PDFs, running Tesseract OCR, and extracting structured tender fields (dates, amounts, organization info, products/items, etc.).

## Workflows

- **Backend API** — `cd /home/runner/workspace && PYTHONPATH=/home/runner/workspace .pythonlibs/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload`
- **Frontend** — `cd /home/runner/workspace/frontend && npm run dev` (serves on port 5000)

## Useful commands

- `cd frontend && npm run build` — TypeScript + Vite production build
- `PYTHONPATH=/home/runner/workspace .pythonlibs/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload` — run backend manually

## User preferences

*(None recorded yet.)*
