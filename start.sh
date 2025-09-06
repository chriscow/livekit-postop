#!/bin/bash
set -e

echo "Starting PostOp AI services..."

# Cleanup function
cleanup() {
    echo "Shutting down services..."
    if [ ! -z "$NEXTJS_PID" ] && kill -0 $NEXTJS_PID 2>/dev/null; then
        echo "Stopping NextJS (PID: $NEXTJS_PID)"
        kill -TERM $NEXTJS_PID
        wait $NEXTJS_PID 2>/dev/null || true
    fi
    if [ ! -z "$AGENT_PID" ] && kill -0 $AGENT_PID 2>/dev/null; then
        echo "Stopping Python agent (PID: $AGENT_PID)"
        kill -TERM $AGENT_PID
        wait $AGENT_PID 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

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

# Start Python agent in background too so we can handle signals
echo "Starting LiveKit agent..."
cd /home/appuser/agent
python main.py discharge dev &
AGENT_PID=$!

echo "Python agent started (PID: $AGENT_PID)"

# Wait for either process to exit
wait