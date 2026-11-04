#!/bin/bash
# FILE: start_cloud.sh
# Starts Cloud Jarvis Gateway on Azure VM.

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "[Setup] Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "[Setup] Activating environment and verifying dependencies..."
source .venv/bin/activate
pip install -q -r backend/cloud/requirements.txt

export PYTHONPATH="$PYTHONPATH:$DIR/backend"
echo "[Launch] Starting Cloud Jarvis Gateway on 0.0.0.0:8765..."
python backend/cloud/server.py
