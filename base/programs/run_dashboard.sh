#!/bin/bash
# Setup and run script for LightsOff Dashboard

echo "========================================"
echo "  LightsOff Dashboard Setup"
echo "========================================"
echo ""

# Check if textual is installed
if python3 -c "import textual" 2>/dev/null; then
    echo "✓ Textual is already installed"
else
    echo "⚠ Textual is not installed"
    echo ""
    read -p "Would you like to install it now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing textual..."
        pip install textual
        if [ $? -eq 0 ]; then
            echo "✓ Textual installed successfully"
        else
            echo "✗ Failed to install textual"
            exit 1
        fi
    else
        echo "Cannot run dashboard without textual. Exiting."
        exit 1
    fi
fi

echo ""
echo "========================================"
echo "  Starting LightsOff Dashboard..."
echo "========================================"
echo ""
echo "Keyboard shortcuts:"
echo "  • Arrow keys / Tab: Navigate"
echo "  • Enter: Select item"
echo "  • R: Refresh devices"
echo "  • Q: Quit"
echo ""
sleep 2

# Run the dashboard
python3 Dashboard.py
