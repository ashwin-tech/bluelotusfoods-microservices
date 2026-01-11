#!/bin/bash
set -e

echo "========================================" 
echo "🚀 Starting Uvicorn Server"
echo "PORT=${PORT:-NOT_SET}"
echo "Using port: ${PORT:-8000}"
echo "========================================"

exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
