#!/bin/bash

# Function to display usage
usage() {
    echo "Usage: $0 host [config_file]"
    exit 1
}

# Check if the host argument is provided
if [ $# -eq 0 ]; then
    usage
fi

TARGET_HOST="$1"

# Check if the config file argument is provided
if [ -n "$2" ]; then
    CONFIG_FILE="./ssh/$2"
else
    CONFIG_FILE="./ssh/config_lightsoff"
fi

REMOTE_HOST=""
USER_NAME=""
CURRENT_HOST=""

# Function to parse ssh/config file (robust against whitespace/line-ending quirks)
parse_ssh_config() {
    local found_target=false

    while IFS= read -r line; do
        # Strip leading/trailing whitespace and ignore empty/comment lines
        line="$(echo "$line" | sed 's/^\s*//;s/\s*$//')"
        [ -z "$line" ] && continue
        [[ "$line" =~ ^# ]] && continue

        # Split into key and value (first token is key, rest is value)
        local key value
        key="${line%% *}"
        value="${line#* }"

        if [[ "$key" == "Host" ]]; then
            CURRENT_HOST="$value"
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
            if [[ "$key" == "HostName" ]]; then
                REMOTE_HOST="$value"
            elif [[ "$key" == "User" ]]; then
                USER_NAME="$value"
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
SOURCE_DIR="./cambots/"
REMOTE_PATH="/home/$USER_NAME/Documents/LightsOff_Project/cambots/"

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo "Source directory $SOURCE_DIR not found"
    exit 1
fi

echo "Deploying to $USER_NAME@$REMOTE_HOST:$REMOTE_PATH"

PASSWORD="lightsoff"  # Set your password here

# Use sshpass with rsync
sshpass -p "$PASSWORD" rsync -avz --progress "${SOURCE_DIR%/}" "$USER_NAME@$REMOTE_HOST:/home/$USER_NAME/Documents/LightsOff_Project/"

if [ $? -eq 0 ]; then
    echo "Deployment completed successfully"
else
    echo "Deployment failed"
    exit 1
fi
