"""Rutinas ópticas conservadoras y metrología proyectiva para DXF.

La imagen no contiene profundidad ni parámetros de lente: ninguna de estas
rutinas puede certificar tolerancias dimensionales sin una medida física.
"""
from __future__ import annotations
import math
import cv2
import numpy as np


def detectar_circulo_agujero(gris:np.ndarray,contorno:np.ndarray):
    """Reconoce únicamente agujeros aproximadamente redondos de alto contraste.

    Utiliza la imagen, no los vértices simplificados. Un círculo no fiable
    permanece como polilínea, sin inventar mecanizados.
    """
    if len(contorno)<5 or cv2.contourArea(contorno)<20:
        return None
    x,y,w,h=cv2.boundingRect(contorno)
    if not 5<=w<=75 or not 5<=h<=75 or max(w,h)/min(w,h)>1.65:
        return None
    mm=cv2.moments(contorno)
    if mm['m00']<=0: return None
    center=np.array([mm['m10']/mm['m00'],mm['m01']/mm['m00']],float)
    margin=24
    x0=max(0,int(center[0]-margin));y0=max(0,int(center[1]-margin))
    x1=min(gris.shape[1],int(center[0]+margin+1));y1=min(gris.shape[0],int(center[1]+margin+1))
    roi=cv2.GaussianBlur(gris[y0:y1,x0:x1],(5,5),1.0)
    lo=max(3,int(min(w,h)*0.38));hi=min(30,int(max(w,h)*1.15))
    circles=cv2.HoughCircles(roi,cv2.HOUGH_GRADIENT,dp=1,minDist=10,
                            param1=80,param2=13,minRadius=lo,maxRadius=hi)
    if circles is None: return None
    mejor=None
    for a,b,r in circles[0]:
        cx=float(a+x0);cy=float(b+y0);r=float(r)
        if math.hypot(cx-center[0],cy-center[1])>max(4.,r*.65):continue
        # Contraste de círculo completo, descartando manchas locales o
        # redondeos que corresponderían a una esquina interior.
        angles=np.linspace(0,2*np.pi,36,endpoint=False)
        rad_in=r*.55;rad_out=r*1.40
        ii_x=np.clip(np.rint(cx+rad_in*np.cos(angles)).astype(int),0,gris.shape[1]-1)
        ii_y=np.clip(np.rint(cy+rad_in*np.sin(angles)).astype(int),0,gris.shape[0]-1)
        oo_x=np.clip(np.rint(cx+rad_out*np.cos(angles)).astype(int),0,gris.shape[1]-1)
        oo_y=np.clip(np.rint(cy+rad_out*np.sin(angles)).astype(int),0,gris.shape[0]-1)
        contrastes=gris[ii_y,ii_x].astype(float)-gris[oo_y,oo_x].astype(float)
        median=float(np.median(contrastes))
        prop=float(np.mean(contrastes>15))
        if median<32 or prop<.79:continue
        valor=median + prop*10 - math.hypot(cx-center[0],cy-center[1])*1.5
        if mejor is None or valor>mejor[0]:mejor=(valor,[cx,cy],r,median,prop)
    if mejor is None:
        # Fallback por ajuste de elipse SOLO para orificios suficientemente
        # redondos y contrastados. No convertir rayaduras en agujeros CAD.
        per=cv2.arcLength(contorno,True)
        circ=4*math.pi*cv2.contourArea(contorno)/(per*per) if per>0 else 0.
        if (len(contorno)<5 or cv2.contourArea(contorno)<90 or circ<.74):
            return None
        (ex,ey),(ma,mb),ang=cv2.fitEllipse(contorno)
        if min(ma,mb)<=0 or max(ma,mb)/min(ma,mb)>1.31:
            return None
        r=(ma+mb)/4.
        theta=np.linspace(0,2*np.pi,36,endpoint=False)
        ix=np.clip(np.rint(ex+.44*r*np.cos(theta)).astype(int),0,gris.shape[1]-1)
        iy=np.clip(np.rint(ey+.44*r*np.sin(theta)).astype(int),0,gris.shape[0]-1)
        ox=np.clip(np.rint(ex+1.45*r*np.cos(theta)).astype(int),0,gris.shape[1]-1)
        oy=np.clip(np.rint(ey+1.45*r*np.sin(theta)).astype(int),0,gris.shape[0]-1)
        diff=gris[iy,ix].astype(float)-gris[oy,ox].astype(float)
        if np.median(diff)<20 or np.mean(diff>10)<.76:return None
        return {'centro_px':[round(float(ex),3),round(float(ey),3)],
                'radio_px':round(float(r),3),'contraste':round(float(np.median(diff)),1),
                'fraccion_borde':round(float(np.mean(diff>10)),2),'metodo':'ajuste_foto'}
    return {'centro_px':mejor[1],'radio_px':round(mejor[2],3),
            'contraste':round(mejor[3],1),'fraccion_borde':round(mejor[4],2)}


