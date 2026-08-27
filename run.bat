@echo off
REM Obsidian RAG launcher: run unified entry with project .venv Python.
REM Usage:
REM   run.bat                 desktop mode (FastAPI + watchdog + tray + hotkey Ctrl+Shift+S)
REM   run.bat --headless      no-tray mode (FastAPI + watchdog only, for service/verify)
cd /d "%~dp0"
".venv\Scripts\python.exe" -m src.main %*
