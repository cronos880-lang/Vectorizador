"""Corrección independiente de ancho X y alto Y del CAD nominal.

El mismo CAD transformado alimenta el STL y el DXF ajustado; el DXF original
conserva sus entidades. Las curvas anisotrópicas se aproximan con polilíneas,
pues un círculo deformado en un solo eje es una elipse, no un CIRCLE.
"""
from __future__ import annotations
import copy
import math
from motor.editor_cad import validar_entidades
from motor.extrusion_stl import _poligonos_solidos, _vertices, PRECISION_STL, MAX_PUNTOS


def _limites(solidos):
    return (min(p.bounds[0] for p in solidos), min(p.bounds[1] for p in solidos),
            max(p.bounds[2] for p in solidos), max(p.bounds[3] for p in solidos))


def corregir_entidades(entidades, objetivo_ancho_mm=None, objetivo_alto_mm=None):
    """Escala X/Y respecto del centro del rectángulo envolvente ORIGINAL.

    None significa eje sin corrección. No tocar las entidades con factores=1
    garantiza que la extrusión antigua siga siendo idéntica cuando no se usa.
    """
    validar_entidades(entidades)
    cfg=PRECISION_STL['normal']
    bbox=_limites(_poligonos_solidos(entidades,cfg['error_cuerda'],cfg['simplificacion']))
    w,h=bbox[2]-bbox[0],bbox[3]-bbox[1]
    if w<0.01 or h<0.01:raise ValueError('La geometría es demasiado pequeña para corregir sus dimensiones.')
    for target,axis in ((objetivo_ancho_mm,'ancho X'),(objetivo_alto_mm,'alto Y')):
        if target is not None and (isinstance(target,bool) or not isinstance(target,(int,float)) or
                                   not math.isfinite(target) or target<=0 or target>20000):
            raise ValueError(f'La medida real de {axis} debe ser positiva y menor o igual a 20000 mm.')
    sx=1.0 if objetivo_ancho_mm is None else float(objetivo_ancho_mm)/w
    sy=1.0 if objetivo_alto_mm is None else float(objetivo_alto_mm)/h
    # Entrada redondeada a milésimas que corresponde al ancho original: no
    # introducimos una microdeformación al cambiar solamente el offset.
    if objetivo_ancho_mm is not None and abs(float(objetivo_ancho_mm)-w)<.00055:sx=1.0
    if objetivo_alto_mm is not None and abs(float(objetivo_alto_mm)-h)<.00055:sy=1.0
    if not .1<=sx<=10 or not .1<=sy<=10:
        raise ValueError('La corrección X/Y supera un factor 10. Revisa la calibración inicial.')
    meta={'ancho_base_mm':w,'alto_base_mm':h,'escala_x':sx,'escala_y':sy}
    if sx==sy==1.0:return entidades,meta
    cx,cy=(bbox[0]+bbox[2])/2,(bbox[1]+bbox[3])/2
    def xy(x,y):return [cx+(float(x)-cx)*sx,cy+(float(y)-cy)*sy]
    isotropico=abs(sx-sy)<1e-12
    salida=[]
    for ent in entidades:
        e=copy.deepcopy(ent)
        t=e['tipo']
        if t=='circle':
            if isotropico:
                e['cx'],e['cy']=xy(e['cx'],e['cy']);e['radio']*=sx
            else:
                # Geometría elíptica precisa dentro de la tolerancia normal STL.
                x,y,r=e['cx'],e['cy'],e['radio']
                n=max(64,4*math.ceil((math.pi/2)*math.sqrt(max(r,1)/(.025*8))))
                n=min(n,MAX_PUNTOS-4)
                e={'id':e['id'],'tipo':'polyline','capa':e['capa'],'cerrada':True,
                   'vertices':[[*xy(x+r*math.cos(2*math.pi*j/n),y+r*math.sin(2*math.pi*j/n)),0.] for j in range(n)]}
        elif t=='rectangle':
            e['a']=xy(*e['a']);e['b']=xy(*e['b'])
        elif t=='polyline':
            if isotropico or all(abs(v[2])<1e-12 for v in e['vertices']):
                e['vertices']=[[ *xy(v[0],v[1]),v[2]] for v in e['vertices']]
            else:
                # Transformar un bulge directamente bajo escalado anisotrópico
                # generaría arcos incorrectos. Primero interpolar el arco real.
                puntos=_vertices(e,.01)
                if len(puntos)>=MAX_PUNTOS:
                    raise ValueError('El contorno curvo tiene demasiados puntos para corregir X/Y.')
                e['vertices']=[[ *xy(x,y),0.] for x,y in puntos]
        else:
            raise ValueError('Solo se corrigen perfiles CAD cerrados compatibles con STL.')
        salida.append(e)
    validar_entidades(salida)
    # Rechazo de intersecciones/contornos inválidos posterior a la transformación.
    _poligonos_solidos(salida,cfg['error_cuerda'],cfg['simplificacion'])
    return salida,meta
