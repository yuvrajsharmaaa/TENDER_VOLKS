#!/bin/bash
# reset_dev_db.sh - Wipes and restarts compose services along with database/storage volumes

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "=========================================================="
echo "Wiping volumes and resetting local development environment"
echo "=========================================================="

cd "$PROJECT_ROOT/infra"

echo "Stopping containers and destroying persistent volumes..."
docker compose -f docker-compose.dev.yml down -v

echo "Rebuilding and starting services from clean slate..."
docker compose -f docker-compose.dev.yml up -d --build

echo "=========================================================="
echo "Reset completed! Services have restarted with empty volumes."
echo "=========================================================="
