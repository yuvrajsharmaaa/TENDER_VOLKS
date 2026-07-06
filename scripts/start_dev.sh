#!/bin/bash
# start_dev.sh - Starts local Docker Compose development environment for Day 2

set -e

# Locate project directories
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "=========================================================="
echo "Starting VolksEnergies Tender OCR Stack (Day 2 Dev)"
echo "=========================================================="

# Ensure environment file is available
if [ ! -f "$PROJECT_ROOT/.env.dev" ]; then
    echo "Notice: .env.dev not found. Copying .env.example..."
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env.dev"
fi

# Spin up compose stack
echo "Running docker compose up..."
cd "$PROJECT_ROOT/infra"
docker compose -f docker-compose.dev.yml up -d --build

echo ""
echo "=========================================================="
echo "Dev services are spinning up in the background:"
echo " - PostgreSQL:      localhost:5432"
echo " - Redis:           localhost:6379"
echo " - MinIO API:       localhost:9000"
echo " - MinIO Console:   http://localhost:9001  (Access: minioadmin / minioadmin)"
echo " - Backend API:     http://localhost:8000"
echo " - API Docs:        http://localhost:8000/docs"
echo " - Health Route:    http://localhost:8000/health"
echo "=========================================================="
echo "Tailing backend container logs... (Ctrl+C to stop tailing)"
echo ""

docker compose -f docker-compose.dev.yml logs -f backend
