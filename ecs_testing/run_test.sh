#!/bin/bash
# ECS Connection Capacity Test Runner
# This script runs the connection capacity test with proper setup

set -e

echo "=========================================="
echo "ECS Connection Capacity Test"
echo "=========================================="
echo ""

# Check if running in ECS
if [ -z "$ECS_CONTAINER_METADATA_URI_V4" ]; then
    echo "⚠️  Warning: Not detected as ECS task"
    echo "   This script works best when run in ECS"
    echo ""
fi

# Try to increase file descriptor limit
if command -v ulimit &> /dev/null; then
    echo "Setting file descriptor limit..."
    ulimit -n 65536 2>/dev/null || echo "  Could not set limit (may require root)"
    echo "Current limit: $(ulimit -n)"
    echo ""
fi

# Check environment
echo "Checking ECS environment..."
python check_ecs_environment.py
echo ""

# Run capacity test
echo "Starting connection capacity test..."
echo ""
python test_connection_capacity.py

echo ""
echo "=========================================="
echo "Test Complete"
echo "=========================================="

