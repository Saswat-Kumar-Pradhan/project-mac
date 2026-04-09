#!/bin/bash
echo "Starting MACADS via Podman Compose..."

# Check if podman-compose is available
if ! command -v podman-compose &> /dev/null; then
    echo "podman-compose not found in PATH."
    if [ -d "venv" ]; then
        echo "Found local venv! Activating and installing podman-compose automatically..."
        source venv/bin/activate
        pip install podman-compose
    else
        echo "Attempting to install podman-compose globally via pip..."
        pip3 install podman-compose
    fi
fi

# Run it
podman-compose up --build -d

echo "---------------------------------"
echo "MACADS is running in the background!"
echo "Backend API Docs: http://localhost:8000/docs"
echo "Frontend Dashboard: http://localhost:8501"
echo "---------------------------------"
