"""Detecta cápsulas CAD verdaderas a partir de muestras del borde en mm.

Ajusta dos tramos paralelos tangentes a dos arcos semicirculares. Rechaza
candidatos que no estén apoyados por todo el contorno original: no reemplaza
ranuras de radios pequeños, contornos dañados o huecos irregulares por una
cápsula ideal. No contiene umbrales para ningún archivo ni pieza particular.
"""
from __future__ import annotations
import math
import numpy as np
import cv2


def _distancias(points, prm):
    cx, cy, angle, half, radius=prm
    co,si=math.cos(angle),math.sin(angle)
    d=points-np.array((cx,cy))
    u=d[:,0]*co+d[:,1]*si
    v=-d[:,0]*si+d[:,1]*co
    return np.hypot(np.maximum(np.abs(u)-half,0.0),v)-radius


def _inicio(p):
    center=np.mean(p,axis=0)
    val,evec=np.linalg.eigh(np.cov((p-center).T))
    order=np.argsort(val)[::-1]
    if val[order[1]]<1e-8 or val[order[0]]/val[order[1]]<1.65:return None
    u=evec[:,order[0]]
    angle=float(math.atan2(u[1],u[0]))
    v=np.array((-u[1],u[0]))
    coord=(p-center)@u
    cross=(p-center)@v
    # Percentiles limitan el sesgo de una marca aislada.
    r=float((np.percentile(cross,97)-np.percentile(cross,3))*.5)
    half=float((np.percentile(coord,99)-np.percentile(coord,1))*.5-r)
    center=center+u*float((np.percentile(coord,99)+np.percentile(coord,1))*.5)
    center=center+v*float((np.percentile(cross,97)+np.percentile(cross,3))*.5)
    if r<.3 or half<r*.36:return None
    return np.array((center[0],center[1],angle,half,r),float)


def ajustar_capsula(borde_mm, tolerancia_mm=.28):
    """(coords LWPOLYLINE xybulge, calidad) o None.

    Se necesita contorno denso; se verifica no solo RMS sino error máximo,
    rectitud, área y envolvente antes de reemplazar el DXF existente.
    """
    p=np.asarray(borde_mm,dtype=float)
    if p.ndim!=2 or p.shape[1]!=2 or not(36<=len(p)<=9000) or not np.isfinite(p).all():return None
    q=_inicio(p)
    if q is None:return None
    first=q.copy()
    # Optimización local Gauss-Newton amortiguada sin dependencias externas.
    lam=.10
    for _ in range(26):
        d=_distancias(p,q)
        H=np.empty((len(p),5),float)
        steps=np.array((.0008,.0008,.00008,.0008,.0008))
        for i in range(5):
            next_q=q.copy();next_q[i]+=steps[i]
            H[:,i]=(_distancias(p,next_q)-d)/steps[i]
        # Huber: ruido leve no desplaza la pieza.
        weights=np.minimum(1.,.16/np.maximum(np.abs(d),1e-9))
        HW=H*weights[:,None]
        A=H.T@HW
        b=H.T@(weights*d)
        try: delta=np.linalg.solve(A+lam*np.eye(5),-b)
        except np.linalg.LinAlgError:return None
        delta=np.clip(delta,[-.9,-.9,-.16,-1.,-.9],[.9,.9,.16,1.,.9])
        candidate=q+delta
        if (candidate[3]<=candidate[4]*.32 or candidate[4]<=.3 or
            abs(candidate[2]-first[2])>.35 or
            np.linalg.norm(candidate[:2]-first[:2])>first[4]*.9):
            lam=min(lam*3,1e7);continue
        before=float(np.mean(np.minimum(d*d,.16*.16)))
        new=_distancias(p,candidate)
        after=float(np.mean(np.minimum(new*new,.16*.16)))
        if after<before:
            q=candidate;lam=max(lam*.55,1e-6)
            if np.max(np.abs(delta))<1e-5:break
        else:lam=min(lam*4,1e8)
    deviations=np.abs(_distancias(p,q))
    maximum=float(np.max(deviations))
    rms=float(np.sqrt(np.mean(deviations**2)))
    tol=float(np.clip(tolerancia_mm,.07,.30))
    # Dos dimensiones y zona observada: garantiza que no es una forma cualquiera.
    if maximum>tol or rms>tol*.43:return None
    cx,cy,theta,h,r=q
    if h<r*.38:return None
    # Comprobación de cobertura: debe haber puntos de ambos lados rectos
    # y de ambos extremos curvos, evitando un arco accidental sobre un borde.
    co,si=math.cos(theta),math.sin(theta)
    axis=np.array((co,si));normal=np.array((-si,co))
    pr=(p-q[:2])@axis
    cross=(p-q[:2])@normal
    if (sum((pr>h*.99)&(pr<h+r*.9))<5 or sum((pr<-h*.99)&(pr>-h-r*.9))<5 or
        sum((np.abs(pr)<h*.8)&(cross>r*.77))<5 or
        sum((np.abs(pr)<h*.8)&(cross<-r*.77))<5):return None
    # Modelo de cuatro vértices, dos lados perfectamente rectos y dos
    # arcos semicirculares reales; bulge +/-1 = semicírculo CAD.
    center=np.array((cx,cy))
    a=center-h*axis+r*normal
    b=center+h*axis+r*normal
    c=center+h*axis-r*normal
    d=center-h*axis-r*normal
    capsule=[(float(a[0]),float(a[1]),0.),
             (float(b[0]),float(b[1]),-1.),
             (float(c[0]),float(c[1]),0.),
             (float(d[0]),float(d[1]),-1.)]
    # Área modelo y área observada: verifica además concordancia topológica.
    raw_area=abs(float(cv2.contourArea(p.astype(np.float32))))
    area=4*h*r+math.pi*r*r
    if raw_area<1 or abs(area-raw_area)>max(.26,raw_area*.022):return None
    return capsule, {'max_error_mm':round(maximum,3),'rms_mm':round(rms,3),
                     'radio_mm':round(float(r),3),'longitud_mm':round(float(2*(h+r)),3)}
