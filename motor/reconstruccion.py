"""Reconstruccion general de contornos y agujeros en geometria 2D.

No contiene coordenadas, dimensiones, reglas, umbrales por foto ni
tratamientos especiales para ninguna pieza. Si no hay evidencia de circulo,
conserva el agujero como polilinea para evitar fabricar geometria.
"""
from __future__ import annotations
import math
import cv2
import numpy as np


def silueta_binaria(roi_gray: np.ndarray, umbral: int) -> np.ndarray:
    """Elimina JPEG/ruido fino sin rellenar orificios ni modificar gran escala."""
    gris=cv2.GaussianBlur(roi_gray,(3,3),0)
    mask=np.uint8(gris < int(umbral))*255
    # Opening minimo elimina pixeles oscuros aislados sin cerrar agujeros.
    return cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((2,2),np.uint8))


def _raw_index(poly, raw):
    """Indices reales de los puntos RDP en el contorno CHAIN_APPROX_NONE."""
    d={tuple(map(int,p)): i for i,p in enumerate(raw)}
    ix=[]
    for p in poly:
        i=d.get(tuple(map(int,p)))
        if i is None: return None
        ix.append(i)
    return ix


def lineas_cad(contorno:np.ndarray, bbox, *, interior:bool=False)->np.ndarray:
    """Reconstruye lineas rectas continuas desde el borde original.

    Elimina quiebros de 1-2 px solo cuando TODOS los pixeles intermedios
    sustentan la cuerda. No depende de la orientación de la pieza. Mantiene
    vertices donde la curva, esquina o muesca supera la tolerancia de imagen.
    La tolerancia esta acotada para no erosionar detalles con fotos grandes.
    """
    raw=np.asarray(contorno,dtype=np.int32).reshape(-1,2)
    if len(raw)<5:
        return raw
    size=max(int(bbox[2]),int(bbox[3]))
    base_eps=float(np.clip(size*.00255,.8,1.7)) if not interior else .85
    poly=cv2.approxPolyDP(raw.reshape(-1,1,2),base_eps,True).reshape(-1,2)
    if len(poly)<=3:
        return poly
    indices=_raw_index(poly,raw)
    if indices is None:
        return poly

    # Desviacion maxima del borde en pixeles, no solo angulo entre segmentos:
    # una recta ligeramente irregular puede fundirse, pero una curva real no.
    tolerance=float(np.clip(size*.0030,1.55,2.20)) if not interior else float(np.clip(size*.0020,1.20,1.65))
    original_area=abs(float(cv2.contourArea(raw)))
    n=len(raw)
    indices=list(indices)
    # Combinar la mejor eliminacion en cada iteracion; se evita depender
    # de donde OpenCV haya situado el inicio del contorno circular.
    for _ in range(max(0,len(indices)-3)):
        if len(indices)<=3:break
        best=None
        for j in range(len(indices)):
            i0=indices[(j-1)%len(indices)]
            i1=indices[j]
            i2=indices[(j+1)%len(indices)]
            a=raw[i0].astype(float);b=raw[i1].astype(float);c=raw[i2].astype(float)
            ab=b-a;bc=c-b;ac=c-a
            chord=float(np.hypot(ac[0],ac[1]))
            if chord<5.0: continue
            # La parte intermedia debe pertenecer al tramo de contorno original.
            if i0<i2:
                segment=raw[i0:i2+1].astype(float)
            else:
                segment=np.vstack((raw[i0:],raw[:i2+1])).astype(float)
            offsets=segment-a
            # Producto vectorial 2D ESCALAR (compatible NumPy 1.x y 2.x).
            errors=np.abs(ac[0]*offsets[:,1]-ac[1]*offsets[:,0])/chord
            max_err=float(np.max(errors))
            if max_err>tolerance: continue
            # Evitar atajos que recorren el contorno hacia atrás, incluso
            # si varios puntos están cerca de una misma linea geométrica.
            projected=(offsets@ac)/(chord*chord)
            if float(projected.min())<-.055 or float(projected.max())>1.055:
                continue
            # Pequeña limitación de área local protege muescas agudas.
            local_area=abs(ab[0]*bc[1]-ab[1]*bc[0])*.5
            if local_area>tolerance*chord*.75:continue
            # Valor menor => fusión más limpia. Desempate determinista.
            score=(max_err/tolerance,local_area/max(chord,1),j)
            if best is None or score<best[0]:best=(score,j)
        if best is None:break
        indices.pop(best[1])
    result=raw[indices]
    # Protección global: no debe cambiar sustancialmente la superficie.
    if original_area>0:
        area=abs(float(cv2.contourArea(result)))
        if abs(area-original_area)/original_area>.035:
            return poly
    return result


def _components_binary(binary:np.ndarray, center):
    n,labels,stats,cents=cv2.connectedComponentsWithStats(np.uint8(binary),8)
    cy,cx=center[1],center[0]
    cy=int(round(cy));cx=int(round(cx))
    if not(0<=cy<binary.shape[0] and 0<=cx<binary.shape[1]):return []
    # Components locally around seed may shift their centroid by perspective/
    # shadows: collect all bright regions with centroids near seed.
    candidates=[]
    for i in range(1,n):
        x,y,w,h,area=stats[i]
        if area<15 or x==0 or y==0 or x+w>=binary.shape[1]-1 or y+h>=binary.shape[0]-1:continue
        dist=np.linalg.norm(cents[i]-np.asarray(center))
        if dist<=max(w,h)*.85+3:
            mask=np.uint8(labels==i)*255
            cnt,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
            if cnt:candidates.append((cnt[0],mask,int(area),float(dist)))
    return candidates


