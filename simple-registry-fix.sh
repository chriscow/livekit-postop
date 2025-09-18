#!/bin/bash
# Simple registry authentication fix - bypasses complex checks

set -e

REGISTRY_NAME="postop-container-registry"
REGISTRY_URL="registry.digitalocean.com/${REGISTRY_NAME}"

echo "🔧 Simple DigitalOcean Registry Fix"
echo "=================================="
echo ""

echo "1️⃣ Testing doctl command..."
echo "Registry URL: $REGISTRY_URL"
if doctl registry repository list; then
    echo "✅ doctl is working and can access registry"
else
    echo "❌ doctl command failed - check your authentication"
    echo "Run: doctl auth init"
    exit 1
fi
echo ""

echo "2️⃣ Checking if images exist..."
echo "Looking for repositories..."
doctl registry repository list
echo ""

echo "3️⃣ Clearing any old Docker credentials..."
docker logout registry.digitalocean.com 2>/dev/null || echo "No existing login to clear"
echo ""

echo "4️⃣ Logging into registry..."
echo "This will authenticate Docker with the registry..."
doctl registry login --expiry-seconds 3600
echo ""

echo "5️⃣ Testing image pull..."
echo "Attempting to pull: ${REGISTRY_URL}/livekit-agent:latest"
if docker pull "${REGISTRY_URL}/livekit-agent:latest"; then
    echo "✅ SUCCESS! Authentication is working."
    echo ""
    echo "🎉 You can now run your deployment:"
    echo "   docker compose -f docker-compose.prod.yaml pull"
    echo "   docker compose -f docker-compose.prod.yaml up -d"
else
    echo "❌ Pull failed. Let's check what's available..."
    echo ""
    echo "Available repositories:"
    doctl registry repository list
    echo ""
    echo "Tags in livekit-agent repository:"
    doctl registry repository list-tags livekit-agent || echo "No livekit-agent repository found"
    echo ""
    echo "Tags in postop-web repository:"
    doctl registry repository list-tags postop-web || echo "No postop-web repository found"
fi