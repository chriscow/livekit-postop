#!/bin/bash
# Deployment script for PostOp AI to DigitalOcean

set -e

REGISTRY_NAME="postop-container-registry"  # Update this
REGISTRY_URL="registry.digitalocean.com/${REGISTRY_NAME}"


echo "🏗️  Building images locally..."
docker compose build

echo "🏷️  Tagging images for DigitalOcean registry..."
docker tag livekit-postop-livekit-agent ${REGISTRY_URL}/livekit-agent:latest
docker tag livekit-postop-postop ${REGISTRY_URL}/postop-web:latest

echo "📤 Pushing to DigitalOcean Container Registry..."
doctl registry login
docker push ${REGISTRY_URL}/livekit-agent:latest
docker push ${REGISTRY_URL}/postop-web:latest

echo "✅ Images pushed successfully!"
echo ""
echo "📋 To deploy on server:"
echo "   1. Copy docker-compose.prod.yaml and .env to server"
echo "   2. Run: doctl registry login"
echo "   3. Run: docker compose -f docker-compose.prod.yaml pull"
echo "   4. Run: docker compose -f docker-compose.prod.yaml up -d"