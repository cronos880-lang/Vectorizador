"""Utilidades complementarias V2.0.15. No modifica el motor de vectorización.

Las advertencias del verificador son geométricas y NO certifican la capacidad
para fabricar un sólido en Onshape.
"""
import math
import numpy as np
import cv2
from motor.reconstruccion import silueta_binaria
from motor.editor_cad import validar_entidades


def detectar_piezas(img, threshold=120, exclusiones=None, max_piezas=12):
    """Candidatas separadas de la plantilla; el usuario confirma el conjunto."""
    h,w=img.shape[:2]
    mask=silueta_binaria(cv2.cvtColor(img,cv2.COLOR_BGR2GRAY),int(threshold))
    if exclusiones:
        for esquinas in exclusiones.values():
            poly=np.asarray(esquinas,float)
            ctr=poly.mean(axis=0)
            cv2.fillConvexPoly(mask,np.rint(ctr+(poly-ctr)*1.25).astype(np.int32),0)
    n, labels, stats, _=cv2.connectedComponentsWithStats(mask,8)
    items=[]
    for i in range(1,n):
        x,y,bw,bh,area=[int(z) for z in stats[i]]
        if area<max(250,h*w*0.00013) or bw<10 or bh<10:continue
        if bw>.75*w or bh>.75*h or area>.4*h*w:continue
        if x<8 or y<8 or x+bw>w-8 or y+bh>h-8:continue
        # Mantener lejos de marcos y números externos: límite amplio, no ubicación fija de pieza.
        if area<1000 and min(bw,bh)<22:continue
        margin=max(12,int(.22*max(bw,bh)))
        box=[max(0,x-margin),max(0,y-margin),min(w,x+bw+margin),min(h,y+bh+margin)]
        items.append({'id':f'pieza-{i}','bbox':[x,y,x+bw,y+bh],'recorte':box,'area_px':area})
    items.sort(key=lambda a:a['area_px'],reverse=True)
    # Evitar una cascada de falsos candidatos (textos, reglas y ruido)
    return items[:max_piezas]


def _dist(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])
def _point(a):return (float(a[0]),float(a[1]))

def _lines_for_entity(e):
    t=e['tipo']
    if t=='line':return [(e['a'],e['b'])]
    if t=='rectangle':
        a,b=e['a'],e['b'];pts=[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]]]
        return list(zip(pts,pts[1:]+pts[:1]))
    if t=='polyline':
        v=e['vertices'];return [(v[i],v[(i+1)%len(v)]) for i in range(len(v) if e['cerrada'] else len(v)-1) if abs(v[i][2])<1e-9]
    return []

def _endpoints(e):
    t=e['tipo']
    if t=='line':return [e['a'],e['b']]
    if t=='polyline' and not e['cerrada']:return [e['vertices'][0],e['vertices'][-1]]
    if t in ('arc','curve'):return [e['a'],e['b']]
    return []

def _intersection(a,b,c,d):
    r=np.subtract(b[:2],a[:2]);s=np.subtract(d[:2],c[:2]);det=float(r[0]*s[1]-r[1]*s[0])
    if abs(det)<1e-10:return None
    q=np.subtract(c[:2],a[:2]);u=(q[0]*s[1]-q[1]*s[0])/det;v=(q[0]*r[1]-q[1]*r[0])/det
    return [float(a[0]+u*r[0]),float(a[1]+u*r[1])],float(u),float(v)

def verificar_plano(entities,tol=0.08):
    validar_entidades(entities)
    warnings=[]
    exact={};endpoint=[];segments=[]
    for e in entities:
        t=e['tipo'];id=e['id']
        if t=='polyline' and not e['cerrada']:warnings.append({'tipo':'abierto','id':id,'mensaje':'Polilínea abierta'})
        if t in ('line','arc','curve'):
            for p in _endpoints(e):endpoint.append((id,_point(p)))
        if t=='polyline':
            for p in _endpoints(e):endpoint.append((id,_point(p)))
        if t=='circle':
            sig=('c',round(e['cx']/tol),round(e['cy']/tol),round(e['radio']/tol))
        else:
            sig=(t,tuple(round(float(z)/tol) for a,b in _lines_for_entity(e) for z in (a[0],a[1],b[0],b[1]))) if t in ('line','rectangle') else None
        if sig is not None:
            if sig in exact:warnings.append({'tipo':'duplicado','id':id,'mensaje':f'Posible duplicado de {exact[sig]}'})
            else:exact[sig]=id
        segments.extend([(id,a,b) for a,b in _lines_for_entity(e)])
    gaps=[]
    # Solo avisar de extremos próximos no coincidentes, no de todos los extremos libres de CAD.
    for i,(ia,a) in enumerate(endpoint):
        for ib,b in endpoint[i+1:]:
            d=_dist(a,b)
            if ia!=ib and 1e-6<d<tol:gaps.append((ia,ib,round(d,4),a,b))
    for ia,ib,d,a,b in gaps[:35]:warnings.append({'tipo':'hueco','id':ia,'mensaje':f'Extremos de {ia} y {ib} a {d} mm', 'puntos':[a,b]})
    crossings=set()
    for i,(ia,a,b) in enumerate(segments):
        for ib,c,d in segments[i+1:]:
            if ia==ib:continue
            inter=_intersection(a,b,c,d)
            if inter is None:continue
            p,u,v=inter
            if p and tol< u*max(_dist(a,b),1e-9) < _dist(a,b)-tol and tol< v*max(_dist(c,d),1e-9) <_dist(c,d)-tol:
                key=tuple(sorted([ia,ib]));
                if key not in crossings:crossings.add(key);warnings.append({'tipo':'cruce','id':ia,'mensaje':f'Cruce entre {ia} y {ib}', 'punto':p})
            if len(warnings)>150:break
        if len(warnings)>150:break
    return {'ok':len(warnings)==0,'avisos':warnings[:150], 'entidades':len(entities),
            'cerradas':sum(e['tipo'] in ('circle','rectangle') or (e['tipo']=='polyline' and e['cerrada']) for e in entities),
            'nota':'Avisos orientativos; no comprueban todas las uniones curvas ni garantizan un sólido en Onshape.'}


def evaluar_bordes(img,vector):
    """Marca para revisión (no corrige geometría) bordes de contraste débil.

    Score interno heurístico, no probabilidad de precisión metrológica.
    """
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    blurred=cv2.GaussianBlur(gray,(5,5),0)
    gx=cv2.Sobel(blurred,cv2.CV_32F,1,0,ksize=3)
    gy=cv2.Sobel(blurred,cv2.CV_32F,0,1,ksize=3)
    mag=cv2.magnitude(gx,gy)
    H,W=mag.shape
    for c in vector.get('contornos',[]):
        if c.get('origen_deteccion')=='recuperado':
            c['revision_recomendada']=True
            c['motivo_revision']='Perforación recuperada: confirmar que no sea reflejo'
            continue
        pts=np.asarray(c.get('borde_px') or c.get('puntos') or [],dtype=float)
        if len(pts)<3:continue
        pts=np.rint(pts[::max(1,len(pts)//240)]).astype(int)
        pts[:,0]=np.clip(pts[:,0],0,W-1);pts[:,1]=np.clip(pts[:,1],0,H-1)
        vals=mag[pts[:,1],pts[:,0]]
        if not len(vals):continue
        # Gradiente Sobel de 5x5; <35 denota borde muy blando o débil.
        weak=float(np.mean(vals<35.))
        if weak>.62:
            c['revision_recomendada']=True
            c['motivo_revision']='Más del 62 % del borde tiene contraste débil'
    return vector
