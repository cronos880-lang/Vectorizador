"""Recuperación conservadora de taladros que quedan fuera del umbral global.

No sustituye la vectorización anterior ni el reconocimiento de ranuras. Requiere
un hueco claro persistente a varios umbrales, una transición circular oscura
suficientemente continua y pared real alrededor. Los reflejos especulares de
borde nítido siguen siendo ambiguos; no se declara certeza metrológica.
"""
from __future__ import annotations
import math
import cv2
import numpy as np

_ANGULOS = (2*np.pi*np.arange(96,dtype=np.float32)/96)
_COS = np.cos(_ANGULOS)[None,:]
_SIN = np.sin(_ANGULOS)[None,:]


def _anillos(gris: np.ndarray,x:float,y:float,radios)->np.ndarray:
    r=np.asarray(radios,np.float32).reshape(-1,1)
    xx=(x+r*_COS).astype(np.float32)
    yy=(y+r*_SIN).astype(np.float32)
    return cv2.remap(gris,xx,yy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT).astype(np.float32)


def _ajuste_radial(gris_suave,x:float,y:float,radio0:float):
    pasos=np.linspace(max(2.25,radio0*.60),max(3.0,radio0*1.55),21)
    mejor=None
    for dx in (-1.,0.,1.):
        for dy in (-1.,0.,1.):
            xx,yy=x+dx,y+dy
            grad=_anillos(gris_suave,xx,yy,pasos-1.1)-_anillos(gris_suave,xx,yy,pasos+1.1)
            cobertura=np.mean(grad>14,axis=1)
            puntuaciones=np.mean(np.clip(grad,0,75),axis=1)/75*cobertura+.0006*np.mean(grad,axis=1)-.004*math.hypot(dx,dy)
            j=int(np.argmax(puntuaciones))
            if mejor is None or puntuaciones[j]>mejor[0]:
                mejor=(float(puntuaciones[j]),xx,yy,float(pasos[j]))
    if mejor is None:return None
    _,xx,yy,r=mejor
    grad=_anillos(gris_suave,xx,yy,[r-1.1])[0]-_anillos(gris_suave,xx,yy,[r+1.1])[0]
    centro=float(np.median(_anillos(gris_suave,xx,yy,[max(.5,r*.4)])))
    alrededor=float(np.median(_anillos(gris_suave,xx,yy,[r*1.7])))
    return {'x':float(xx),'y':float(yy),'radio':r,'cobertura':float(np.mean(grad>14)),
            'borde':float(np.median(grad)),'contraste':centro-alrededor}


def _ya_existe(vec, x:float,y:float,r:float)->bool:
    for e in vec['contornos']:
        if e['tipo']!='interior':continue
        if e.get('circulo'):
            centro=np.asarray(e['circulo']['centro_px'],float)
            if np.hypot(centro[0]-x,centro[1]-y) < r+float(e['circulo']['radio_px'])+1.5:
                return True
        else:
            cont=np.asarray(e['puntos'],np.float32)
            if cv2.pointPolygonTest(cont,(x,y),True)>=-r-1.5:
                return True
    return False


