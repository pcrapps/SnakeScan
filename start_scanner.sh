#!/bin/bash
# SnakeScan Startup Script
# Automatically cleans up any existing processes and starts the scanner

echo "🛰️  SnakeScan - Mobile Ham Radio Scanner"
echo "========================================"

# Kill any existing processes
echo "Cleaning up existing processes..."
pkill -f scanner_frontend.py 2>/dev/null
sleep 1

# Start the scanner
echo "Starting enhanced GPS scanner on http://localhost:8080"
echo "Press Ctrl+C to stop"
echo ""

python3 scanner_frontend.py