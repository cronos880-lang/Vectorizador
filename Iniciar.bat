@echo off
setlocal
cd /d "%~dp0"
title Vectorizador V2.6
if not exist ".venv\Scripts\python.exe" (
 echo Falta instalar el entorno. Ejecuta Instalar_Entorno.bat una sola vez.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" launcher.py
if errorlevel 1 pause
