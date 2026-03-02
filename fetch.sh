#!/bin/bash

# Function to display usage
usage() {
    echo "Usage: $0 host [config_file] [-d]"
    echo "  -d: Delete files from remote machine after copying"
    exit 1
}

# Check if the host argument is provided
if [ $# -eq 0 ]; then
    usage
fi

TARGET_HOST="$1"
DELETE_FLAG=0
CONFIG_FILE="./ssh/config_lightsoff"

# Parse arguments
shift
while [[ $# -gt 0 ]]; do
    case $1 in
        -d)
            DELETE_FLAG=1
            shift
            ;;
        *)
            # If it doesn't start with -, treat it as config file
            if [[ ! "$1" =~ ^- ]]; then
                CONFIG_FILE="./ssh/$1"
            fi
            shift
            ;;
    esac
done

REMOTE_HOST=""
USER_NAME=""
CURRENT_HOST=""

# Function to parse ssh/config file
parse_ssh_config() {
    local found_target=false
    
    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        
        # Remove leading/trailing whitespace
        line=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        
        if [[ "$line" =~ ^Host[[:space:]]+ ]]; then
            CURRENT_HOST=$(echo "$line" | sed 's/^Host[[:space:]]*//;s/[[:space:]]*$//')
            if [[ "$CURRENT_HOST" == "$TARGET_HOST" ]]; then
                found_target=true
            else
                # If we were processing the target host and found a new host, we're done
                if [[ "$found_target" == true ]]; then
                    break
                fi
                found_target=false
            fi
        elif [[ "$found_target" == true ]]; then
            if [[ "$line" =~ ^HostName[[:space:]]+ ]]; then
                REMOTE_HOST=$(echo "$line" | sed 's/^HostName[[:space:]]*//;s/[[:space:]]*$//')
            elif [[ "$line" =~ ^User[[:space:]]+ ]]; then
                USER_NAME=$(echo "$line" | sed 's/^User[[:space:]]*//;s/[[:space:]]*$//')
            fi
        fi
    done < "$CONFIG_FILE"
}

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file $CONFIG_FILE not found"
    exit 1
fi

# Parse the config file
parse_ssh_config

# Check if the required variables are set
if [ -z "$REMOTE_HOST" ]; then
    echo "HostName not found for host $TARGET_HOST in config file"
    exit 1
fi

if [ -z "$USER_NAME" ]; then
    echo "User not found for host $TARGET_HOST in config file"
    exit 1
fi

# Set variables
REMOTE_SAVE_DIR="/home/$USER_NAME/Documents/LightsOff_Project/cambots/save/"
LOCAL_SAVE_DIR="./"

echo "Fetching from $USER_NAME@$REMOTE_HOST:$REMOTE_SAVE_DIR"

# Use scp to copy all files from the remote save directory while preserving the directory structure
scp -r "$USER_NAME@$REMOTE_HOST:$REMOTE_SAVE_DIR" "$LOCAL_SAVE_DIR"

if [ $? -ne 0 ]; then
    echo "Failed to fetch files from remote machine"
    exit 1
fi

echo "Files fetched successfully"

# Optionally delete files from the remote machine if -d flag is set
if [ $DELETE_FLAG -eq 1 ]; then
    echo "Deleting files from remote machine..."
    ssh "$USER_NAME@$REMOTE_HOST" "rm -rf $REMOTE_SAVE_DIR*"
    
    if [ $? -eq 0 ]; then
        echo "Files deleted from remote machine successfully"
    else
        echo "Failed to delete files from remote machine"
        exit 1
    fi
fi
