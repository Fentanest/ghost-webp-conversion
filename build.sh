#!/bin/bash

# This script builds and pushes a multi-platform Docker image to Docker Hub.
# It uses a local VERSION file for automatic versioning.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Versioning ---
# Define the version file
VERSION_FILE="VERSION"

# Check if the version file exists, create it if not
if [ ! -f "$VERSION_FILE" ]; then
  echo "Version file not found. Creating with initial version 0.1.0."
  echo "0.1.0" > "$VERSION_FILE"
fi

# Read the current version
CURRENT_VERSION=$(cat "$VERSION_FILE")
echo "Current version is: $CURRENT_VERSION"

# --- Docker Build ---
# Define image names
IMAGE_NAME_LATEST="fentanest/ghost-webp-converter:latest"
IMAGE_NAME_VERSIONED="fentanest/ghost-webp-converter:$CURRENT_VERSION"

# Check if the user is logged in to Docker Hub
if ! docker info | grep -q "Username"; then
  echo "You are not logged in to Docker Hub. Please run 'docker login' first."
  exit 1
fi

# Set up the multi-arch builder if it doesn't exist
if ! docker buildx ls | grep -q "multi-arch-builder"; then
  echo "Creating a new multi-arch builder..."
  docker buildx create --name multi-arch-builder --use
fi

# Ensure the builder is running
docker buildx inspect --bootstrap

# Build and push the multi-platform image with both 'latest' and version tags
echo "Building and pushing multi-platform image..."
echo "Tags: $IMAGE_NAME_LATEST, $IMAGE_NAME_VERSIONED"
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t "$IMAGE_NAME_LATEST" \
  -t "$IMAGE_NAME_VERSIONED" \
  --push .

echo "Successfully built and pushed images."

# --- Update Version ---
# Increment the patch version (e.g., 1.2.3 -> 1.2.4)
IFS='.' read -ra V_PARTS <<< "$CURRENT_VERSION"
V_PARTS[2]=$((V_PARTS[2] + 1))
NEW_VERSION="${V_PARTS[0]}.${V_PARTS[1]}.${V_PARTS[2]}"
echo "Incrementing version to: $NEW_VERSION"

# Write the new version back to the file
echo "$NEW_VERSION" > "$VERSION_FILE"

echo "All done. Version updated to $NEW_VERSION."