#!/bin/bash
# Fix DigitalOcean Container Registry authentication based on 2024 research

echo "🔧 DigitalOcean Registry Authentication Fix (2024 Solution)"
echo "=========================================================="
echo ""

echo "1️⃣ Checking if doctl is installed via snap..."
if snap list doctl 2>/dev/null; then
    echo "✅ doctl is installed via snap"
    echo ""
    echo "2️⃣ Connecting doctl snap to Docker (most common 2024 fix)..."
    sudo snap connect doctl:dot-docker
    echo "✅ Snap connection established"
    echo ""
else
    echo "ℹ️  doctl not installed via snap, skipping snap connection"
    echo ""
fi

echo "3️⃣ Clearing existing Docker credentials..."
docker logout registry.digitalocean.com 2>/dev/null || echo "No existing credentials to clear"
echo ""

echo "4️⃣ Fresh registry login..."
doctl registry login --expiry-seconds 3600
echo ""

echo "5️⃣ Testing authentication..."
REGISTRY_URL="registry.digitalocean.com/postop-container-registry"
echo "Testing pull: ${REGISTRY_URL}/livekit-agent:latest"

if docker pull "${REGISTRY_URL}/livekit-agent:latest"; then
    echo ""
    echo "🎉 SUCCESS! Authentication fixed!"
    echo ""
    echo "You can now run:"
    echo "   docker compose -f docker-compose.prod.yaml pull"
    echo "   docker compose -f docker-compose.prod.yaml up -d"
else
    echo ""
    echo "❌ Still failing. Let's try alternative solutions..."
    echo ""

    echo "6️⃣ Alternative: Checking credential store..."
    echo "Current Docker config:"
    if [ -f ~/.docker/config.json ]; then
        cat ~/.docker/config.json | jq '.' 2>/dev/null || cat ~/.docker/config.json
    else
        echo "No Docker config found"
    fi
    echo ""

    echo "7️⃣ Alternative: Manual token approach..."
    echo "Getting DigitalOcean token for manual login..."
    if TOKEN=$(doctl auth list --format=Token --no-header | head -1); then
        echo "Using token as both username and password (2025 method)..."
        echo "$TOKEN" | docker login registry.digitalocean.com --username="$TOKEN" --password-stdin
        echo ""
        echo "Testing with manual token login..."
        docker pull "${REGISTRY_URL}/livekit-agent:latest"
    else
        echo "Could not get token from doctl"
    fi
fi