#!/bin/bash
# Debug script for DigitalOcean Container Registry authentication issues

set -e

REGISTRY_NAME="postop-container-registry"
REGISTRY_URL="registry.digitalocean.com/${REGISTRY_NAME}"

echo "🔍 DigitalOcean Container Registry Debug Script"
echo "=============================================="
echo ""

echo "1️⃣ Checking doctl authentication..."
if ! doctl auth list | grep -q "current context"; then
    echo "❌ doctl not authenticated. Run: doctl auth init"
    exit 1
else
    echo "✅ doctl is authenticated"
    doctl auth list
fi
echo ""

echo "2️⃣ Verifying registry exists and listing repositories..."
echo "Registry: $REGISTRY_URL"
if doctl registry repository list; then
    echo "✅ Registry accessible via doctl"
else
    echo "❌ Cannot access registry via doctl"
    exit 1
fi
echo ""

echo "3️⃣ Checking if images exist in registry..."
echo "Looking for livekit-agent and postop-web repositories..."
if doctl registry repository list-tags livekit-agent; then
    echo "✅ livekit-agent repository found with tags"
else
    echo "❌ livekit-agent repository not found or no tags"
fi

if doctl registry repository list-tags postop-web; then
    echo "✅ postop-web repository found with tags"
else
    echo "❌ postop-web repository not found or no tags"
fi
echo ""

echo "4️⃣ Checking current Docker authentication..."
echo "Docker config location: ~/.docker/config.json"
if [ -f ~/.docker/config.json ]; then
    echo "Current Docker auths:"
    cat ~/.docker/config.json | jq '.auths // {}' 2>/dev/null || echo "No jq available, showing raw file:"
    cat ~/.docker/config.json | grep -A 5 -B 5 "registry.digitalocean.com" || echo "No DigitalOcean registry auth found"
else
    echo "No Docker config file found"
fi
echo ""

echo "5️⃣ Attempting fresh registry login..."
echo "Logging into DigitalOcean Container Registry..."
if doctl registry login; then
    echo "✅ Registry login successful"
else
    echo "❌ Registry login failed"
    exit 1
fi
echo ""

echo "6️⃣ Testing manual image pull..."
echo "Attempting to pull one image manually..."
echo "Testing: docker pull ${REGISTRY_URL}/livekit-agent:latest"
if docker pull "${REGISTRY_URL}/livekit-agent:latest"; then
    echo "✅ Manual pull successful!"
else
    echo "❌ Manual pull failed"
    echo ""
    echo "💡 Troubleshooting suggestions:"
    echo "   - Run: docker logout registry.digitalocean.com"
    echo "   - Run: doctl registry login --expiry-seconds 3600"
    echo "   - Try: docker login registry.digitalocean.com"
    echo "   - Check if registry is private and requires specific permissions"
fi
echo ""

echo "7️⃣ Testing docker-compose pull with test file..."
if [ -f "test-pull.yaml" ]; then
    echo "Using test-pull.yaml to isolate the issue..."
    if docker compose -f test-pull.yaml pull; then
        echo "✅ docker-compose pull with test file successful!"
    else
        echo "❌ docker-compose pull with test file failed"
    fi
else
    echo "⚠️  test-pull.yaml not found"
fi
echo ""

echo "8️⃣ Current Docker system info..."
echo "Docker version:"
docker --version
echo ""
echo "Docker system info (auth-related):"
docker system info | grep -A 10 -B 5 -i "registry\|credential" || echo "No registry info in docker system info"
echo ""

echo "🏁 Debug complete!"
echo ""
echo "If manual pull worked but docker-compose pull failed:"
echo "  - The issue is likely with docker-compose's credential handling"
echo "  - Try running docker-compose commands with sudo if on Linux"
echo "  - Check if docker-compose is using a different credential store"
echo ""
echo "If manual pull failed:"
echo "  - The registry authentication is the issue"
echo "  - Try: doctl registry login --expiry-seconds 3600"
echo "  - Verify your DigitalOcean account has access to the registry"
echo "  - Check if the registry requires specific permissions"