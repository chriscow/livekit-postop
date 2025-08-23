#!/bin/bash
set -e

echo "Starting PostOp AI services..."

# Start NextJS in background on 0.0.0.0:3000
echo "Starting NextJS frontend..."
cd /home/appuser
HOST=0.0.0.0 PORT=3000 pnpm start &
NEXTJS_PID=$!

# Start Python agent in foreground
echo "Starting LiveKit agent..."
cd /home/appuser/agent
exec python main.py discharge dev