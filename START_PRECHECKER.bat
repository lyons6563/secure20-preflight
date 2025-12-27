@echo off
echo Starting SECURE 2.0 Preflight Checker - Drop-Folder Mode...
echo.
echo Running in EXE mode (no Python required).
echo.

SECURE2_Preflight.exe

echo.
echo Watcher exited. Exit code: %ERRORLEVEL%
pause
