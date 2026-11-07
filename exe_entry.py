"""Arranque portable Windows: abre Vectorizador sin consola y con salida desde bandeja."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn


BASE_DATOS = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'Vectorizador'
ARCHIVO_INSTANCIA = BASE_DATOS / 'instancia.json'


def iniciar_registro():
    BASE_DATOS.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open(BASE_DATOS / 'registro_errores.log', 'a', encoding='utf-8', buffering=1)


def mensaje(texto: str, titulo: str = 'Vectorizador'):
    ctypes.windll.user32.MessageBoxW(0, texto, titulo, 0x40)


def instancia_ya_activa(version: str) -> bool:
    """Evita lanzar varios servidores del programa al hacer doble clic repetido."""
    try:
        registro = json.loads(ARCHIVO_INSTANCIA.read_text('utf-8'))
        puerto = int(registro['puerto'])
        if not (1024 <= puerto <= 65535):
            return False
        url = f'http://127.0.0.1:{puerto}/api/version'
        with urllib.request.urlopen(url, timeout=1.3) as respuesta:
            if json.load(respuesta).get('version') != version:
                return False
        webbrowser.open_new_tab(f'http://127.0.0.1:{puerto}/')
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def escribir_instancia(puerto: int):
    temporal = BASE_DATOS / 'instancia.tmp'
    temporal.write_text(json.dumps({'puerto': puerto, 'pid': os.getpid()}), encoding='utf-8')
    temporal.replace(ARCHIVO_INSTANCIA)


def borrar_instancia():
    try:
        d = json.loads(ARCHIVO_INSTANCIA.read_text('utf-8'))
        if d.get('pid') == os.getpid():
            ARCHIVO_INSTANCIA.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def icono_bandeja():
    from PIL import Image, ImageDraw
    im = Image.new('RGBA', (64, 64), (13, 20, 32, 255))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((5, 5, 58, 58), radius=13, fill=(27, 52, 82, 255), outline=(90, 158, 230, 255), width=3)
    d.line([(16, 18), (31, 47), (48, 18)], fill=(194, 229, 255, 255), width=7, joint='curve')
    d.ellipse((26, 43, 36, 53), fill=(255, 197, 91, 255))
    return im


def main():
    if sys.platform != 'win32':
        raise RuntimeError('El EXE portable se compila y se ejecuta exclusivamente en Windows.')

    iniciar_registro()
    import servidor
    servidor.ARCHIVOS = BASE_DATOS / 'Archivos'
    servidor.CARPETAS = {'fotos': servidor.ARCHIVOS / 'Fotos', 'dxf': servidor.ARCHIVOS / 'DXF', 'stl': servidor.ARCHIVOS / 'STL'}
    servidor.HISTORIAL = servidor.ARCHIVOS / 'Historial'

    # Mutex exclusivo de Windows. No se guarda dentro del ZIP ni depende de Python instalado.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    mutex = kernel.CreateMutexW(None, False, r'Local\Vectorizador_V2_6')
    if not mutex:
        mensaje('No se pudo iniciar Vectorizador. Consulta el registro de errores.')
        return
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        if not instancia_ya_activa(servidor.VERSION):
            mensaje('Vectorizador ya está abierto. Utiliza el icono V de la bandeja del sistema para abrirlo.')
        kernel.CloseHandle(mutex)
        return

    try:
        import pystray
        from pystray import MenuItem as Item
        from pystray import Menu

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', 0))
            sock.listen(2048)
            puerto = sock.getsockname()[1]
            escribir_instancia(puerto)
            url = f'http://127.0.0.1:{puerto}/'
            config = uvicorn.Config(servidor.app, host='127.0.0.1', port=puerto, log_level='warning', access_log=False)
            server = uvicorn.Server(config)
            icono = None

            def abrir(_icon=None, _item=None):
                webbrowser.open_new_tab(url)

            def abrir_dxf(_icon=None, _item=None):
                carpeta = servidor.CARPETAS['dxf']
                carpeta.mkdir(parents=True, exist_ok=True)
                os.startfile(str(carpeta))

            def cerrar(_icon=None, _item=None):
                server.should_exit = True
                if icono is not None:
                    icono.stop()

            icono = pystray.Icon('Vectorizador', icono_bandeja(), 'Vectorizador · Ver_oficial',
                Menu(Item('Abrir Vectorizador', abrir, default=True),
                     Item('Abrir carpeta DXF', abrir_dxf),
                     Item('Salir de Vectorizador', cerrar)))

            def bandeja():
                try:
                    icono.run()
                except Exception as exc:
                    print('Error en bandeja:', repr(exc), file=sys.stderr)
                    server.should_exit = True
                    mensaje('No se pudo crear el icono de la bandeja. Revisa registro_errores.log.')

            threading.Thread(target=bandeja, daemon=True, name='VectorizadorBandeja').start()

            def abrir_cuando_listo():
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{puerto}/api/version', timeout=.3) as respuesta:
                            if json.load(respuesta).get('version') == servidor.VERSION:
                                abrir()
                                return
                    except (OSError, ValueError):
                        time.sleep(.12)

            threading.Thread(target=abrir_cuando_listo, daemon=True).start()
            server.run(sockets=[sock])
            try:
                icono.stop()
            except Exception:
                pass
    except Exception as exc:
        import traceback
        traceback.print_exc(file=sys.stderr)
        mensaje(r'No se pudo iniciar Vectorizador. Revisa el archivo registro_errores.log en AppData\Local\Vectorizador.')
    finally:
        borrar_instancia()
        kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
