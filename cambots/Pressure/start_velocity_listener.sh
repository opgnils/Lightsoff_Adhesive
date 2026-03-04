#!/bin/bash
# Start the Nanotec velocity control listener

cd ~/Documents/LightsOff_Project/cambots/Pressure

# Kill any existing listener on port 5002
lsof -ti:5002 | xargs kill -9 2>/dev/null

# Wait for port to be released
sleep 1

# Start the velocity control listener
nohup python3 velocity_control.py > velocity_control.log 2>&1 &

echo "Velocity control listener started on port 5002"
echo "PID: $!"
