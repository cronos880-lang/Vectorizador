"""Motor V1.1: referencia V0.1 intacta y modo de afinado conservador.

La calibración afín opcional compensa inclinación/cizalla en la fotografía,
pero NO es una rectificación de perspectiva proyectiva ni prueba metrológica.
"""
from __future__ import annotations
import io
import base64
from typing import Any
import numpy as np
import cv2
from motor.reconstruccion import circulo_agujero, lineas_cad, silueta_binaria
from motor.afinado_v13 import contorno_ajustado

MAX_PIXELS = 32_000_000


def decodificar(foto: bytes) -> np.ndarray:
    raw = np.frombuffer(foto, dtype=np.uint8)
    imagen = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError('No se ha podido leer la foto. Utiliza JPG o PNG.')
    alto, ancho = imagen.shape[:2]
    if alto * ancho > MAX_PIXELS or min(alto, ancho) < 150:
        raise ValueError('Dimensiones de imagen fuera de rango.')
    return imagen


def _lineas_regla(gris: np.ndarray):
    h, w = gris.shape
    bordes = cv2.Canny(gris, 55, 150)
    min_len = max(20, round(min(w, h) * 0.05))
    detectadas = cv2.HoughLinesP(bordes, 1, np.pi/180, threshold=36,
                                minLineLength=min_len, maxLineGap=5)
    # No se extrapolan escalas si no hay repeticiones estables.
    ys, xs = [], []
    if detectadas is None:
        return ys, xs
    for linea in detectadas[:, 0]:
        x1, y1, x2, y2 = map(int, linea)
        largo_h, largo_v = abs(x1-x2), abs(y1-y2)
        if (abs(y1-y2) <= 3 and largo_h >= max(36, int(0.059*w))
            and min(x1,x2) > .71*w and max(x1,x2) < .90*w
            and 0.015*h < (y1+y2)/2 < .79*h):
            ys.append((y1+y2)/2)
        if (abs(x1-x2) <= 3 and largo_v >= max(36, int(.032*h))
            and .75*h < min(y1,y2) < .9*h and max(y1,y2) < .90*h
            and .015*w < (x1+x2)/2 < .78*w):
            xs.append((x1+x2)/2)
    return ys, xs


def _estimar_periodo(valores):
    """Inferir paso de 1 cm de líneas principales sin confundir múltiplos."""
    valores = sorted(set(round(float(v)) for v in valores))
    # Hough puede devolver ambos bordes del mismo trazo.
    grupos = []
    for v in valores:
        if grupos and v-grupos[-1][-1] <= 4:
            grupos[-1].append(v)
        else:
            grupos.append([v])
    marcas = np.array([np.median(g) for g in grupos], dtype=float)
    if len(marcas) < 4:
        return None
    deltas = np.diff(marcas)
    # Marcas principales de cm pueden estar separadas por 1,2,3... cm.
    propuestas = []
    for d in deltas:
        for n in (1,2,3,4):
            px = d/n
            if 28 <= px <= 220:
                propuestas.append(px)
    if not propuestas:
        return None
    mejor = (0,None)
    for p in propuestas:
        errores = []
        aciertos = 0
        for i in range(len(marcas)):
            for j in range(i+1,len(marcas)):
                d = marcas[j]-marcas[i]
                k = round(d/p)
                if k < 1 or k > 30: continue
                e=abs(d-k*p)
                if e < max(2.0, p*.035):
                    aciertos += 1
                    errores.append(e)
        # Penalizar submúltiplos (5mm) buscando la mayor cadencia plausible
        score = aciertos + .002*p - np.median(errores)*.08 if errores else 0
        if score > mejor[0]: mejor = (score, p)
    if mejor[0] < 4:
        return None
    periodo = float(mejor[1])
    # estimación más precisa usando todas las diferencias consistentes
    ajustadas=[]
    for i in range(len(marcas)):
        for j in range(i+1,len(marcas)):
            delta=marcas[j]-marcas[i]
            k=round(delta/periodo)
            if 1<=k<=30 and abs(delta-k*periodo)<max(2.,periodo*.035):
                ajustadas.append(delta/k)
    if len(ajustadas) < 4: return None
    p=float(np.median(ajustadas))
    return round(p/10,4) # px/mm


