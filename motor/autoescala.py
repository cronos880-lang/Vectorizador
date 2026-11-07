"""Detección automática y cautelosa de las reglas impresas de la plantilla.

Usa cadencia de marcas largas (1 cm) y calibra una transformación local
AFÍN alrededor de la pieza. No promete homografía ni precisión metrológica;
rechaza patrones incompletos o irregulares en vez de aplicar ajustes falsos.
"""
from __future__ import annotations
import math
import cv2
import numpy as np


def _candidatos(gris):
    h,w=gris.shape
    bordes=cv2.Canny(gris,50,150)
    lines=cv2.HoughLinesP(bordes,1,np.pi/360,threshold=28,
                          minLineLength=max(22,int(.032*min(h,w))),maxLineGap=9)
    horizontales=[];verticales=[]
    if lines is None:return [],[]
    for xx1,yy1,xx2,yy2 in lines[:,0]:
        x1,y1,x2,y2=map(float,(xx1,yy1,xx2,yy2))
        dx=x2-x1;dy=y2-y1
        if (abs(dy)<=max(3,abs(dx)*.055) and abs(dx)>=.043*w and
            .68*w<min(x1,x2)<.87*w and max(x1,x2)<.96*w and
            .018*h<(y1+y2)/2<.77*h):
            horizontales.append((x1,y1,x2,y2))
        if (abs(dx)<=max(3,abs(dy)*.055) and abs(dy)>=.032*h and
            .72*h<min(y1,y2)<.87*h and max(y1,y2)<.94*h and
            .008*w<(x1+x2)/2<.84*w):
            verticales.append((x1,y1,x2,y2))
    return horizontales,verticales


def _picos(signal,periodo):
    # Umbral relativo y ventanas estrechas: los trazos de 1 mm de menor
    # longitud quedan fuera de la franja donde empiezan los de 1 cm.
    signal=np.asarray(signal,float)
    sm=np.convolve(signal,np.ones(5)/5,mode='same')
    techo=float(np.max(sm))
    if techo<18:return np.empty(0),np.empty(0)
    filtro=max(18.,techo*.48)
    candidatos=np.where((sm[2:-2]>=sm[:-4])&(sm[2:-2]>=sm[4:])&
                       (sm[2:-2]>=sm[1:-3])&(sm[2:-2]>=sm[3:-1])&
                       (sm[2:-2]>filtro))[0]+2
    # Elimina ambos bordes de un mismo trazo (1-3 píxeles).
    seleccion=[]
    for i in sorted(candidatos,key=lambda j:-sm[j]):
        if all(abs(i-j)>max(5,int(periodo*.19)) for j in seleccion):
            seleccion.append(int(i))
    seleccion.sort()
    seleccion=[j for j in seleccion if sm[j]>=techo*.70]
    return np.array(seleccion,float),sm[seleccion]


def _ajustar_regla(picos,fuerzas,periodo,pixel_centro):
    if len(picos)<6 or not np.isfinite(periodo) or not 35<periodo<220:
        return None
    # Selecciona la fase de los centímetros, descartando las medias marcas.
    mejor=None
    for p in picos:
        k=np.rint((picos-p)/periodo)
        residual=np.abs(picos-p-k*periodo)
        ok=residual<max(3.5,.11*periodo)
        if np.count_nonzero(ok)<6:continue
        indices=np.unique(k[ok]);span=np.ptp(indices)
        if span<5:continue
        score=float(np.sum(fuerzas[ok])) + float(span)*10
        if mejor is None or score>mejor[0]:mejor=(score,k,ok)
    if mejor is None:return None
    _,k,ok=mejor
    kval=k[ok];pix=picos[ok];wt=fuerzas[ok]
    if len(np.unique(kval))<6:return None
    # Estimación del cambio de escala con la posición (perspectiva suave).
    # La derivada en el centro de la pieza da una escala local más útil que
    # un promedio de toda la regla. Se limita el término de segundo grado.
    lineal=np.polyfit(kval,pix,1)
    if not .92*periodo<lineal[0]<1.08*periodo:return None
    ajustado=np.polyfit(kval,pix,2,w=np.sqrt(wt)) if len(kval)>=8 else np.array([0.,*lineal])
    pred=np.polyval(ajustado,kval)
    rms=float(np.sqrt(np.mean((pred-pix)**2)))
    if rms>2.4:return None
    # Evitar extrapolación excesiva a piezas fuera del tramo visible.
    ncentro=float(np.interp(pixel_centro,pix[np.argsort(pix)],kval[np.argsort(pix)]))
    if pixel_centro<min(pix)-periodo or pixel_centro>max(pix)+periodo:
        return None
    local=float(2*ajustado[0]*ncentro+ajustado[1])
    if not (.92*periodo<local<1.08*periodo):return None
    return {'px_por_cm':round(local,5),'rms_px':round(rms,3),
            'marcas_cm':int(len(kval)), 'periodo_medio_px':round(float(lineal[0]),3)}


