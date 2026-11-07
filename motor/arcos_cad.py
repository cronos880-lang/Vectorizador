"""Ajuste CAD acotado a los bordes originales, independiente de la pieza.

Crea un DXF LWPOLYLINE con segmentos rectos (bulge=0) y arcos circulares
(bulge=tan(angulo/4)) sin romper el contorno cerrado. No convierte a arcos
las esquinas ni crea curvas con apoyo optico insuficiente.
"""
from __future__ import annotations
import math
import numpy as np
import cv2


def _raw_indices(vertices, original):
    # Cada punto de lineas_cad es un punto real del contorno CHAIN_APPROX_NONE.
    lookup={tuple(map(int,point)):i for i,point in enumerate(original)}
    ids=[]
    for p in vertices:
        key=tuple(map(int,np.rint(p)))
        if key not in lookup:return None
        ids.append(lookup[key])
    if len(set(ids))!=len(ids):return None
    return ids


def _fit_arc_ends(boundary, a, b, tol):
    """Circulo obligado a pasar exactamente por ambos extremos CAD.

    Ajusta el centro sobre la mediatriz, validando TODOS los píxeles originales.
    Devuelve bulge orientado o None. No hay tolerancias basadas en piezas.
    """
    if len(boundary)<8:return None
    delta=b-a
    d=float(np.linalg.norm(delta))
    if d<max(1.3,3.4*tol):return None
    mid=(a+b)*.5
    normal=np.array([-delta[1],delta[0]],float)/d
    vec=boundary-mid
    projection=vec@normal
    denom=2*float(projection@projection)
    if denom<1e-13:return None
    h=float(projection@(np.sum(vec*vec,axis=1)-d*d*.25))/denom
    if not math.isfinite(h):return None
    center=mid+h*normal
    r=math.hypot(.5*d,h)
    if r<.75 or r>10000:return None
    radii=np.linalg.norm(boundary-center,axis=1)
    errors=np.abs(radii-r)
    max_error=float(np.max(errors));rms=float(np.sqrt(np.mean(errors*errors)))
    # Límite duro de separación: nada de curvas de fantasía o atajos notables.
    if max_error>tol or rms>tol*.51:return None
    angles=np.unwrap(np.arctan2(boundary[:,1]-center[1],boundary[:,0]-center[0]))
    sweep=float(angles[-1]-angles[0])
    if not (.95<=abs(sweep)<=3.75):return None
    diffs=np.diff(angles)
    if abs(float(diffs.sum()))<1e-8:return None
    backwards=float(np.abs(diffs[diffs*sweep<0]).sum())
    if backwards>max(.12,abs(sweep)*.23):return None
    sagitta=r*(1-math.cos(abs(sweep)*.5))
    if sagitta<max(.16,1.45*tol):return None
    length=np.linalg.norm(np.diff(boundary,axis=0),axis=1).sum()
    # La escalera raster puede alargar algo los segmentos.
    if float(length)/(r*abs(sweep))>1.53:return None
    bulge=math.tan(sweep*.25)
    if not math.isfinite(bulge) or abs(bulge)>2.0:return None
    return float(bulge),max_error,rms,abs(sweep)


def _max_line_error(boundary,a,b):
    d=b-a; length=float(np.linalg.norm(d))
    if length<1e-7:return math.inf,math.inf
    q=boundary-a
    dist=np.abs(d[0]*q[:,1]-d[1]*q[:,0])/length
    t=q@d/(length*length)
    return float(np.max(dist)),float(max(0.,-np.min(t),np.max(t)-1))


def _arc_samples(a,b,bulge,count=30):
    delta=b-a
    chord=float(np.linalg.norm(delta))
    if chord==0 or abs(bulge)<1e-8:return np.array([a,b])
    alpha=4*math.atan(bulge)
    normal=np.array([-delta[1],delta[0]])/chord
    h=chord/(4*bulge)*(1-bulge*bulge)
    center=(a+b)*.5+h*normal
    radius=float(np.linalg.norm(a-center))
    theta=math.atan2(a[1]-center[1],a[0]-center[0])
    ts=np.linspace(0,alpha,count)
    return np.column_stack((center[0]+radius*np.cos(theta+ts),center[1]+radius*np.sin(theta+ts)))


