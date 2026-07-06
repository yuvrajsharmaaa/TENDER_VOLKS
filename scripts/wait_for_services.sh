#!/bin/bash
# wait_for_services.sh - Loops and waits until PostgreSQL, Redis, and MinIO are healthy

TIMEOUT=60
COUNTER=0

echo "=========================================================="
echo "Waiting for PostgreSQL, Redis, and MinIO to be online..."
echo "=========================================================="

while [ $COUNTER -lt $TIMEOUT ]; do
    # Check Postgres (5432)
    PG_UP=0
    if (exec 3<>/dev/tcp/localhost/5432) 2>/dev/null; then
        PG_UP=1
        exec 3>&-
    fi

    # Check Redis (6379)
    REDIS_UP=0
    if (exec 3<>/dev/tcp/localhost/6379) 2>/dev/null; then
        REDIS_UP=1
        exec 3>&-
    fi

    # Check MinIO (9000)
    MINIO_UP=0
    MINIO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:9000/minio/health/live || echo "DOWN")
    if [ "$MINIO_STATUS" = "200" ]; then
        MINIO_UP=1
    fi

    if [ $PG_UP -eq 1 ] && [ $REDIS_UP -eq 1 ] && [ $MINIO_UP -eq 1 ]; then
        echo -e "\n[\033[0;32mSUCCESS\033[0m] All services are fully healthy and ready to accept traffic!"
        exit 0
    fi

    echo -n "."
    sleep 2
    let COUNTER=COUNTER+2
done

echo -e "\n[\033[0;31mTIMEOUT\033[0m] Reached limit ($TIMEOUT sec) waiting for dependencies."
echo "Last status: PostgreSQL=$PG_UP, Redis=$REDIS_UP, MinIO=$MINIO_UP"
exit 1