def homografia_reglas(calibracion:dict):
    """Calibración en mm con 3 marcas en cada una de dos reglas perpendiculares.

    Orden: x1,x2,x3 en regla inferior (positivo hacia izquierda) y
    y1,y2,y3 en regla derecha (positivo hacia arriba).
    Se usa SVD DLT normalizada por OpenCV sobre seis puntos.
    """
    try:
        pts=np.asarray(calibracion['puntos'],dtype=np.float64)
        xs=np.asarray(calibracion['mm_x'],dtype=np.float64)
        ys=np.asarray(calibracion['mm_y'],dtype=np.float64)
    except (KeyError,TypeError,ValueError) as e:
        raise ValueError('Calibración proyectiva incompleta.') from e
    if (pts.shape!=(6,2) or xs.shape!=(3,) or ys.shape!=(3,) or
        not all(np.isfinite(a).all() for a in (pts,xs,ys)) or
        np.any(xs<5) or np.any(xs>200) or np.any(ys<5) or np.any(ys>280) or
        not (xs[0]<xs[1]<xs[2] and ys[0]<ys[1]<ys[2]) or
        np.linalg.norm(pts[0]-pts[2])<30 or np.linalg.norm(pts[3]-pts[5])<30):
        raise ValueError('Marcas inválidas: deben ser seis, ordenadas y estar separadas.')
    if not (np.all(np.diff(pts[:3,0])<-10) and np.all(np.diff(pts[3:,1])<-10)):
        raise ValueError('Selecciona X de derecha a izquierda e Y de abajo hacia arriba.')
    # X real positivo a la izquierda. Y positivo hacia arriba.
    mundo=np.vstack((np.column_stack((xs,np.zeros(3))),
                     np.column_stack((np.zeros(3),ys))))
    # findHomography estima foto -> coordenadas del papel.
    mat,_=cv2.findHomography(pts,mundo,method=0)
    if mat is None or not np.isfinite(mat).all():
        raise ValueError('No es posible calcular la perspectiva con estas marcas.')
    calc=cv2.perspectiveTransform(pts.reshape(-1,1,2),mat).reshape(-1,2)
    dif=np.linalg.norm(calc-mundo,axis=1)
    rms=float(np.sqrt(np.mean(dif**2)))
    worst=float(np.max(dif))
    if rms>1.15 or worst>2.0:
        raise ValueError(f'Marcas inconsistentes (error {rms:.2f} mm). Amplía el zoom y repite.')
    # Validación en torno al origen estimado para evitar transformaciones extremas.
    try:
        inv=np.linalg.inv(mat)
    except np.linalg.LinAlgError as e:
        raise ValueError('La perspectiva produce una transformación singular.') from e
    origen=cv2.perspectiveTransform(np.array([[[0.,0.]]],dtype=np.float64),inv)[0,0]
    b1=cv2.perspectiveTransform(np.array([[[50.,0.]]],dtype=np.float64),inv)[0,0]
    b2=cv2.perspectiveTransform(np.array([[[0.,50.]]],dtype=np.float64),inv)[0,0]
    pxmm1=np.linalg.norm(b1-origen)/50
    pxmm2=np.linalg.norm(b2-origen)/50
    if not (1.0<pxmm1<150 and 1.0<pxmm2<150):
        raise ValueError('Escala proyectiva fuera de rango.')
    return mat,{'rms_mm':round(rms,3),'max_error_mm':round(worst,3),
                'px_mm_orientativos':[round(pxmm1,3),round(pxmm2,3)]}


def aplicar_homografia(pts:np.ndarray,mat:np.ndarray)->np.ndarray:
    a=cv2.perspectiveTransform(np.asarray(pts,dtype=np.float64).reshape(-1,1,2),mat).reshape(-1,2)
    if not np.isfinite(a).all() or np.max(np.abs(a))>1e5:
        raise ValueError('Transformación geométrica fuera de rango.')
    return np.column_stack((-a[:,0],a[:,1]))
