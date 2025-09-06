#!/bin/bash
set -e

echo "Starting PostOp AI services..."

# Start NextJS in background on 0.0.0.0:3000
echo "Starting NextJS frontend..."
cd /home/appuser
echo "Running: HOST=0.0.0.0 PORT=3000 pnpm start"
HOST=0.0.0.0 PORT=3000 pnpm start > /tmp/nextjs.log 2>&1 &
NEXTJS_PID=$!

# Give NextJS a moment to start
sleep 5

# Check if NextJS is still running
if ! kill -0 $NEXTJS_PID 2>/dev/null; then
    echo "ERROR: NextJS failed to start!"
    echo "NextJS logs:"
    cat /tmp/nextjs.log
    exit 1
fi

echo "NextJS started successfully (PID: $NEXTJS_PID)"

# Start Python agent in foreground
echo "Starting LiveKit agent..."
cd /home/appuser/agent
exec python main.py discharge dev