def calibracion_automatica(imagen, bbox=None):
    """Devuelve escala y ajuste afín si ambas reglas superan control de calidad.

    El ajuste evita pedir clics al usuario. No corrige distorsión radial ni
    garantiza una rectificación proyectiva completa.
    """
    gris=cv2.cvtColor(imagen,cv2.COLOR_BGR2GRAY)
    h,w=gris.shape
    cx=(bbox[0]+bbox[2]/2) if bbox else w*.5
    cy=(bbox[1]+bbox[3]/2) if bbox else h*.6
    horizontales,verticales=_candidatos(gris)
    fallo={'estado':'no_fiable','metodo':'sin_calibracion',
           'descripcion':'No se pudieron reconocer ambas reglas de 1 cm con suficiente fiabilidad.',
           'px_mm_x':None,'px_mm_y':None,'afin_automatica':None}
    if len(horizontales)<5 or len(verticales)<5:return fallo
    hh=[min(a[0],a[2]) for a in horizontales if (a[1]+a[3])/2<.77*h]
    vv=[min(a[1],a[3]) for a in verticales if (a[0]+a[2])/2<.8*w]
    if not hh or not vv:return fallo
    x_ini=np.median(hh)
    y_ini=np.median(vv)
    xb0=max(0,int(x_ini-9));xb1=min(w,int(x_ini+35))
    yb0=max(0,int(y_ini-9));yb1=min(h,int(y_ini+36))
    if xb1-xb0<15 or yb1-yb0<15:return fallo
    # Proyección oscura de tramos donde llegan principalmente rayas largas.
    ya=max(0,int(.02*h));yb=min(h,int(.82*h))
    xa=max(0,int(.01*w));xb=min(w,int(.85*w))
    proj_y=np.mean(255-gris[ya:yb,xb0:xb1].astype(float),axis=1)
    proj_x=np.mean(255-gris[yb0:yb1,xa:xb].astype(float),axis=0)
    # Paso de un centímetro: estimación robusta de segmentos largos.
    from motor.vectorizar import _estimar_periodo, _lineas_regla
    principales_y, principales_x = _lineas_regla(gris)
    prior_y=_estimar_periodo(principales_y)
    prior_x=_estimar_periodo(principales_x)
    if prior_y and not prior_x:
        # Si en iluminación diferente Hough ve medias divisiones de 5 mm,
        # resuelve la ambigüedad usando la cadencia del otro eje.
        parcial=_estimar_periodo([.5*(r[0]+r[2]) for r in verticales])
        if parcial:
            opciones=[parcial,2*parcial]
            elegido=min(opciones,key=lambda p:abs(p-prior_y))
            if abs(elegido-prior_y)/prior_y<.25:prior_x=elegido
    if not prior_y or not prior_x:return fallo
    py,fy=_picos(proj_y,prior_y*10)
    px,fx=_picos(proj_x,prior_x*10)
    py+=ya;px+=xa
    info_y=_ajustar_regla(py,fy,prior_y*10,cy)
    info_x=_ajustar_regla(px,fx,prior_x*10,cx)
    if not info_x or not info_y:return fallo
    sx=info_x['px_por_cm']/10;sy=info_y['px_por_cm']/10
    # Ángulo de las marcas: compensar ligera rotación y cizalla en el papel.
    ang_x=np.array([(r[3]-r[1])/(r[2]-r[0]) for r in horizontales if abs(r[2]-r[0])>30])
    ang_y=np.array([(r[2]-r[0])/(r[3]-r[1]) for r in verticales if abs(r[3]-r[1])>30])
    slope_x=float(np.median(ang_x)) if len(ang_x)>4 else 0.
    slope_y=float(np.median(ang_y)) if len(ang_y)>4 else 0.
    if abs(slope_x)>.075 or abs(slope_y)>.075:return fallo
    origin=[float(cx),float(cy)]
    # Para reproducir la orientación del DXF V1.1: coordenada horizontal
    # CAD crece hacia la derecha; vertical CAD hacia arriba.
    point_x=[origin[0]-10*sx,origin[1]-10*sx*slope_x]
    point_y=[origin[0]-10*sy*slope_y,origin[1]-10*sy]
    return {'estado':'detectada','metodo':'reglas_automaticas_afin_local',
            'descripcion':'Reglas de 1 cm detectadas. Escala local y leve inclinación ajustadas automáticamente.',
            'px_mm_x':round(sx,5),'px_mm_y':round(sy,5),
            'afin_automatica':{'origen':origin,'punto_x':point_x,'punto_y':point_y,
                               'mm_x':10,'mm_y':10},
            'calidad':{'eje_x':info_x,'eje_y':info_y}}
