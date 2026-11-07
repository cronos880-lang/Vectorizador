#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ ! -f .venv/bin/python ]; then echo 'Ejecuta primero ./Instalar_Entorno.sh';exit 1;fi
.venv/bin/python launcher.py
