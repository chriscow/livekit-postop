#!/bin/bash
# Fix DigitalOcean Container Registry authentication for root user (2024 research-based)

set -e

REGISTRY_NAME="postop-container-registry"
REGISTRY_URL="registry.digitalocean.com"
FULL_REGISTRY_URL="${REGISTRY_URL}/${REGISTRY_NAME}"

echo "🔧 Root User DigitalOcean Registry Fix (Research-Based 2024)"
echo "==========================================================="
echo ""

echo "1️⃣ Running as root - ensuring consistent sudo usage..."
echo "Current user: $(whoami)"
if [ "$(whoami)" != "root" ]; then
    echo "❌ This script should be run as root. Use: sudo ./fix-root-auth.sh"
    exit 1
fi
echo "✅ Running as root"
echo ""

echo "2️⃣ Method 1: Using doctl registry docker-config (recommended for root)..."
echo "This generates proper Docker config for root user authentication"

# Backup existing config
if [ -f ~/.docker/config.json ]; then
    cp ~/.docker/config.json ~/.docker/config.json.backup.$(date +%s)
    echo "✅ Backed up existing Docker config"
fi

# Use doctl registry docker-config to generate proper auth
echo "Generating Docker config with doctl registry docker-config..."
mkdir -p ~/.docker
doctl registry docker-config > ~/.docker/config.json
echo "✅ Generated new Docker config"
echo ""

echo "3️⃣ Testing with docker-config method..."
echo "Testing pull: ${FULL_REGISTRY_URL}/livekit-agent:latest"
if docker pull "${FULL_REGISTRY_URL}/livekit-agent:latest"; then
    echo ""
    echo "🎉 SUCCESS with docker-config method!"
    echo ""
    echo "You can now run your deployment:"
    echo "   docker compose -f docker-compose.prod.yaml pull"
    echo "   docker compose -f docker-compose.prod.yaml up -d"
    exit 0
fi
echo ""

echo "4️⃣ Method 2: Direct API token authentication..."
echo "Getting API token for direct authentication..."

# Get the token from doctl config
TOKEN_FILE="/root/.config/doctl/config.yaml"
if [ -f "$TOKEN_FILE" ]; then
    # Extract token from YAML config file
    TOKEN=$(grep "access-token:" "$TOKEN_FILE" | sed 's/.*access-token: *//')
    if [ -n "$TOKEN" ]; then
        echo "✅ Found API token"
        echo ""
        echo "Using token for direct docker login..."
        echo "$TOKEN" | docker login "$REGISTRY_URL" --username="$TOKEN" --password-stdin
        echo ""
        echo "Testing with direct token authentication..."
        if docker pull "${FULL_REGISTRY_URL}/livekit-agent:latest"; then
            echo ""
            echo "🎉 SUCCESS with direct token method!"
            exit 0
        fi
    else
        echo "❌ Could not extract token from config"
    fi
else
    echo "❌ doctl config file not found at $TOKEN_FILE"
fi
echo ""

echo "5️⃣ Method 3: Fresh root authentication..."
echo "Clearing all Docker credentials and re-authenticating as root..."
rm -f ~/.docker/config.json
docker logout "$REGISTRY_URL" 2>/dev/null || true

echo "Running fresh doctl registry login as root..."
doctl registry login --expiry-seconds 3600

echo "Testing fresh authentication..."
if docker pull "${FULL_REGISTRY_URL}/livekit-agent:latest"; then
    echo ""
    echo "🎉 SUCCESS with fresh root authentication!"
    exit 0
fi
echo ""

echo "❌ All methods failed. Diagnostic information:"
echo ""
echo "Registry repositories:"
doctl registry repository list
echo ""
echo "Current Docker config:"
cat ~/.docker/config.json 2>/dev/null || echo "No Docker config found"
echo ""
echo "doctl account info:"
doctl account get