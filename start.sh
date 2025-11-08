#!/bin/bash

# Quick Start Script for Calendar Sync System
# Run this to get up and running in 2 minutes

set -e

echo "🚀 Calendar Sync System - Quick Start"
echo "======================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi

echo "✓ Python found: $(python3 --version)"

# Create venv
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Install Playwright
echo "🎭 Installing Playwright browsers..."
playwright install chromium

# Setup credentials
if [ ! -f "credentials.json" ]; then
    echo ""
    echo "⚙️  Setting up credentials..."
    cp credentials.json.template credentials.json
    echo ""
    echo "⚠️  IMPORTANT: Edit credentials.json with your login details:"
    echo "   nano credentials.json"
    echo ""
    read -p "Press Enter when you've added your credentials..."
fi

# Test email parser
echo ""
echo "🧪 Testing email parser..."
python email_parser.py

# Ask about browser test
echo ""
read -p "🧪 Test platform blocker? (shows browser, y/n): " test_blocker

if [ "$test_blocker" = "y" ]; then
    export HEADLESS=false
    echo "Opening browser to test blocking..."
    echo "(This will try to log in and block test dates)"
    python platform_blocker.py || echo "⚠️  Test failed - check credentials"
fi

# Start server
echo ""
echo "✅ Setup complete!"
echo ""
echo "🌐 Starting server..."
echo "   Dashboard: http://localhost:8000"
echo "   API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python main.py
