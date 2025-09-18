#!/bin/bash
# Quick fix script for DigitalOcean Container Registry authentication

set -e

REGISTRY_NAME="postop-container-registry"
REGISTRY_URL="registry.digitalocean.com/${REGISTRY_NAME}"

echo "🔧 Fixing DigitalOcean Container Registry Authentication"
echo "====================================================="
echo ""

echo "1️⃣ Clearing existing Docker credentials..."
if [ -f ~/.docker/config.json ]; then
    echo "Backing up current Docker config..."
    cp ~/.docker/config.json ~/.docker/config.json.backup.$(date +%s)
fi

# Remove any existing DigitalOcean registry credentials
docker logout registry.digitalocean.com 2>/dev/null || echo "No existing registry.digitalocean.com login found"
echo ""

echo "2️⃣ Fresh doctl authentication check..."
if ! doctl auth list | grep -q "current context"; then
    echo "❌ doctl not authenticated. Please run: doctl auth init"
    exit 1
fi
echo "✅ doctl authenticated"
echo ""

echo "3️⃣ Logging into registry with extended expiry..."
echo "Using 1 hour expiry for registry token..."
if doctl registry login --expiry-seconds 3600; then
    echo "✅ Registry login successful with extended expiry"
else
    echo "❌ Registry login failed"
    exit 1
fi
echo ""

echo "4️⃣ Verifying authentication with test pull..."
echo "Testing authentication by pulling an image..."
echo "docker pull ${REGISTRY_URL}/livekit-agent:latest"

if docker pull "${REGISTRY_URL}/livekit-agent:latest"; then
    echo "✅ Authentication working! Image pulled successfully."
    echo ""
    echo "🎉 Registry authentication fixed!"
    echo ""
    echo "You can now run:"
    echo "   docker compose -f docker-compose.prod.yaml pull"
    echo "   docker compose -f docker-compose.prod.yaml up -d"
else
    echo "❌ Authentication still failing"
    echo ""
    echo "💡 Additional troubleshooting needed:"
    echo "   1. Check if the registry is private and you have access"
    echo "   2. Verify the images were pushed successfully:"
    echo "      doctl registry repository list-tags livekit-agent"
    echo "      doctl registry repository list-tags postop-web"
    echo "   3. Try manual Docker login:"
    echo "      docker login registry.digitalocean.com"
    echo "   4. Check DigitalOcean registry permissions in the web console"
fi