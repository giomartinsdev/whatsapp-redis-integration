#!/bin/bash

set -e

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

REGISTRY="${REGISTRY_URL}"
PASSWORD="${REGISTRY_PASSWORD}"
USERNAME="${REGISTRY_USERNAME}"

if [ -z "$REGISTRY" ] || [ -z "$PASSWORD" ] || [ -z "$USERNAME" ]; then
  echo "Error: REGISTRY_URL, REGISTRY_PASSWORD, and REGISTRY_USERNAME must be defined in .env file."
  return 1 2>/dev/null || exit 1
fi

echo "Logging in to $REGISTRY..."
echo "$PASSWORD" | docker login "$REGISTRY" -u "$USERNAME" --password-stdin

echo "========================================"
echo "Building Container Images..."
echo "========================================"

# Python Backend services (API and Worker) use the root Dockerfile
docker build --platform linux/amd64 -t "$REGISTRY/whatsapp-api:latest" -f Dockerfile .
docker build --platform linux/amd64 -t "$REGISTRY/whatsapp-worker:latest" -f Dockerfile .

# Node.js WhatsApp service uses the Dockerfile in its subdirectory
docker build --platform linux/amd64 -t "$REGISTRY/whatsapp-node:latest" -f src/whatsapp_worker/Dockerfile ./src/whatsapp_worker

echo "========================================"
echo "Pushing Container Images..."
echo "========================================"

docker push "$REGISTRY/whatsapp-api:latest"
docker push "$REGISTRY/whatsapp-worker:latest"
docker push "$REGISTRY/whatsapp-node:latest"

echo "========================================"
echo "All images pushed successfully!"
echo "========================================"
