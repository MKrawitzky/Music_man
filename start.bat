@echo off
title Lyric Video Generator
cd /d "%~dp0"
echo.
echo  ================================================
echo   Lyric Video Generator
echo   Free ^| Local ^| Stable Diffusion + SVD + Whisper
echo  ================================================
echo.
echo  Starting server... Chrome will open automatically.
echo  Press Ctrl+C to stop.
echo.
".venv\Scripts\python.exe" app.py
pause
