@echo off
setlocal enabledelayedexpansion

REM Check if the host argument is provided
if "%~1"=="" (
    echo Usage: %0 host
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
set SOURCE_DIR=./cambots/
set REMOTE_PATH=/home/%USER_NAME%/Documents/LightsOff_Project/cambots/

REM Use scp to copy all files in the source directory
scp -r %SOURCE_DIR%* %USER_NAME%@%REMOTE_HOST%:%REMOTE_PATH%

endlocal