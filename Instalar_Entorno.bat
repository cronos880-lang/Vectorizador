@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 (
 python -m venv .venv
 if errorlevel 1 ( echo Necesitas instalar Python 3.10 o posterior. & pause & exit /b 1 )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Error al instalar dependencias. & pause & exit /b 1 )
echo Instalacion completada. Ejecuta Iniciar.bat.
pause
