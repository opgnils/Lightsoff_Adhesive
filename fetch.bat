@echo off
setlocal enabledelayedexpansion

REM Check if the host argument is provided
if "%~1"=="" (
    echo Usage: %0 host [-d]
    endlocal
    exit /b 1
)

set TARGET_HOST=%~1

REM Check if the config file argument is provided
if "%~2"=="" (
    set CONFIG_FILE=./ssh/config_lightsoff
) else (
    set CONFIG_FILE=./ssh/%~2
)

REM Check for the optional -d flag
set DELETE_FLAG=0
for %%i in (%*) do (
    if "%%i"=="-d" (
        set DELETE_FLAG=1
    )
)

set REMOTE_HOST=
set USER_NAME=
set CURRENT_HOST=

REM Function to parse ssh/config file
for /f "tokens=1,* delims= " %%i in (%CONFIG_FILE%) do (
    if "%%i"=="Host" (
        set CURRENT_HOST=%%j
    ) else if "%%i"=="HostName" (
        if "!CURRENT_HOST!"=="%TARGET_HOST%" (
            set REMOTE_HOST=%%j
        )
    ) else if "%%i"=="User" (
        if "!CURRENT_HOST!"=="%TARGET_HOST%" (
            set USER_NAME=%%j
        )
    )
    if defined REMOTE_HOST if defined USER_NAME goto :found
)

:found
REM Check if the required variables are set
if "%REMOTE_HOST%"=="" (
    echo HostName not found for host %TARGET_HOST% in config file
    endlocal
    exit /b 1
)

if "%USER_NAME%"=="" (
    echo User not found for host %TARGET_HOST% in config file
    endlocal
    exit /b 1
)

REM Set variables
set REMOTE_SAVE_DIR=/home/%USER_NAME%/Documents/LightsOff_Project/cambots/save/
set LOCAL_SAVE_DIR=./

REM Use scp to copy all files from the remote save directory while preserving the directory structure
scp -r %USER_NAME%@%REMOTE_HOST%:%REMOTE_SAVE_DIR% %LOCAL_SAVE_DIR%

REM Optionally delete files from the remote machine if -d flag is set
if "%DELETE_FLAG%"=="1" (
    echo Password required to delete files from remote machine...
    ssh %USER_NAME%@%REMOTE_HOST% "rm -rf %REMOTE_SAVE_DIR%*"
)

endlocal