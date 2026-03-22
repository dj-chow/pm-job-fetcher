@echo off
cd /d "%~dp0"
set PATH=%PATH%;%APPDATA%\npm
echo === Run started: %DATE% %TIME% === >> "%~dp0digest.log"
python daily_digest.py >> "%~dp0digest.log" 2>&1
echo === Run ended: %DATE% %TIME% === >> "%~dp0digest.log"
echo. >> "%~dp0digest.log"
