#!/bin/bash
# Manual authentication approach for DigitalOcean Container Registry

set -e

REGISTRY_URL="registry.digitalocean.com"
REGISTRY_NAME="postop-container-registry"
FULL_REGISTRY_URL="${REGISTRY_URL}/${REGISTRY_NAME}"

echo "🔧 Manual DigitalOcean Registry Authentication"
echo "=============================================="
echo ""

echo "1️⃣ Getting authentication token from doctl..."
# Get the authentication token directly from doctl
AUTH_TOKEN=$(doctl auth list --format=Token --no-header | head -1)
if [ -z "$AUTH_TOKEN" ]; then
    echo "❌ Failed to get authentication token from doctl"
    echo "Run: doctl auth init"
    exit 1
fi
echo "✅ Got authentication token"
echo ""

echo "2️⃣ Using manual docker login with token..."
# Use the token directly with docker login
echo "$AUTH_TOKEN" | docker login "$REGISTRY_URL" --username="$(doctl account get --format=Email --no-header)" --password-stdin

echo "✅ Manual docker login completed"
echo ""

echo "3️⃣ Testing authentication with manual pull..."
echo "Attempting to pull: ${FULL_REGISTRY_URL}/livekit-agent:latest"
if docker pull "${FULL_REGISTRY_URL}/livekit-agent:latest"; then
    echo "✅ SUCCESS! Manual authentication working."
    echo ""
    echo "🎉 Now you can run your deployment:"
    echo "   docker compose -f docker-compose.prod.yaml pull"
    echo "   docker compose -f docker-compose.prod.yaml up -d"
else
    echo "❌ Manual pull still failed"
    echo ""
    echo "Let's try alternative approach with registry credentials..."
    echo ""

    echo "4️⃣ Alternative: Using doctl registry docker-config..."
    mkdir -p ~/.docker
    doctl registry docker-config | base64 -d > ~/.docker/config.json
    echo "✅ Updated Docker config with registry credentials"
    echo ""

    echo "5️⃣ Testing with updated config..."
    if docker pull "${FULL_REGISTRY_URL}/livekit-agent:latest"; then
        echo "✅ SUCCESS with docker-config approach!"
    else
        echo "❌ Still failing. Let's check what we have:"
        echo ""
        echo "Current Docker config:"
        cat ~/.docker/config.json | jq '.' 2>/dev/null || cat ~/.docker/config.json
        echo ""
        echo "Registry info:"
        doctl registry get
    fi
fi