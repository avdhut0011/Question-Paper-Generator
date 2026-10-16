#!/bin/bash

# QPG Network Server Launcher
# Created by Avadhut Jagtap
# This script starts the QPG application on the network using Waitress

echo "========================================"
echo "QPG Network Server Launcher"
echo "Created by Avadhut Jagtap"
echo "========================================"
echo

# Check if Python is available
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[ERROR] Python is not installed or not in PATH"
    echo "Please install Python 3.12+ and try again"
    exit 1
fi

# Use python3 if available, otherwise python
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "[INFO] Using Python: $PYTHON_CMD"
$PYTHON_CMD --version

# Check if virtual environment exists and activate it
if [ -f "venv/bin/activate" ]; then
    echo "[INFO] Activating virtual environment..."
    source venv/bin/activate
elif [ -f ".venv/bin/activate" ]; then
    echo "[INFO] Activating virtual environment..."
    source .venv/bin/activate
else
    echo "[INFO] No virtual environment found, using system Python"
fi

# Check if waitress is installed
$PYTHON_CMD -c "import waitress" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[INFO] Installing Waitress..."
    pip install waitress
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install Waitress"
        exit 1
    fi
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "[WARNING] .env file not found"
    echo "Configure DATABASE_URL and FLASK_SECRET_KEY in .env. See README.md."
    echo "Example:"
    echo "DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/ashoka_qpg"
    echo "FLASK_SECRET_KEY=your_unique_random_secret"
    echo
    read -p "Press Enter to continue..."
fi

echo "[INFO] Starting QPG Network Server..."
echo "[INFO] The server will be accessible from other computers on your network"
echo "[INFO] Press Ctrl+C to stop the server"
echo

# Start the server with default settings
$PYTHON_CMD serve.py

echo
echo "[INFO] Server stopped"
