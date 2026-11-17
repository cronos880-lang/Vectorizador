@echo off
setlocal
title Actualizacion de prueba STL - Vectorizador V2.6
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Actualizar_Vectorizador_STL.ps1"
if errorlevel 1 (
 echo.
 echo No se ha completado la actualizacion. Lee el error.
) else (
 echo.
 echo Proceso finalizado. Usa tu acceso directo habitual.
)
pause
