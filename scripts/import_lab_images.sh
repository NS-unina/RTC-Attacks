#!/usr/bin/env bash
# Import all lab Docker images from tarballs
# Use this to load images exported with export_lab_images.sh

set -e

# Directory containing exported images
INPUT_DIR="docker-images"

# Check if directory exists
if [ ! -d "${INPUT_DIR}" ]; then
    echo "❌ Error: Directory ${INPUT_DIR}/ not found"
    echo "   Please run export_lab_images.sh first or ensure tarballs are in ${INPUT_DIR}/"
    exit 1
fi

# Find all tar files
tar_files=$(find "${INPUT_DIR}" -name "*.tar" -type f 2>/dev/null || true)

if [ -z "${tar_files}" ]; then
    echo "❌ No .tar files found in ${INPUT_DIR}/"
    exit 1
fi

echo "Starting import of Docker images from ${INPUT_DIR}/"
echo "=================================================="
echo ""

# Import each tarball
for tarball in ${tar_files}; do
    filename=$(basename "${tarball}")
    image_name="${filename%.tar}"
    
    echo "📥 Importing ${filename}..."
    docker load -i "${tarball}"
    echo "✅ Loaded ${image_name}"
    echo ""
done

echo "=================================================="
echo "Import complete!"
echo ""
echo "To verify imported images:"
echo "  docker images"
