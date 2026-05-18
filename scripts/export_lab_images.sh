#!/usr/bin/env bash
# Export all lab Docker images as tarballs
# Created to facilitate sharing and offline deployment of lab environments

set -e

# Directory for storing exported images
OUTPUT_DIR="docker-images"

# List of custom images built from labs
IMAGES=(
    "freeswitch"
    "attacker"
    "sip-cli-fs"
    "kamailio"
    "sipp101"
    "asterisk"
    "baresip-cli"
    "sippts"
    "wireshark"
    "coturn"
    "stunner"
    "node_socketiofile"
    "vdoninja"
    "node_mongoose"
    "node_firefox"
    "gophish"
    "firefox"
    "suricata-rtc"
)

# Create output directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

echo "Starting export of Docker images to ${OUTPUT_DIR}/"
echo "=================================================="
echo ""

# Export each image
for image in "${IMAGES[@]}"; do
    output_file="${OUTPUT_DIR}/${image}.tar"
    
    # Check if image exists
    if ! docker image inspect "${image}" > /dev/null 2>&1; then
        echo "⚠️  Skipping ${image}: image not found locally"
        echo "   Build it first with: cd public/labs/<lab_dir> && docker compose build"
        echo ""
        continue
    fi
    
    echo "📦 Exporting ${image}..."
    docker save -o "${output_file}" "${image}"
    
    # Get file size
    size=$(du -h "${output_file}" | cut -f1)
    echo "✅ Saved ${image} → ${output_file} (${size})"
    echo ""
done

echo "=================================================="
echo "Export complete!"
echo ""
echo "To import images on another machine:"
echo "  docker load -i docker-images/<image>.tar"
echo ""
echo "To import all images at once:"
echo "  for f in docker-images/*.tar; do docker load -i \"\$f\"; done"
