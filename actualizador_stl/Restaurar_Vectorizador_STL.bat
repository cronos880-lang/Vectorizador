@echo off
setlocal
title Restaurar Vectorizador anterior a la prueba STL
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restaurar_Vectorizador_STL.ps1"
pause
