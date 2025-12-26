@echo off
REM SECURE 2.0 Preflight Checker - Drop-Folder Mode Launcher
REM This script starts the inbox watcher for automatic processing

echo Starting SECURE 2.0 Preflight Checker - Drop-Folder Mode...
echo.
echo Place CSV files in the inbox/ folder to process them automatically.
echo Press Ctrl+C to stop the watcher.
echo.

python watch_inbox.py

echo.
echo Watcher stopped. Press any key to close this window.
pause >nul

