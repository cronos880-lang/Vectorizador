"""Entidades CAD 2D para edición antes de DXF; no modifica el vectorizador V1.77."""
from __future__ import annotations
import io
import math
import numpy as np
import ezdxf
from motor.exportar import geometria

MAX_ENTIDADES = 1000
MAX_VERTICES = 40000
MAX_COORD = 20000


def documento_inicial(vector, sx, sy, afin=None, proyectiva=None, sin_escala=False):
    # Reutilizar exactamente el mismo motor geométrico que V1.77.
    piezas, resumen = geometria(vector, 1., 1.) if sin_escala else geometria(vector,sx,sy,afin,proyectiva)
    entidades=[]
    for i,(parte, clase, coords) in enumerate(piezas):
        capa = 'CONTORNO_EXTERIOR' if parte=='exterior' else 'AGUJEROS'
        if clase == 'circle':
            centro,radio=coords
            entidades.append({'id':f'original-{i}', 'tipo':'circle','capa':capa,
                              'cx':float(centro[0]),'cy':float(centro[1]),'radio':float(radio)})
        else:
            p = np.asarray(coords,dtype=float)
            if p.ndim != 2 or p.shape[1] not in (2,3):
                raise ValueError('Geometría CAD no válida.')
            vertices=[[float(row[0]),float(row[1]),float(row[2]) if len(row)>2 else 0.] for row in p]
            entidades.append({'id':f'original-{i}','tipo':'polyline','capa':capa,
                              'cerrada':True,'vertices':vertices})
    validar_entidades(entidades)
    return {'entidades':entidades, 'unidades':'px' if sin_escala else 'mm', 'resumen':resumen}


def _numero(x):
    if isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or abs(x)>MAX_COORD:
        raise ValueError('Coordenada o dimensión CAD no válida.')
    return float(x)


def _punto(p):
    if not isinstance(p,(list,tuple)) or len(p)!=2:
        raise ValueError('Punto CAD incorrecto.')
    return [_numero(p[0]),_numero(p[1])]



def geometria_arco_3p(a, paso, b):
    """Centro/radio y ángulos DXF CCW del arco que pasa por los tres puntos.

    Si el punto de paso está en el sentido horario de inicio a fin, se invierten
    inicio/fin para respetar la convención CCW de la entidad DXF ARC.
    """
    p1=_punto(a); pm=_punto(paso); p3=_punto(b)
    ux,uy=pm[0]-p1[0],pm[1]-p1[1]
    vx,vy=p3[0]-p1[0],p3[1]-p1[1]
    d=2*(ux*vy-uy*vx)
    max_side=max(math.hypot(ux,uy), math.hypot(vx,vy), math.hypot(pm[0]-p3[0], pm[1]-p3[1]))
    if max_side<.001 or abs(d)<=2e-6*max_side*max_side:
        raise ValueError('Los tres puntos del arco deben ser distintos y no estar alineados.')
    u2=ux*ux+uy*uy;v2=vx*vx+vy*vy
    cx=p1[0]+(u2*vy-v2*uy)/d
    cy=p1[1]+(v2*ux-u2*vx)/d
    radius=math.hypot(p1[0]-cx,p1[1]-cy)
    if not all(map(math.isfinite,(cx,cy,radius))) or not .01<=radius<=10000:
        raise ValueError('Arco con radio fuera de rango.')
    if abs(cx)>MAX_COORD or abs(cy)>MAX_COORD:
        raise ValueError('Centro del arco fuera de rango.')
    def ang(p):return math.degrees(math.atan2(p[1]-cy,p[0]-cx))%360
    start,through,end=ang(p1),ang(pm),ang(p3)
    # Si el punto medio cae en el arco antihorario inicio->fin,
    # conservarlo. De otro modo recorrer fin->inicio en CCW.
    if (through-start)%360 < (end-start)%360:
        return cx,cy,radius,start,end
    return cx,cy,radius,end,start

