from fastapi.testclient import TestClient
from servidor import app, VERSION

def main():
    assert VERSION == 'V2.6'
    cliente = TestClient(app)
    assert cliente.get('/api/version').json()['version'] == VERSION
    html = cliente.get('/').text
    assert '<title>Vectorizador V2.6</title>' in html
    assert 'Medir' in html and 'Centrar vista' in html
    assert 'Guardar proyecto' in html and 'Abrir proyecto' in html
    assert "const VERSION_UI='V2.6'" in html
    for nombre in ['editor.js','mejoras.js','visor_stl.js','medidor_stl.js','proyectos.js']:
        r = cliente.get('/'+nombre)
        assert r.status_code==200,(nombre,r.status_code)
    print('OK: Vectorizador V2.6, interfaz, servidor y cinco modulos cargados.')

if __name__=='__main__': main()
