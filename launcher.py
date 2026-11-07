"""Abre siempre la instancia de ESTE paquete, evitando puertos antiguos."""
from __future__ import annotations
import socket
import threading
import time
import urllib.request
import webbrowser
from urllib.parse import urlencode
import uvicorn
from servidor import app, VERSION

HOST='127.0.0.1'


def abrir_cuando_este_listo(port:int)->None:
    url=f'http://{HOST}:{port}/?'+urlencode({'version':VERSION,'instancia':port})
    check=f'http://{HOST}:{port}/api/version'
    for _ in range(100):
        try:
            with urllib.request.urlopen(check,timeout=.3) as r:
                import json
                if json.load(r).get('version')==VERSION:
                    webbrowser.open_new_tab(url)
                    print('Navegador: '+url,flush=True)
                    return
        except (OSError,ValueError):
            time.sleep(.12)
    print('No se pudo abrir el navegador. Comprueba el servidor local.',flush=True)


def main():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.bind((HOST,0))
        sock.listen(2048)
        port=sock.getsockname()[1]
        print(f'Vectorizador {VERSION} | servidor propio http://{HOST}:{port}',flush=True)
        threading.Thread(target=abrir_cuando_este_listo,args=(port,),daemon=True).start()
        config=uvicorn.Config(app,host=HOST,port=port,log_level='warning',access_log=False)
        uvicorn.Server(config).run(sockets=[sock])

if __name__=='__main__':main()