def estimar_escala(imagen: np.ndarray) -> dict[str,Any]:
    gris=cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    ys,xs=_lineas_regla(gris)
    sy=_estimar_periodo(ys)
    sx=_estimar_periodo(xs)
    # El cálculo es orientativo en V0.1: no corrige perspectiva de la cámara.
    return {'px_mm_x': sx,'px_mm_y': sy,
            'metodo':'reglas_detectadas' if (sx and sy) else 'incompleto',
            'advertencia':'Escala estimada en la fotografía; sin rectificación de perspectiva.'}


def extraer_contornos(imagen: np.ndarray, umbral:int=120, modo:str="precision", recorte=None, exclusiones=None)->dict[str,Any]:
    """Detección de una pieza aislada con orificios y contorno exterior cerrado.

    El modo referencia reproduce la V0.1, sin alteraciones. En precisión se
    detectan los huecos circulares por imagen y se conservan formas complejas
    como polilíneas sin inventar caras ni rectas perfectas.
    """
    if modo not in ('referencia','precision'):
        raise ValueError('Modo de vectorización no reconocido.')
    if not 40<=umbral<=220:raise ValueError('Umbral fuera de rango.')
    h,w=imagen.shape[:2]
    gray=cv2.cvtColor(imagen,cv2.COLOR_BGR2GRAY)
    if recorte is not None and modo!='referencia':
        if not isinstance(recorte,(list,tuple)) or len(recorte)!=4:raise ValueError('Recorte inválido.')
        try: x0,y0,x1,y1=(int(float(v)) for v in recorte)
        except (ValueError,TypeError) as e: raise ValueError('Recorte inválido.') from e
        if not (0<=x0<x1<=w and 0<=y0<y1<=h and x1-x0>=25 and y1-y0>=25):
            raise ValueError('El recorte debe cubrir una región válida de la foto.')
    elif modo=='referencia':
        x0,y0,x1,y1=0,0,int(.75*w),int(.77*h)
    else:
        # Área amplia: evita el sesgo de tener que colocar siempre las piezas
        # en el cuadrante superior izquierdo de la hoja.
        x0,y0,x1,y1=0,0,int(.97*w),int(.95*h)
    roi=gray[y0:y1,x0:x1]
    mask=silueta_binaria(roi,umbral)
    if exclusiones:
        # Marcadores V2: no confundirlos con piezas negras. Se excluyen solo
        # cuando realmente se han identificado sus cuatro esquinas ArUco.
        for esquinas in exclusiones.values():
            poly=np.rint(np.asarray(esquinas,float)-[x0,y0]).astype(np.int32)
            centro=poly.mean(axis=0)
            poly=np.rint(centro+(poly-centro)*1.09).astype(np.int32)
            cv2.fillConvexPoly(mask,poly,0)
    total,etiquetas,stats,_=cv2.connectedComponentsWithStats(mask,8)
    candidatos=[]
    for i in range(1,total):
        x,y,ww,hh,area=map(int,stats[i])
        if (area>=max(150,h*w*.0001) and
            x>2 and y>2 and x+ww<roi.shape[1]-2 and y+hh<roi.shape[0]-2 and
            (modo=='referencia' or
             (ww<roi.shape[1]*.90 and hh<roi.shape[0]*.9 and
              ww>6 and hh>6))):
            candidatos.append((area,i,x,y,ww,hh))
    if not candidatos:
        raise ValueError('No se encontró una pieza negra aislada. Delimita la pieza o ajusta el umbral.')
    area,etiqueta,x,y,ww,hh=max(candidatos)
    select=np.uint8(etiquetas==etiqueta)*255
    if modo=='precision':
        # Filtro mínimo: reduce ruido JPG sin sellar orificios.
        limpia=cv2.medianBlur(select,3)
        cb,_=cv2.findContours(select,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
        ca,_=cv2.findContours(limpia,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
        if len(ca)>=len(cb):select=limpia
    contours,hierarchy=cv2.findContours(select,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    # Muestras originales CHAIN_APPROX_NONE: solo se usan al reconstruir arcos
    # durante la exportación, después de aplicar la calibración en mm.
    dense,_=cv2.findContours(select,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
    salida=[]
    area_limite_agujero=max(22.0,float(area)*.001)
    if hierarchy is not None:
        for i,c in enumerate(contours):
            a=abs(cv2.contourArea(c))
            if a<15:continue
            interior=int(hierarchy[0,i,3])!=-1
            if interior and modo=='precision' and a<area_limite_agujero:continue
            if interior and modo=='precision':
                # Un brillo unido casi al borde exterior no es una perforación
                # fiable: rechazar interiores con pared aparente menor de 2.5px.
                # Criterio topológico general, independiente de la pieza.
                padre=int(hierarchy[0,i,3])
                pared=min(cv2.pointPolygonTest(contours[padre],
                         (float(pt[0][0]),float(pt[0][1])),True) for pt in c)
                if pared<2.5:continue
            if modo=='referencia':
                poly=cv2.approxPolyDP(c,.65,True).reshape(-1,2)
            else:
                poly=lineas_cad(c,(x,y,ww,hh),interior=interior)
            if len(poly)<3:continue
            puntos=poly.astype(float)+[x0,y0]
            item={'tipo':'interior' if interior else 'exterior',
                  'puntos':puntos.tolist(),'area_px2':round(a,2)}
            if modo=='precision' and i<len(dense) and abs(cv2.contourArea(dense[i])-cv2.contourArea(c))<.01:
                # No inventar puntos: el borde sirve para evaluar la desviación
                # del ajuste de círculos y arcos.
                item['borde_px']=(dense[i].reshape(-1,2).astype(float)+[x0,y0]).tolist()
            if modo=='precision' and interior:
                c_global=c+np.array([[[x0,y0]]],dtype=np.int32)
                circ=circulo_agujero(gray,c_global)
                if circ:
                    item['circulo']=circ
            salida.append(item)
    if not salida:raise ValueError('No se ha podido vectorizar el contorno.')
    # La bbox es la de la máscara, no la del círculo reconocido.
    # Vista intermedia binaria REAL de la pieza seleccionada, sin reglas,
    # sombras ni textura. El DXF sigue partiendo del contorno detectado.
    silueta=np.full((h,w),255,dtype=np.uint8)
    for item in salida:
        if item['tipo']=='exterior':
            cv2.fillPoly(silueta,[np.rint(item['puntos']).astype(np.int32)],0)
    for item in salida:
        if item['tipo']=='interior':
            if item.get('circulo'):
                circ=item['circulo']
                centro=tuple(np.rint(circ['centro_px']).astype(int))
                cv2.circle(silueta,centro,max(1,int(round(circ['radio_px']))),255,-1)
            else:
                cv2.fillPoly(silueta,[np.rint(item['puntos']).astype(np.int32)],255)
    ok,buffer=cv2.imencode('.png',silueta,[cv2.IMWRITE_PNG_COMPRESSION,5])
    preview='data:image/png;base64,'+base64.b64encode(buffer).decode('ascii') if ok else None
    return {'contornos':salida,'bbox_px':[x+x0,y+y0,ww,hh],
            'silueta_png':preview,
            'pixeles_pieza':int(area),'umbral':int(umbral),'modo':modo,
            'recorte':recorte,'ancho_imagen':w,'alto_imagen':h,
            'aviso':'Foto: la precisión dimensional real sigue sin estar verificada.'}
