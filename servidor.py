"""Vectorizador V2.0.26: calibración proyectiva con marcadores A4 V2 y retrocompatibilidad."""
from pathlib import Path
import math
import json
import os
import hashlib
import subprocess
import sys
import unicodedata
from urllib.parse import quote
from typing import Literal
from fastapi import FastAPI,UploadFile,File,Form,HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,ConfigDict
from motor.vectorizar import decodificar,extraer_contornos,estimar_escala
from motor.agujeros_adicionales import recuperar_agujeros
from motor.exportar import dxf,geometria
from motor.editor_cad import documento_inicial,dxf_editado
from motor.fondo_editor import preparar_fondo
from motor.autoescala import calibracion_automatica
from motor.escala_hoja import calibracion_a4
from motor.escala_reglas import calibracion_reglas_generica
from motor.marcadores_a4 import detectar_marcadores, calibracion_marcadores, excluir_marcadores_plantilla
from motor.escala_papel_fisico import verificar_y_corregir
from motor.afinado_v13 import calibracion_general
import uvicorn

ROOT=Path(__file__).resolve().parent
ARCHIVOS=ROOT/'Archivos'
CARPETAS={'fotos':ARCHIVOS/'Fotos','dxf':ARCHIVOS/'DXF','stl':ARCHIVOS/'STL'}
VERSION='V2.6'
app=FastAPI(title=f'Vectorizador {VERSION} DXF/STL')
MAX_FILE=20*1024*1024

@app.get('/')
def inicio():return FileResponse(ROOT/'Vectorizador.html',headers={'Cache-Control':'no-store, no-cache, must-revalidate', 'Pragma':'no-cache', 'Expires':'0'})

