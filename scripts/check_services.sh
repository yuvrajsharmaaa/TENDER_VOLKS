#!/bin/bash
# check_services.sh - Probes service ports from the host machine to diagnose availability

echo "=========================================================="
echo "Diagnosing VolksEnergies Tender OCR Services (Day 2)"
echo "=========================================================="

# Helper function to check TCP socket connection
check_port() {
    local host=$1
    local port=$2
    local service_name=$3
    
    # Try using bash socket connection if available, otherwise fallback to curl
    if (exec 3<>/dev/tcp/$host/$port) 2>/dev/null; then
        echo -e "[\033[0;32mONLINE\033[0m] $service_name is listening on port $port"
        exec 3>&-
        return 0
    else
        # Try checking with curl connection test (exit code 52 is empty reply from server, which means port is open)
        local curl_test
        curl_test=$(curl -s --connect-timeout 2 http://$host:$port 2>&1)
        local status=$?
        if [ $status -eq 0 ] || [ $status -eq 52 ] || [ $status -eq 45 ]; then
            echo -e "[\033[0;32mONLINE\033[0m] $service_name is listening on port $port"
            return 0
        else
            echo -e "[\033[0;31mOFFLINE\033[0m] $service_name on port $port is unreachable!"
            return 1
        fi
    fi
}

# 1. Probe database
check_port "localhost" 5432 "PostgreSQL"

# 2. Probe cache
check_port "localhost" 6379 "Redis"

# 3. Probe storage S3
echo -n "MinIO Health Status: "
MINIO_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:9000/minio/health/live || echo "DOWN")
if [ "$MINIO_HTTP" = "200" ]; then
    echo -e "[\033[0;32mHEALTHY (200 OK)\033[0m]"
else
    echo -e "[\033[0;31mUNHEALTHY/DOWN (Status: $MINIO_HTTP)\033[0m]"
fi

# 4. Probe Backend health endpoint
echo "Backend /health check:"
BACKEND_RESP=$(curl -s --connect-timeout 2 http://localhost:8000/health || echo "DOWN")
if [ "$BACKEND_RESP" != "DOWN" ]; then
    echo -e " - Status: [\033[0;32mUP\033[0m]"
    echo " - Payload: $BACKEND_RESP"
else
    echo -e " - Status: [\033[0;31mDOWN\033[0m]"
fi
echo "=========================================================="
