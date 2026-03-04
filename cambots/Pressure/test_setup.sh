#!/bin/bash
# Quick test script to verify Nanotec motor setup

echo "=========================================="
echo "NANOTEC MOTOR TEST SCRIPT"
echo "=========================================="
echo ""

cd ~/Documents/LightsOff_Project/cambots/Pressure || exit 1

echo "1. Testing Python and nanolib import..."
python3 -c "from nanotec_nanolib import Nanolib; print('   ✓ Import successful')" || {
    echo "   ✗ FAILED - nanolib not installed"
    echo "   Install with: pip3 install nanotec-nanolib"
    exit 1
}

echo ""
echo "2. Scanning for motor devices..."
python3 find_motor.py

echo ""
echo "3. Check if velocity listener is running..."
if lsof -i:5002 >/dev/null 2>&1; then
    echo "   ✓ Velocity listener IS running on port 5002"
    lsof -i:5002
else
    echo "   ✗ Velocity listener is NOT running"
    echo "   Start with: python3 velocity_control.py"
fi

echo ""
echo "=========================================="
echo "TEST COMPLETE"
echo "=========================================="
