#!/bin/bash
# ISP Accountability Monitor - Linux/Mac launcher

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Starting ISP Accountability Monitor..."
echo "Access dashboard at http://localhost:8000"
echo "Press Ctrl+C to stop monitoring"
echo ""
echo "Installing dependencies if needed..."
./venv/bin/pip install -r requirements.txt > /dev/null 2>&1

source venv/bin/activate
python src/main.py