def _obtener_candidatos(gris, contorno):
    x,y,ancho,alto=cv2.boundingRect(contorno)
    mask=np.zeros(gris.shape,np.uint8)
    cv2.fillPoly(mask,[contorno],255)
    erodida=cv2.erode(mask,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7)))
    valores=gris[erodida>0]
    if len(valores)<100:return []
    otsu,_=cv2.threshold(valores.reshape(-1,1),0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    roi=gris[y:y+alto,x:x+ancho]; interior=erodida[y:y+alto,x:x+ancho]
    niveles=sorted(set([int(np.clip(otsu+d,55,190)) for d in (-20,-10,0,10,20)]+[95,105,115,125,135]))
    grupos=[]
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(3,3))
    for nivel in niveles:
        brillo=np.uint8((roi>nivel)&(interior>0))*255
        brillo=cv2.morphologyEx(brillo,cv2.MORPH_OPEN,kernel)
        n, etiquetas, estadisticas, centros=cv2.connectedComponentsWithStats(brillo,8)
        for j in range(1,n):
            xx,yy,ww,hh,area=map(int,estadisticas[j])
            if (area<12 or area>2000 or ww<4 or hh<4 or max(ww,hh)/max(1,min(ww,hh))>1.8):continue
            cx,cy=float(centros[j,0]+x),float(centros[j,1]+y)
            if cv2.pointPolygonTest(contorno,(cx,cy),True)<6:continue
            sub=np.uint8(etiquetas[yy:yy+hh,xx:xx+ww]==j)*255
            bordes,_=cv2.findContours(sub,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            if not bordes:continue
            c=max(bordes,key=cv2.contourArea)
            p=cv2.arcLength(c,True)
            if p<1 or 4*np.pi*cv2.contourArea(c)/(p*p)<.52:continue
            rad=max(2.,math.sqrt(area/np.pi))
            aa=2*np.pi*np.arange(16)/16
            xi=np.clip(np.rint(cx+.40*rad*np.cos(aa)).astype(int),0,gris.shape[1]-1)
            yi=np.clip(np.rint(cy+.40*rad*np.sin(aa)).astype(int),0,gris.shape[0]-1)
            xo=np.clip(np.rint(cx+1.65*rad*np.cos(aa)).astype(int),0,gris.shape[1]-1)
            yo=np.clip(np.rint(cy+1.65*rad*np.sin(aa)).astype(int),0,gris.shape[0]-1)
            contraste=float(np.median(gris[yi,xi])-np.median(gris[yo,xo]))
            if contraste<18:continue
            registro=(cx,cy,nivel,area,contraste)
            coincidencias=[]
            for k,g in enumerate(grupos):
                gx=np.median([item[0] for item in g]);gy=np.median([item[1] for item in g])
                if nivel not in [item[2] for item in g]:
                    dist=math.hypot(cx-gx,cy-gy)
                    if dist<max(3.5,rad*.45):coincidencias.append((dist,k))
            if coincidencias:
                grupos[min(coincidencias)[1]].append(registro)
            else:grupos.append([registro])
    resultado=[]
    for g in grupos:
        if len(g)<2:continue
        resultado.append((float(np.median([t[0] for t in g])),
                          float(np.median([t[1] for t in g])),
                          math.sqrt(float(np.median([t[3] for t in g]))/np.pi),
                          len(g),float(np.median([t[4] for t in g]))))
    return sorted(resultado,key=lambda a:(a[1],a[0]))


def recuperar_agujeros(imagen:np.ndarray,vector:dict, *, limite:int=35)->dict:
    """Devuelve la geometría con círculos extra solo si superan TODOS los filtros.

    La función no modifica `vector`, para mantener un punto de restauración.
    """
    salida={**vector, 'contornos':list(vector['contornos'])}
    exteriores=[c for c in salida['contornos'] if c['tipo']=='exterior']
    if len(exteriores)!=1:
        salida['agujeros_recuperados']=0
        return salida
    exterior=np.rint(np.asarray(exteriores[0].get('borde_px',exteriores[0]['puntos']),float)).astype(np.int32)
    if len(exterior)<3:
        salida['agujeros_recuperados']=0
        return salida
    gris=cv2.cvtColor(imagen,cv2.COLOR_BGR2GRAY)
    suave=cv2.GaussianBlur(gris,(3,3),.7)
    for cx,cy,r0,soporte,contraste in _obtener_candidatos(gris,exterior):
        if salida.get('agujeros_recuperados',0)>=limite:break
        if _ya_existe(salida,cx,cy,r0):continue
        ajuste=_ajuste_radial(suave,cx,cy,r0)
        if ajuste is None:continue
        xx,yy,r=ajuste['x'],ajuste['y'],ajuste['radio']
        # La pared debe ser mayor que el radio. Ello rechaza reflejos unidos
        # al contorno y perforaciones cuyo centro no pertenece al material.
        pared=float(cv2.pointPolygonTest(exterior,(xx,yy),True))
        if not (r>=3.6 and ajuste['cobertura']>=.72 and ajuste['borde']>=16
                and ajuste['contraste']>=32 and pared>=1.90*r+1.5
                and _ya_existe(salida,xx,yy,r) is False):continue
        # Evitar geometrías que tocan el contorno y duplicados.
        coords=np.column_stack((xx+r*np.cos(_ANGULOS), yy+r*np.sin(_ANGULOS)))
        salida['contornos'].append({'tipo':'interior','puntos':coords.tolist(),
                    'area_px2':round(math.pi*r*r,2),'origen_deteccion':'recuperado',
                    'circulo':{'centro_px':[xx,yy],'radio_px':r}})
        salida['agujeros_recuperados']=salida.get('agujeros_recuperados',0)+1
    salida.setdefault('agujeros_recuperados',0)
    # La vista previa binaria se mantiene coherente con los nuevos agujeros.
    if salida['agujeros_recuperados'] and isinstance(vector.get('silueta_png'),str):
        import base64
        data=vector['silueta_png'].split(',',1)[-1]
        mini=cv2.imdecode(np.frombuffer(base64.b64decode(data),np.uint8),cv2.IMREAD_GRAYSCALE)
        if mini is not None:
            for c in salida['contornos']:
                if c.get('origen_deteccion')=='recuperado':
                    cp=c['circulo'];cv2.circle(mini,tuple(int(round(z)) for z in cp['centro_px']),
                       int(round(cp['radio_px'])),255,-1)
            ok,b=cv2.imencode('.png',mini,[cv2.IMWRITE_PNG_COMPRESSION,5])
            if ok:salida['silueta_png']='data:image/png;base64,'+base64.b64encode(b).decode('ascii')
    return salida
