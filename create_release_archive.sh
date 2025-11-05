#!/bin/bash
# Script to create release archive locally (for testing before GitHub release)

set -e

echo "=========================================="
echo "URack ESP32 Platform - Release Archive"
echo "=========================================="
echo ""

# Check if version is provided
if [ -z "$1" ]; then
    echo "Usage: ./create_release_archive.sh VERSION"
    echo "Example: ./create_release_archive.sh v1.0.0"
    exit 1
fi

VERSION=$1
ARCHIVE_NAME="platform-urack-esp32-${VERSION}.zip"

echo "Creating release archive: ${ARCHIVE_NAME}"
echo ""

# Check if prebuilt directory exists
if [ ! -d "prebuilt" ]; then
    echo "⚠️  prebuilt/ directory not found!"
    echo "Building pre-compiled libraries..."
    python3 build_precompiled_libs.py
    echo ""
fi

# Verify prebuilt
echo "Verifying prebuilt directory..."
if [ ! -f "prebuilt/liburack_arduino.a" ]; then
    echo "❌ Error: prebuilt/liburack_arduino.a not found!"
    exit 1
fi

echo "✅ Library: $(du -h prebuilt/liburack_arduino.a | cut -f1)"
echo "✅ Headers: $(find prebuilt/include -name "*.h" | wc -l) files"
echo ""

# Create archive
echo "Creating archive..."
zip -r "${ARCHIVE_NAME}" \
    platform.json \
    platform.py \
    boards/ \
    builder/ \
    prebuilt/ \
    build_precompiled_libs.py \
    README.md \
    .gitignore \
    -x "*.pyc" -x "__pycache__/*" -x ".git/*"

echo ""
echo "=========================================="
echo "✅ Release archive created successfully!"
echo "=========================================="
echo ""
echo "📦 File: ${ARCHIVE_NAME}"
echo "📊 Size: $(du -h ${ARCHIVE_NAME} | cut -f1)"
echo ""
echo "Test usage in platformio.ini:"
echo ""
echo "[env:modesp32v1]"
echo "platform = file://$(pwd)/${ARCHIVE_NAME}"
echo "board = mod-esp32-v1"
echo "framework = arduino"
echo ""

