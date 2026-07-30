@echo off
cd /d "C:\Users\bravo\OneDrive\Escritorio\JARVIS\Mi-JARVIS"
rem Los .pyc van fuera de OneDrive (menos sincronizacion, menos lag de disco)
set PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\IRIS\pycache
rem SIEMPRE el Python del venv: "py" lanzaba el Python del sistema aunque el
rem venv estuviera activado, y se acumulaban guardias duplicados mezclados.
.venv\Scripts\python.exe guardia.py
pause
