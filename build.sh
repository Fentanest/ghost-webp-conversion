#!/bin/bash

# This script builds and pushes a multi-platform Docker image to Docker Hub.
# It uses a local VERSION file for automatic versioning.
# Use the --dev flag to build and push a 'dev' tagged image without versioning.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Argument Parsing ---
BUILD_DEV=false
if [ "$1" == "--dev" ]; then
  BUILD_DEV=true
fi

# --- Tag & Versioning Logic ---
if [ "$BUILD_DEV" = true ]; then
  # --- Dev Build ---
  echo "--- Starting Development Build ---"
  IMAGE_TAGS="-t fentanest/ghost-webp-converter:dev"
else
  # --- Production Build with Versioning ---
  echo "--- Starting Production Build ---"
  VERSION_FILE="VERSION"

  if [ ! -f "$VERSION_FILE" ]; then
    echo "Version file not found. Creating with initial version 0.1.0."
    echo "0.1.0" > "$VERSION_FILE"
  fi

  CURRENT_VERSION=$(cat "$VERSION_FILE")
  echo "Current version is: $CURRENT_VERSION"
  
  IMAGE_TAGS="-t fentanest/ghost-webp-converter:latest -t fentanest/ghost-webp-converter:$CURRENT_VERSION"
fi

# --- Docker Build ---
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

# Build and push the multi-platform image
echo "Building and pushing multi-platform image with tags:"
echo "$IMAGE_TAGS"
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  $IMAGE_TAGS \
  --push .

echo "Successfully built and pushed images."

# --- Update Version (only for production builds) ---
if [ "$BUILD_DEV" = false ]; then
  IFS='.' read -ra V_PARTS <<< "$CURRENT_VERSION"
  V_PARTS[2]=$((V_PARTS[2] + 1))
  NEW_VERSION="${V_PARTS[0]}.${V_PARTS[1]}.${V_PARTS[2]}"
  echo "Incrementing version to: $NEW_VERSION"
  echo "$NEW_VERSION" > "$VERSION_FILE"
  echo "All done. Version updated to $NEW_VERSION."
fi
