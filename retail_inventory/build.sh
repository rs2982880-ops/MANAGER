#!/usr/bin/env bash
# Render Build Script — installs Python deps + builds React frontend

set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Installing Node.js & frontend dependencies ==="
cd frontend
npm install
npm run build
cd ..

echo "=== Build complete ==="