def _circle_from_component(contour, mask, gray, offx,offy, original_center):
    """Clasifica circunferencia por forma, contraste y ajuste radial; no Hough fijo."""
    area=float(cv2.contourArea(contour))
    if area<35 or len(contour)<6:return None
    per=float(cv2.arcLength(contour,True))
    circularity=4*math.pi*area/per**2 if per>0 else 0
    x,y,w,h=cv2.boundingRect(contour)
    if max(w,h)/min(w,h)>1.28 or circularity<.71:return None
    pts=contour.reshape(-1,2).astype(float)
    (cx,cy),r=cv2.minEnclosingCircle(contour)
    # En lugar del radio maximo, ajustar por minimos cuadrados los puntos de borde.
    A=np.column_stack((2*pts[:,0],2*pts[:,1],np.ones(len(pts))))
    b=np.sum(pts**2,axis=1)
    try:
        sol=np.linalg.lstsq(A,b,rcond=None)[0]
        center=sol[:2]
        radius=math.sqrt(max(0., sol[2]+center@center))
    except (ValueError, np.linalg.LinAlgError):return None
    if radius<3:return None
    dist=np.linalg.norm(pts-center,axis=1)
    rms=float(np.sqrt(np.mean((dist-radius)**2)))
    if rms>max(1.65,.105*radius):return None
    if np.linalg.norm(center-np.asarray(original_center))>max(9,2.3*radius):return None
    # Contraste claro-interior / negro-exterior con 64 puntos en circulo,
    # comparacion local en lugar de exigir un gris absoluto.
    absx=float(center[0]+offx);absy=float(center[1]+offy)
    angles=np.linspace(0,2*math.pi,64,endpoint=False)
    def sample(scale):
        xx=np.clip(np.rint(absx+radius*scale*np.cos(angles)).astype(int),0,gray.shape[1]-1)
        yy=np.clip(np.rint(absy+radius*scale*np.sin(angles)).astype(int),0,gray.shape[0]-1)
        return gray[yy,xx].astype(float)
    inner=sample(.55);outer=sample(1.36)
    contrast=inner-outer
    fraction=float(np.mean(contrast>15))
    median=float(np.median(contrast))
    if fraction<.72 or median<22:return None
    return {'centro_px':[round(absx,3),round(absy,3)],
            'radio_px':round(float(radius),3),'contraste':round(median,2),
            'fraccion_borde':round(fraction,3),'metodo':'reconstruccion_v14',
            'error_ajuste_px':round(rms,3)}


def circulo_agujero(gris: np.ndarray,contorno:np.ndarray):
    """Refina el agujero a partir de la foto, no del poligono umbralizado.

    Usa multiples umbrales de contraste local y selecciona la forma con mejor
    soporte, penalizando componentes incompletas y radios subestimados.
    """
    raw=np.asarray(contorno,dtype=np.int32).reshape(-1,2)
    area=abs(cv2.contourArea(raw))
    if len(raw)<5 or area<20:return None
    m=cv2.moments(raw)
    if not m['m00']:return None
    seed=np.array([m['m10']/m['m00'],m['m01']/m['m00']],float)
    xx,yy,ww,hh=cv2.boundingRect(raw)
    radius=max(ww,hh)/2
    half=int(np.clip(max(28,3.3*radius),28,170))
    x0=max(0,int(seed[0]-half));x1=min(gris.shape[1],int(seed[0]+half+1))
    y0=max(0,int(seed[1]-half));y1=min(gris.shape[0],int(seed[1]+half+1))
    crop=cv2.GaussianBlur(gris[y0:y1,x0:x1],(3,3),.65)
    if min(crop.shape)<30:return None
    locseed=seed-[x0,y0]
    cx=int(np.clip(round(locseed[0]),0,crop.shape[1]-1));cy=int(np.clip(round(locseed[1]),0,crop.shape[0]-1))
    # Estimar nivel relativo a la iluminacion en el centro y a la zona oscura.
    core=crop[max(0,cy-2):cy+3,max(0,cx-2):cx+3]
    centerlevel=float(np.percentile(core,60))
    vals=[]
    for ring_r in (max(11,1.8*radius),max(17,2.5*radius)):
        ang=np.linspace(0,2*np.pi,36,endpoint=False)
        xs=np.clip(np.rint(cx+ring_r*np.cos(ang)).astype(int),0,crop.shape[1]-1)
        ys=np.clip(np.rint(cy+ring_r*np.sin(ang)).astype(int),0,crop.shape[0]-1)
        vals.extend(crop[ys,xs].tolist())
    dark=float(np.percentile(vals,25))
    if centerlevel-dark<27:return None
    # Multiple quantiles, evitando escoger solo el nucleo brillante mas pequeno.
    thresholds=np.linspace(dark+.35*(centerlevel-dark),dark+.62*(centerlevel-dark),7)
    found=[]
    for threshold in thresholds:
        mask=np.uint8(crop>threshold)*255
        # Mantener siempre el perfil optico verdadero, sin cerrados que cambien diametros.
        for comp,_,size,offset in _components_binary(mask,locseed):
            result=_circle_from_component(comp,mask,gris,x0,y0,locseed)
            if result is None:continue
            # Mayor radio consistente pero evitando umbral que una otro objeto.
            score=result['fraccion_borde']*3+result['contraste']/70-result['error_ajuste_px']*.24 + result['radio_px']*.012
            found.append((score,result))
    if not found:return None
    # Elegir mediana del radio de los candidatos con ajuste fiable para no
    # favorecer umbral que reduce agujero por sombras en interior.
    found.sort(key=lambda a:a[0],reverse=True)
    top=found[:max(2, math.ceil(len(found)*.5))]
    best=min(top,key=lambda t: abs(t[1]['radio_px']-float(np.median([a[1]['radio_px'] for a in top]))))
    return best[1]
