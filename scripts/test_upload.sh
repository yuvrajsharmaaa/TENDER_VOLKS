#!/bin/bash
# Day 3 manual test — run from project root
# Usage: bash scripts/test_upload.sh path/to/sample.pdf

PDF_FILE=${1:-"sample.pdf"}
BASE_URL=${2:-"http://localhost:8000"}

echo "=== Test 1: Valid PDF upload ==="
curl -s -X POST \
  -F "file=@${PDF_FILE};type=application/pdf" \
  "${BASE_URL}/tenders/upload" | python3 -m json.tool

echo ""
echo "=== Test 2: Missing file (expect 400) ==="
curl -s -X POST \
  "${BASE_URL}/tenders/upload" | python3 -m json.tool

echo ""
echo "=== Test 3: Wrong content type (expect 400) ==="
curl -s -X POST \
  -F "file=@${PDF_FILE};type=text/plain" \
  "${BASE_URL}/tenders/upload" | python3 -m json.tool

echo ""
echo "=== Test 4: Health check still works ==="
curl -s "${BASE_URL}/health" | python3 -m json.tool