def ajustar_tramos_cad(vertices_px, raw_px, vertices_mm, raw_mm):
    """Lista de vértices DXF (x,y,bulge) o None si no hay ajuste fiable.

    Los puntos del borde en mm se calculan tras la calibración proyectiva.
    Conserva el mismo orden y extremos y no altera calibración o agujeros.
    """
    vpx=np.asarray(vertices_px,float)
    rpx=np.asarray(raw_px,float)
    p=np.asarray(vertices_mm,float)
    raw=np.asarray(raw_mm,float)
    n=len(p);nr=len(raw)
    if n<5 or n>800 or nr<12 or nr>20000 or len(vpx)!=n or len(rpx)!=nr:return None
    if not (np.isfinite(p).all() and np.isfinite(raw).all()):return None
    ids=_raw_indices(vpx,rpx)
    if ids is None:return None
    # Elegir el inicio en la esquina más pronunciada, para que un arco no
    # quede partido arbitrariamente al cerrar el contorno.
    v0=p-np.roll(p,1,axis=0);v1=np.roll(p,-1,axis=0)-p
    lens=np.linalg.norm(v0,axis=1)*np.linalg.norm(v1,axis=1)
    angles=np.zeros(n,float)
    ok=lens>1e-9
    angles[ok]=np.arccos(np.clip(np.sum(v0*v1,axis=1)[ok]/lens[ok],-1,1))
    start=int(np.argmax(angles))
    p=np.roll(p,-start,axis=0)
    ids=ids[start:]+ids[:start]
    id0=ids[0]
    indices=[(i-id0)%nr for i in ids]
    if indices!=sorted(indices):return None
    ext=np.vstack((raw[id0:],raw[:id0+1]))
    ext_px=np.vstack((rpx[id0:],rpx[:id0+1]))
    pts=np.vstack((p,p[0]))
    positions=indices+[nr]

    # Convertir pixel a mm cerca de la pieza: 1-2px de aliasing son visibles,
    # pero no se permite desplazar más de 0.22 mm el borde CAD.
    dx=np.linalg.norm(np.diff(raw,axis=0),axis=1)
    dx=dx[(dx>1e-8)&(dx<2)]
    step=float(np.median(dx)) if len(dx) else .10
    tol=float(np.clip(1.3*step,.09,.33))

    penalty=[math.inf]*(n+1)
    nxt=[None]*n
    penalty[n]=0
    for i in range(n-1,-1,-1):
        best=(math.inf,None)
        for j in range(i+1,min(n,i+24)+1):
            if j<n and positions[j]-positions[i]<2:continue
            a,b=pts[i],pts[j]
            block=ext[positions[i]:positions[j]+1]
            if len(block)<2:continue
            # Línea que conserva el borde: en ausencia de otra cosa hay
            # segmento original válido incluso con ruido subpíxel.
            if j==i+1:
                err,over=_max_line_error(block,a,b)
                score=1.0+min(err/tol,4)*.06+penalty[j]
                if score<best[0]:best=(score,(j,0.0))
            else:
                err,over=_max_line_error(block,a,b)
                if err<=tol and over<.06:
                    score=1.0+.20*(err/tol)+penalty[j]
                    if score<best[0]:best=(score,(j,0.0))
            if j>=i+2:
                result=_fit_arc_ends(block,a,b,tol)
                if result:
                    bulge,max_error,rms,sweep=result
                    # Priorizar una primitiva circular cuando varios lados
                    # de un polígono aproximan realmente un mismo arco.
                    score=1.35+.28*(rms/tol)+.11*(max_error/tol)+penalty[j]
                    if score<best[0]:best=(score,(j,bulge))
        if best[1] is None:return None
        penalty[i]=best[0];nxt[i]=best[1]
    segments=[]
    i=0
    while i<n:
        j,bulge=nxt[i]
        segments.append((i,j,bulge))
        i=j
    if not any(abs(b)>.001 for _,_,b in segments):return None
    output=[]
    ring=[]
    for i,j,bulge in segments:
        a,b=pts[i],pts[j]
        output.append((float(a[0]),float(a[1]),float(bulge)))
        ring.append(_arc_samples(a,b,bulge,18 if abs(bulge)>.001 else 2))
    represented=np.vstack(ring)
    area_fit=abs(float(cv2.contourArea(represented.astype(np.float32))))
    area_raw=abs(float(cv2.contourArea(raw.astype(np.float32))))
    # Tolerancia global de área 1.8% y desviación de dimensiones 0.25 mm.
    if area_raw>1 and abs(area_fit-area_raw)>max(.35,area_raw*.018):return None
    aabb_raw=np.array([raw.min(axis=0),raw.max(axis=0)])
    aabb_fit=np.array([represented.min(axis=0),represented.max(axis=0)])
    if np.max(np.abs(aabb_raw-aabb_fit))>.26:return None
    return output
