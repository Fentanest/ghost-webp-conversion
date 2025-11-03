#!/bin/bash

# This script automates versioning, and builds and pushes a multi-platform Docker image.
# It determines the new version by incrementing the latest git tag.

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Git Checks ---
# Check if the working directory is clean
if ! git diff-index --quiet HEAD --; then
    echo "Git working directory is not clean. Please commit or stash your changes."
    exit 1
fi

# Fetch the latest tags from the remote repository
echo "Fetching latest git tags..."
git fetch --tags

# --- Versioning ---
# Get the latest tag, default to v0.0.0 if no tags exist
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
echo "Latest git tag is: $LATEST_TAG"

# Increment the patch version (e.g., v1.2.3 -> v1.2.4)
IFS='.' read -ra V_PARTS <<< "${LATEST_TAG#v}"
V_PARTS[2]=$((V_PARTS[2] + 1))
NEW_VERSION="v${V_PARTS[0]}.${V_PARTS[1]}.${V_PARTS[2]}"
echo "New version will be: $NEW_VERSION"

# --- Docker Build ---
# Define image names
IMAGE_NAME_LATEST="fentanest/ghost-webp-converter:latest"
IMAGE_NAME_VERSIONED="fentanest/ghost-webp-converter:$NEW_VERSION"

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

# --- Git Tagging ---
# Create and push the new git tag
echo "Creating and pushing new git tag: $NEW_VERSION"
git tag "$NEW_VERSION"
git push origin "$NEW_VERSION"

echo "All done. New version $NEW_VERSION is released."