@app.get('/editor.js')
def editor_script():return FileResponse(ROOT/'editor.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

@app.get('/mejoras.js')
def mejoras_script():return FileResponse(ROOT/'mejoras.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

@app.get('/visor_stl.js')
def visor_stl_script():return FileResponse(ROOT/'visor_stl.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

@app.get('/medidor_stl.js')
def medidor_stl_script():return FileResponse(ROOT/'medidor_stl.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

@app.get('/proyectos.js')
def proyectos_script():return FileResponse(ROOT/'proyectos.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})

@app.get('/api/version')
def version():return {'version':VERSION, 'producto':'Vectorizador', 'formato':'DXF/STL'}


def ruta_carpeta(tipo:str)->Path:
    if tipo not in CARPETAS:
        raise HTTPException(404,'Carpeta no reconocida.')
    destino=CARPETAS[tipo]
    try: destino.mkdir(parents=True,exist_ok=True)
    except OSError as e:raise HTTPException(500,f'No se pudo crear la carpeta {tipo}: {e}') from e
    return destino

def nombre_foto(nombre:str)->str:
    from re import sub
    n=Path((nombre or 'foto.jpg').replace('\\','/').split('/')[-1]).name
    n=sub(r'[<>:"/\\|?*\x00-\x1f]','_',n).strip(' .')[:110]
    if Path(n).suffix.lower() not in {'.jpeg','.jpg','.png'}:
        raise HTTPException(422,'La foto debe ser JPG o PNG.')
    return n

def guardar_en_carpeta(tipo:str,nombre:str,contenido:bytes)->str:
    # No sobreescribir archivos diferentes ni duplicar cargas idénticas.
    ruta=ruta_carpeta(tipo)
    base=Path(nombre)
    for i in range(0,10000):
        actual=base.name if i==0 else f'{base.stem}_{i+1}{base.suffix}'
        fichero=ruta/actual
        try:
            with fichero.open('xb') as f:f.write(contenido)
            return actual
        except FileExistsError:
            # Mismo nombre y mismos bytes: reutilizarlo.
            if fichero.is_file() and fichero.stat().st_size==len(contenido):
                if hashlib.sha256(fichero.read_bytes()).digest()==hashlib.sha256(contenido).digest():
                    return actual
    raise HTTPException(409,'Demasiados archivos con el mismo nombre.')

@app.get('/api/fotos/listar')
def listar_fotos():
    carpeta=ruta_carpeta('fotos')
    fotos=[p for p in carpeta.iterdir() if p.is_file() and not p.is_symlink()
           and p.suffix.lower() in {'.jpg','.jpeg','.png'}]
    fotos.sort(key=lambda p:p.stat().st_mtime,reverse=True)
    return {'fotos':[p.name for p in fotos[:200]]}

@app.get('/api/fotos/archivo/{nombre}')
def abrir_foto_guardada(nombre:str):
    # Solo archivos directos de Fotos, nunca rutas o enlaces fuera de la carpeta.
    carpeta=ruta_carpeta('fotos')
    if not nombre or nombre in {'.','..'} or '/' in nombre or '\\' in nombre:
        raise HTTPException(400,'Nombre de fotografía no válido.')
    try:nombre=nombre_foto(nombre)
    except HTTPException as e:raise HTTPException(404,'Fotografía no encontrada.') from e
    destino=carpeta/nombre
    if not destino.is_file() or destino.is_symlink() or destino.parent.resolve()!=carpeta.resolve():
        raise HTTPException(404,'Fotografía no encontrada.')
    return FileResponse(destino,media_type='image/png' if destino.suffix.lower()=='.png' else 'image/jpeg',
                        headers={'Cache-Control':'no-store'})

@app.post('/api/fotos/guardar')
async def guardar_foto(archivo:UploadFile=File(...)):
    foto=await archivo.read(MAX_FILE+1)
    if len(foto)>MAX_FILE:raise HTTPException(413,'Foto demasiado grande (20 MB máximo).')
    try:
        filename=nombre_foto(archivo.filename or '')
        decodificar(foto) # Verifica imagen real antes de guardarla.
        final=guardar_en_carpeta('fotos',filename,foto)
        return {'guardado':True,'archivo':final,'carpeta':'Fotos'}
    except (ValueError,TypeError) as e:
        raise HTTPException(422,f'Fotografía inválida: {e}') from e
    except OSError as e:
        raise HTTPException(500,f'Error al guardar la foto: {e}') from e

@app.post('/api/carpetas/{tipo}/abrir')
def abrir_carpeta(tipo:Literal['fotos','dxf','stl']):
    destino=ruta_carpeta(tipo)
    try:
        if sys.platform=='win32':os.startfile(str(destino))
        elif sys.platform=='darwin':subprocess.Popen(['open',str(destino)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:subprocess.Popen(['xdg-open',str(destino)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (OSError,FileNotFoundError) as e:
        raise HTTPException(503,f'No se pudo abrir el explorador de archivos: {e}. Carpeta: {destino}') from e
    return {'abierta':True,'carpeta':str(destino)}

@app.post('/api/vectorizar')
async def vectorizar(archivo:UploadFile=File(...),umbral:int=Form(120),recorte:str=Form(''), recuperar:bool=Form(True)):
    foto=await archivo.read(MAX_FILE+1)
    if len(foto)>MAX_FILE:raise HTTPException(413,'Archivo demasiado grande (máximo 20 MB).')
    try:
        r=json.loads(recorte) if recorte else None
        imagen=decodificar(foto)
        marcadores = detectar_marcadores(imagen)
        cal_previa = calibracion_marcadores(imagen, found=marcadores)
        excluir = excluir_marcadores_plantilla(imagen, marcadores, cal_previa)
        vector=extraer_contornos(imagen,umbral,'precision',r,exclusiones=excluir)
        vector=recuperar_agujeros(imagen,vector) if recuperar else {**vector,'agujeros_recuperados':0}
        vector=evaluar_bordes(imagen,vector)
        cal=(calibracion_marcadores(imagen,vector['bbox_px'],found=marcadores)
             if cal_previa['estado']=='detectada' else cal_previa)
        if cal['estado']=='detectada':
            cal, _ = verificar_y_corregir(imagen, cal)
        if cal['estado']!='detectada':
            cal=calibracion_automatica(imagen,vector['bbox_px'])
        if cal['estado']!='detectada':
            # Admite reglas a ambos lados, arriba o abajo, y evita
            # confundir 5 mm con 1 cm en fotografías de mayor resolución.
            general=calibracion_general(imagen,vector['bbox_px'])
            if general['estado']!='no_fiable':
                cal=general
            else:
                # Detector general de retícula en esquinas y fotos recortadas.
                # Solo estima mm si ambos ejes muestran marcas compatibles de 1 cm.
                reticula=calibracion_reglas_generica(imagen,vector['bbox_px'])
                if reticula['estado']!='no_fiable':
                    cal=reticula
                else:
                    vieja=estimar_escala(imagen)
                    if vieja['px_mm_x'] and vieja['px_mm_y']:
                        cal={'estado':'estimada','metodo':'reglas_parciales',
                             'px_mm_x':vieja['px_mm_x'],'px_mm_y':vieja['px_mm_y'],
                             'afin_automatica':None,'descripcion':'Escala solo aproximada; sin corrección de inclinación.'}
        if cal['estado']=='no_fiable':
            hoja=calibracion_a4(imagen,vector['bbox_px'])
            if hoja['estado']!='no_fiable':cal=hoja
        return {**vector,'calibracion':cal,
                'diagnostico':{
                    'pieza_detectada':True,
                    'escala_disponible':cal['estado'] in ('estimada','detectada'),
                    'codigo':'LISTO' if cal['estado'] in ('estimada','detectada') else 'SIN_ESCALA',
                    'mensaje':('La pieza está vectorizada. No se puede calcular una escala real a partir de esta foto; '
                               'puedes exportar sin calibrar o introducir una escala.') if cal['estado']=='no_fiable'
                              else cal.get('descripcion','Escala calculada aproximadamente.'),
                    'solucion':('Incluye dos reglas nítidas, fotografía la hoja A4 entera o usa el ajuste opcional.'
                                if cal['estado']=='no_fiable' else '')}}
    except (ValueError,TypeError,json.JSONDecodeError) as e:
        raise HTTPException(422,str(e)) from e

class Exportacion(BaseModel):
    model_config=ConfigDict(extra="forbid")
    vector:dict
    px_mm_x:float=1.0
    px_mm_y:float=1.0
    afin:dict|None=None
    proyectiva:dict|None=None
    nombre:str|None=None
    sin_escala:bool=False
    entidades_editadas:list[dict]|None=None
    guardar_copia:bool=True
    exigir_edicion:bool=False

def nombre_dxf(nombre:str|None)->str:
    # Nombre seguro tanto para Windows como para Content-Disposition.
    from re import sub
    n=sub(r'[<>:"/\\|?*\x00-\x1f]', '_', (nombre or 'pieza_vector.dxf').strip())
    n=n.strip(' .')[:100]
    if not n.lower().endswith('.dxf'):n+='.dxf'
    return n if n.lower()!='.dxf' else 'pieza_vector.dxf'

@app.post('/api/editor/iniciar')
def editor_iniciar(datos:Exportacion):
    try:
        return documento_inicial(datos.vector,datos.px_mm_x,datos.px_mm_y,
                                 datos.afin,datos.proyectiva,datos.sin_escala)
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as e:
        raise HTTPException(422,f'No se pudo abrir el editor CAD: {e}') from e

@app.post('/api/editor/fondo')
async def fondo_editor(archivo:UploadFile=File(...),datos:str=Form(...)):
    foto=await archivo.read(MAX_FILE+1)
    if len(foto)>MAX_FILE:
        raise HTTPException(413,'Fotografía demasiado grande (máximo 20 MB).')
    try:
        payload=Exportacion.model_validate_json(datos)
        imagen=decodificar(foto)
        return preparar_fondo(imagen,payload.vector,payload.px_mm_x,payload.px_mm_y,
                              payload.afin,payload.proyectiva,payload.sin_escala)
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as e:
        raise HTTPException(422,f'No se pudo alinear el fondo fotográfico: {e}') from e

@app.post('/api/exportar')
def exportar(datos:Exportacion):
    try:
        if datos.exigir_edicion and datos.entidades_editadas is None:
            raise ValueError('La interfaz pidió exportar el CAD editado pero no envió las entidades; no se guardará el DXF automático.')
        tipo_exportado='editado' if datos.entidades_editadas is not None else 'automatico'
        raw=(dxf_editado(datos.entidades_editadas,datos.sin_escala)
             if datos.entidades_editadas is not None
             else dxf(datos.vector,datos.px_mm_x,datos.px_mm_y,datos.afin,datos.proyectiva,
                      sin_escala=datos.sin_escala))
        filename=nombre_dxf(datos.nombre)
        nombre_guardado=guardar_en_carpeta('dxf',filename,raw) if datos.guardar_copia else None
        # Las cabeceras HTTP deben ser ASCII; UTF-8 se codifica según RFC 5987.
        fallback=unicodedata.normalize('NFKD',filename).encode('ascii','ignore').decode('ascii') or 'pieza_vector.dxf'
        disposition=f'attachment; filename="{fallback}"'
        if filename!=fallback:
            disposition+=f"; filename*=UTF-8''{quote(filename, safe='')}"
        return Response(content=raw,media_type='application/dxf',
                        headers={'Content-Disposition':disposition,
                                 'X-DXF-Archivado':quote(nombre_guardado or '',safe=''),
                                 'X-Vectorizador-Tipo':tipo_exportado,
                                 'X-Vectorizador-Entidades':str(len(datos.entidades_editadas)) if datos.entidades_editadas is not None else 'automatico',
                                 'X-Vectorizador-Version':VERSION,
                                 'X-Vectorizador-SHA256':hashlib.sha256(raw).hexdigest()})
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as e:
        raise HTTPException(422,f'No se pudo exportar el DXF: {e}') from e


# V2.0.26: extrusión STL con selector opcional de precisión geométrica.
# DXF y motor de vectorización no se alteran.
class ExportacionSTL(Exportacion):
    grosor:float
    compensacion_agujeros:float = 0.0
    precision_stl:Literal['normal','alta','maxima'] = 'normal'
    reparacion_stl_prueba:bool = False
    offset_exterior:float = 0.0
    objetivo_ancho_mm:float|None = None
    objetivo_alto_mm:float|None = None
    sha256_stl_esperado:str|None = None  # Vista previa exacta en exportaciones sin selector nativo.

@app.post('/api/exportar-stl')
def exportar_stl(datos:ExportacionSTL):
    from motor.extrusion_stl import construir_stl
    from motor.correccion_dimensional import corregir_entidades
    try:
        if datos.sin_escala:
            raise ValueError('El STL requiere calibración en milímetros. Corrige la escala de la foto antes de extruir.')
        if datos.exigir_edicion and datos.entidades_editadas is None:
            raise ValueError('No se recibieron las entidades CAD editadas; se ha cancelado la exportación.')
        entidades=(datos.entidades_editadas if datos.entidades_editadas is not None
                   else documento_inicial(datos.vector, datos.px_mm_x, datos.px_mm_y,
                                         datos.afin, datos.proyectiva, False)['entidades'])
        entidades,correccion=corregir_entidades(entidades,datos.objetivo_ancho_mm,datos.objetivo_alto_mm)
        raw,meta=construir_stl(entidades, datos.grosor, datos.compensacion_agujeros, datos.precision_stl, datos.offset_exterior,
                               datos.reparacion_stl_prueba)
        # Una vista previa existente DEBE coincidir antes de archivar los bytes.
        stl_hash=hashlib.sha256(raw).hexdigest()
        if datos.sha256_stl_esperado is not None and datos.sha256_stl_esperado != stl_hash:
            raise ValueError('El STL ha cambiado desde la vista previa. No se ha guardado ningún archivo.')
        # Nombre STL seguro, independiente del nombre opcional DXF.
        name=nombre_dxf(datos.nombre or 'pieza_vector')
        if name.lower().endswith('.stl.dxf'):
            name=name[:-4]
        elif name.lower().endswith('.dxf'):
            name=name[:-4]+'.stl'
        archived=guardar_en_carpeta('stl',name,raw) if datos.guardar_copia else None
        fallback=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode('ascii') or 'pieza.stl'
        disposition=f'attachment; filename="{fallback}"'
        if fallback!=name:
            disposition+=f"; filename*=UTF-8''{quote(name,safe='')}"
        return Response(content=raw,media_type='model/stl',headers={
            'Content-Disposition':disposition,
            'X-Vectorizador-Tipo':'editado' if datos.entidades_editadas is not None else 'automatico',
            'X-Vectorizador-STL-SHA256':stl_hash,
            'X-Vectorizador-Version':VERSION,
            'X-Vectorizador-Entidades':str(len(entidades)),
            'X-Vectorizador-Triangulos':str(meta['triangulos']),
            'X-Vectorizador-Reparaciones-Prueba':str(len(meta['reparaciones_prueba'])),
            'X-Vectorizador-Ancho':str(meta['ancho_mm']),
            'X-Vectorizador-Alto':str(meta['alto_mm']),
            'X-Vectorizador-Grosor':str(meta['grosor_mm']),
            'X-Vectorizador-Volumen':str(meta['volumen_mm3']),
            'X-Vectorizador-Holgura-Diametro':str(meta['compensacion_agujeros_mm']),
            'X-Vectorizador-Precision-STL':meta['precision_stl'],
            'X-Vectorizador-Offset-Exterior-MM':str(meta['offset_exterior_mm']),
            'X-Vectorizador-Factor-X':str(correccion['escala_x']),
            'X-Vectorizador-Factor-Y':str(correccion['escala_y']),
            'X-Vectorizador-Error-Cuerda-MM':str(meta['error_cuerda_mm']),
            'X-STL-Archivado':quote(archived or '',safe=''),
        })
    except (ValueError, KeyError, TypeError, IndexError, ArithmeticError) as e:
        raise HTTPException(422, f'No se pudo extruir STL: {e}') from e

# V2.0.30: DXF del MISMO perfil exterior que el STL previsualizado.
# /api/exportar sigue siendo el DXF ORIGINAL, sin offset.
@app.post('/api/exportar-dxf-ajustado')
def exportar_dxf_ajustado(datos:ExportacionSTL):
    from motor.extrusion_stl import construir_stl
    from motor.dxf_offset import construir_dxf_ajustado
    from motor.correccion_dimensional import corregir_entidades
    try:
        if datos.sin_escala:
            raise ValueError('El DXF ajustado exige calibración real en milímetros.')
        if datos.exigir_edicion and datos.entidades_editadas is None:
            raise ValueError('Faltan las entidades CAD editadas. Exportación cancelada.')
        if datos.reparacion_stl_prueba:
            raise ValueError('DXF ajustado desactivado en modo reparación STL experimental: el CAD original no se ha modificado.')
        if not datos.sha256_stl_esperado or len(datos.sha256_stl_esperado)!=64:
            raise ValueError('Genera primero una vista previa STL validada antes de exportar el DXF ajustado.')
        entidades=(datos.entidades_editadas if datos.entidades_editadas is not None else
                   documento_inicial(datos.vector,datos.px_mm_x,datos.px_mm_y,
                                     datos.afin,datos.proyectiva,False)['entidades'])
        entidades,correccion=corregir_entidades(entidades,datos.objetivo_ancho_mm,datos.objetivo_alto_mm)
        stl,meta=construir_stl(entidades,datos.grosor,datos.compensacion_agujeros,
                               datos.precision_stl,datos.offset_exterior)
        sha=hashlib.sha256(stl).hexdigest()
        if sha != datos.sha256_stl_esperado:
            raise ValueError('El STL previsualizado ya no coincide con el offset actual. Actualiza antes de exportar.')
        raw,dxf_meta=construir_dxf_ajustado(entidades,datos.offset_exterior,datos.precision_stl)
        if (abs(dxf_meta['ancho_mm']-meta['ancho_mm'])>0.001 or
            abs(dxf_meta['alto_mm']-meta['alto_mm'])>0.001):
            raise ValueError('Las dimensiones exteriores DXF y STL difieren. Exportación cancelada.')
        filename=nombre_dxf(datos.nombre)
        archived=guardar_en_carpeta('dxf',filename,raw) if datos.guardar_copia else None
        fallback=unicodedata.normalize('NFKD',filename).encode('ascii','ignore').decode('ascii') or 'pieza_ajustada.dxf'
        disposition=f'attachment; filename="{fallback}"'
        if filename!=fallback:
            disposition+=f"; filename*=UTF-8''{quote(filename,safe='')}"
        return Response(content=raw,media_type='application/dxf',headers={
            'Content-Disposition':disposition,
            'X-Vectorizador-Version':VERSION,
            'X-Vectorizador-Tipo':'editado' if datos.entidades_editadas is not None else 'automatico',
            'X-Vectorizador-Entidades':str(len(entidades)),
            'X-Vectorizador-Offset-Exterior-MM':str(datos.offset_exterior),
            'X-Vectorizador-Factor-X':str(correccion['escala_x']),
            'X-Vectorizador-Factor-Y':str(correccion['escala_y']),
            'X-Vectorizador-Ancho':str(dxf_meta['ancho_mm']),
            'X-Vectorizador-Alto':str(dxf_meta['alto_mm']),
            'X-Vectorizador-DXF-SHA256':hashlib.sha256(raw).hexdigest(),
            'X-Vectorizador-STL-SHA256':sha,
            'X-DXF-Archivado':quote(archived or '',safe=''),
            'X-Vectorizador-Holgura-Solo-STL':str(datos.compensacion_agujeros),
        })
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as e:
        raise HTTPException(422,f'No se pudo exportar el DXF ajustado: {e}') from e

class Medidas(Exportacion):pass

@app.post('/api/medidas')
def medidas(datos:Medidas):
    try:
        _,resumen=geometria(datos.vector,datos.px_mm_x,datos.px_mm_y,
                            datos.afin,datos.proyectiva)
        return resumen
    except (ValueError,KeyError,TypeError,IndexError,ArithmeticError) as e:
        raise HTTPException(422,str(e)) from e

if __name__=='__main__':
    from launcher import main
    main()

# --- Extensiones V2.0.18, independientes de la calibración estable ---
from motor.funciones_avanzadas import detectar_piezas, verificar_plano, evaluar_bordes
from datetime import datetime, timezone
import re

HISTORIAL=ARCHIVOS/'Historial'

@app.post('/api/piezas/detectar')
async def piezas_detectar(archivo:UploadFile=File(...), umbral:int=Form(120)):
    data=await archivo.read(MAX_FILE+1)
    if len(data)>MAX_FILE:raise HTTPException(413,'Foto demasiado grande.')
    try:
        img=decodificar(data)
        marcadores=detectar_marcadores(img)
        cal=calibracion_marcadores(img,found=marcadores)
        return {'piezas':detectar_piezas(img,umbral,excluir_marcadores_plantilla(img,marcadores,cal)),
                'aviso':'Selecciona solamente las piezas reales. La detección puede incluir textos o marcas.'}
    except (ValueError,TypeError) as e:raise HTTPException(422,str(e)) from e

@app.post('/api/editor/verificar')
def editor_verificar(datos:Exportacion):
    if datos.entidades_editadas is None:raise HTTPException(422,'Abre primero el editor CAD.')
    try:return verificar_plano(datos.entidades_editadas)
    except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e)) from e

@app.post('/api/historial/guardar')
async def historial_guardar(archivo:UploadFile=File(...), datos:str=Form(...)):
    raw=await archivo.read(MAX_FILE+1)
    if len(raw)>MAX_FILE:raise HTTPException(413,'Imagen demasiado grande.')
    try:
        decodificar(raw)
        payload=json.loads(datos)
        if not isinstance(payload,dict):raise ValueError('Trabajo inválido.')
        vector=payload.get('vector')
        if not isinstance(vector,dict) or not 1<=len(vector.get('contornos',[]))<=100:raise ValueError('Vectorización inválida.')
        # Comprobar entidades CAD editadas con validador existente.
        editadas=payload.get('entidades')
        if editadas is not None:
            from motor.editor_cad import validar_entidades
            validar_entidades(editadas)
        if len(datos)>5_000_000:raise ValueError('Proyecto excesivamente grande.')
        HISTORIAL.mkdir(parents=True,exist_ok=True)
        ident=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
        suffix='.png' if raw.startswith(b'\x89PNG') else '.jpg'
        (HISTORIAL/(ident+suffix)).write_bytes(raw)
        safe=nombre_foto(archivo.filename or 'foto.jpg')
        obj={'id':ident,'nombre':safe,'fecha':datetime.now(timezone.utc).isoformat(),
             'foto':ident+suffix,'trabajo':{k:payload.get(k) for k in ('vector','scale','manual','entidades')}}
        (HISTORIAL/(ident+'.json')).write_text(json.dumps(obj,ensure_ascii=False),encoding='utf8')
        return {'guardado':True,'id':ident,'nombre':safe}
    except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e:
        raise HTTPException(422,str(e)) from e

@app.get('/api/historial/listar')
def historial_listar():
    HISTORIAL.mkdir(parents=True,exist_ok=True)
    found=[]
    for p in sorted(HISTORIAL.glob('*.json'),reverse=True)[:60]:
        try:
            d=json.loads(p.read_text('utf8'))
            found.append({k:d[k] for k in ('id','nombre','fecha')})
        except (ValueError,KeyError):continue
    return {'trabajos':found}

def _historia(ident):
    if not re.fullmatch(r'\d{8}_\d{6}_\d{6}',ident):raise HTTPException(404,'Trabajo no encontrado.')
    ruta=HISTORIAL/(ident+'.json')
    if not ruta.is_file():raise HTTPException(404,'Trabajo no encontrado.')
    return json.loads(ruta.read_text('utf8'))

@app.get('/api/historial/abrir/{ident}')
def historial_abrir(ident:str):
    d=_historia(ident)
    return {k:v for k,v in d.items() if k!='foto'}

@app.get('/api/historial/foto/{ident}')
def historial_foto(ident:str):
    d=_historia(ident)
    p=HISTORIAL/d['foto']
    if not p.is_file() or p.parent!=HISTORIAL:raise HTTPException(404,'Imagen no encontrada.')
    return FileResponse(p,media_type='image/png' if p.suffix=='.png' else 'image/jpeg')
