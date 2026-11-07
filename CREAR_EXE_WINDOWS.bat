@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Preparar Vectorizador V2.6.exe para Windows

if not exist "exe_entry.py" (
  echo ERROR: Faltan archivos. Extrae el ZIP completo antes de continuar.
  pause
  exit /b 1
)

if exist ".build_venv\Scripts\python.exe" goto entornolisto

echo [1/4] Creando el entorno de construccion local...
py -3 -m venv ".build_venv" 2>nul
if errorlevel 1 python -m venv ".build_venv"
if not exist ".build_venv\Scripts\python.exe" (
  echo ERROR: Se necesita Python 3.10 o posterior SOLO para compilar el EXE.
  echo Descarga Python para Windows e inicia de nuevo este archivo.
  pause
  exit /b 1
)

:entornolisto
echo [2/4] Instalando librerias y empaquetador (necesita Internet)...
".build_venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements_empaquetado.txt
if errorlevel 1 goto fallo

echo [3/4] Creando EXE portable (puede ocupar varios cientos de MB)...
".build_venv\Scripts\python.exe" -m PyInstaller ^
 --noconfirm --clean --windowed --onedir --name Vectorizador ^
 --icon "vectorizador.ico" ^
 --add-data "Vectorizador.html;." ^
 --add-data "editor.js;." ^
 --add-data "mejoras.js;." ^
 --add-data "visor_stl.js;." ^
 --add-data "medidor_stl.js;." ^
 --add-data "proyectos.js;." ^
 --add-data "plantillas;plantillas" ^
 --collect-all cv2 ^
 --collect-all ezdxf ^
 --collect-all shapely ^
 --collect-submodules uvicorn ^
 --collect-submodules pystray ^
 exe_entry.py
if errorlevel 1 goto fallo
if not exist "dist\Vectorizador\Vectorizador.exe" goto fallo

echo [4/4] Creando ZIP portable...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\Vectorizador\*' -DestinationPath 'dist\Vectorizador_Windows_Portable.zip' -Force"
if errorlevel 1 goto fallo

echo.
echo ================================================
echo   LISTO. EL EXE SE HA CREADO CORRECTAMENTE.
echo ================================================
echo Programa:  dist\Vectorizador\Vectorizador.exe
echo Portable:  dist\Vectorizador_Windows_Portable.zip
echo.
echo Para usarlo, abre Vectorizador.exe. No necesitas Python.
echo Para cerrar, utiliza el icono V junto al reloj de Windows.
echo.
pause
exit /b 0

:fallo
echo.
echo ERROR al empaquetar Vectorizador. Lee el mensaje anterior.
echo No se ha modificado tu Ver_oficial original.
pause
exit /b 1
