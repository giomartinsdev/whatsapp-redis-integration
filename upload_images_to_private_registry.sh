#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# 1. Load Environment Variables
if [ -f .env ]; then
  echo "Loading .env file..."
  set -a
  source .env
  set +a
else
  echo "Error: .env file not found."
  exit 1
fi

# Map variables (Ensure these keys match your .env)
REGISTRY="${REGISTRY_URL}"
PASSWORD="${REGISTRY_PASSWORD}"
USERNAME="${REGISTRY_USERNAME}"

# 2. Validation
if [ -z "$REGISTRY" ] || [ -z "$PASSWORD" ] || [ -z "$USERNAME" ]; then
  echo "Error: REGISTRY_URL, REGISTRY_PASSWORD, and REGISTRY_USERNAME must be defined."
  exit 1
fi

# 3. Connectivity Pre-check (Prevents hanging)
echo "Verifying connection to http://$REGISTRY/v2/..."
if ! curl -Is "http://$REGISTRY/v2/" | grep -q "200\|401\|404"; then
  echo "Error: Cannot reach registry at $REGISTRY. Check your firewall or proxy."
  exit 1
fi

# 4. Docker Login
echo "Logging in to $REGISTRY..."
echo "$PASSWORD" | docker login "$REGISTRY" -u "$USERNAME" --password-stdin

echo "========================================"
echo "Building Container Images..."
echo "========================================"

# Python Backend services (API and Worker)
# Platform flag ensures compatibility if building on Apple Silicon for Linux servers
docker build --platform linux/amd64 -t "$REGISTRY/whatsapp-api:latest" -f Dockerfile .
docker build --platform linux/amd64 -t "$REGISTRY/whatsapp-worker:latest" -f Dockerfile .

# Node.js WhatsApp service
docker build --platform linux/amd64 -t "$REGISTRY/whatsapp-node:latest" \
  -f src/whatsapp_worker/Dockerfile ./src/whatsapp_worker

echo "========================================"
echo "Pushing Container Images..."
echo "========================================"

docker push "$REGISTRY/whatsapp-api:latest"
docker push "$REGISTRY/whatsapp-worker:latest"
docker push "$REGISTRY/whatsapp-node:latest"

echo "========================================"
echo "✅ All images pushed successfully!"
echo "========================================"