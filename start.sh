#!/bin/sh
set -e

echo "Starting PostOp AI NextJS frontend..."

# Start NextJS in production mode
HOST=0.0.0.0 PORT=3000 exec pnpm start