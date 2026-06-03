#!/bin/bash
# iCross Agent - Start servers with fixed ports
# Frontend=3000, Backend=8000

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Kill any processes occupying our ports
echo "Checking ports..."
for port in 3000 8000; do
  pids=$(netstat -ano | grep LISTENING | grep ":$port " | awk '{print $NF}' | sort -u 2>/dev/null)
  for pid in $pids; do
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
      taskkill //F //PID $pid 2>/dev/null || true
    fi
  done
done
sleep 3

echo "Starting backend on port 8000..."
python3 -m uvicorn icross.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 5

echo "Starting frontend on port 3000..."
cd frontend-react
npx vite --port 3000 --strictPort &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo ""
echo "================================="
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "================================="
echo ""
echo "Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