def validar_entidades(entidades):
    if not isinstance(entidades,list) or len(entidades)>MAX_ENTIDADES:
        raise ValueError('Número de entidades CAD no válido.')
    vistas=set()
    total=0
    for ent in entidades:
        if not isinstance(ent,dict):raise ValueError('Entidad CAD no válida.')
        ident=ent.get('id')
        if not isinstance(ident,str) or not 0<len(ident)<=120 or ident in vistas:
            raise ValueError('Identificador CAD duplicado o inválido.')
        vistas.add(ident)
        if ent.get('capa') not in {'CONTORNO_EXTERIOR','AGUJEROS','DIBUJO'}:
            raise ValueError('Capa de geometría desconocida.')
        tipo=ent.get('tipo')
        if tipo=='circle':
            _numero(ent.get('cx'));_numero(ent.get('cy'))
            r=_numero(ent.get('radio'))
            if not .01<=r<=10000:raise ValueError('Radio CAD fuera de rango.')
        elif tipo=='curve':
            a=_punto(ent.get('a'));c1=_punto(ent.get('c1'));c2=_punto(ent.get('c2'));b=_punto(ent.get('b'))
            if math.dist(a,b)<.001:raise ValueError('Curva con extremos coincidentes.')
        elif tipo=='arc':
            geometria_arco_3p(ent.get('a'),ent.get('paso'),ent.get('b'))
        elif tipo=='line':
            a=_punto(ent.get('a'));b=_punto(ent.get('b'))
            if math.dist(a,b)<.001:raise ValueError('Línea de longitud nula.')
        elif tipo=='rectangle':
            a=_punto(ent.get('a'));b=_punto(ent.get('b'))
            if abs(a[0]-b[0])<.001 or abs(a[1]-b[1])<.001:
                raise ValueError('Rectángulo de tamaño nulo.')
        elif tipo=='polyline':
            vs=ent.get('vertices')
            cerrada=ent.get('cerrada')
            if not isinstance(vs,list) or len(vs) < (3 if cerrada else 2) or len(vs)>MAX_VERTICES:
                raise ValueError('Polilínea de tamaño incorrecto.')
            if not isinstance(cerrada,bool):raise ValueError('Cierre de polilínea incorrecto.')
            total+=len(vs)
            for pt in vs:
                if not isinstance(pt,(list,tuple)) or len(pt)!=3:
                    raise ValueError('Vértice CAD inválido.')
                _numero(pt[0]);_numero(pt[1]);b=_numero(pt[2])
                if abs(b)>20:raise ValueError('Arco CAD demasiado pronunciado.')
        else:raise ValueError('Tipo de entidad CAD desconocido.')
    if total>MAX_VERTICES:raise ValueError('Demasiados vértices CAD.')


def dxf_editado(entidades, sin_escala=False):
    validar_entidades(entidades)
    doc=ezdxf.new('R2010');doc.units=0 if sin_escala else 4
    doc.header['$INSUNITS']=0 if sin_escala else 4
    for layer,color in [('CONTORNO_EXTERIOR',7),('AGUJEROS',3),('DIBUJO',5)]:
        doc.layers.new(layer,dxfattribs={'color':color})
    m=doc.modelspace()
    for ent in entidades:
        layer=ent['capa'];kind=ent['tipo']
        if kind=='circle':
            m.add_circle((ent['cx'],ent['cy']),ent['radio'],dxfattribs={'layer':layer})
        elif kind=='curve':
            puntos=[(*ent[name],0.0) for name in ('a','c1','c2','b')]
            m.add_open_spline(puntos,degree=3,knots=[0,0,0,0,1,1,1,1],dxfattribs={'layer':layer})
        elif kind=='arc':
            cx,cy,r,aa,ab=geometria_arco_3p(ent['a'],ent['paso'],ent['b'])
            m.add_arc((cx,cy),r,start_angle=aa,end_angle=ab,
                      dxfattribs={'layer':layer})
        elif kind=='line':
            m.add_line(ent['a'],ent['b'],dxfattribs={'layer':layer})
        elif kind=='rectangle':
            a,b=ent['a'],ent['b']
            m.add_lwpolyline([(a[0],a[1]),(b[0],a[1]),(b[0],b[1]),(a[0],b[1])],close=True,dxfattribs={'layer':layer})
        elif kind=='polyline':
            m.add_lwpolyline(ent['vertices'],format='xyb',close=ent['cerrada'],dxfattribs={'layer':layer})
    if doc.audit().has_errors:raise ValueError('El DXF editado contiene errores.')
    f=io.StringIO();doc.write(f)
    return f.getvalue().encode('utf-8')
