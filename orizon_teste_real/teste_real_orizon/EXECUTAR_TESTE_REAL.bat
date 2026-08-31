@echo off
cd /d "%~dp0"
python yolo11objectdetection-track.py camera_1.json
if errorlevel 1 (
  echo.
  echo O teste terminou com erro. Copie o texto acima e envie no chat.
)
pause
