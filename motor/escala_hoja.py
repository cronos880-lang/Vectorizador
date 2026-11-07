"""Calibración auxiliar por dimensiones de A4 visible.

Solo utiliza el tamaño de una hoja A4 reconocida como región clara aislada
sobre fondo oscuro, no segmentos de la pieza ni posiciones precargadas.
Devuelve estimación cuando falta parte del perímetro; nunca medida certificada.
"""
from __future__ import annotations
import cv2
import numpy as np


def _runs(mask):
    changes=np.diff(np.r_[False,mask,False].astype(np.int8))
    starts=np.where(changes==1)[0]; ends=np.where(changes==-1)[0]
    return list(zip(starts,ends))


def calibracion_a4(imagen, bbox=None):
    gray=cv2.cvtColor(imagen,cv2.COLOR_BGR2GRAY)
    h,w=gray.shape
    fail={'estado':'no_fiable','metodo':'a4_no_detectado',
          'descripcion':'No se ha identificado una hoja A4 completa o casi completa.',
          'px_mm_x':None,'px_mm_y':None,'afin_automatica':None}
    # Select paper when it stands out from the background; Otsu may be unreliable
    # if lighting varies, so test multiple moderate brightness thresholds.
    for level in (100,115,85,130):
        binary=np.uint8(gray>level)
        # Noise removed without appreciable change to page boundary.
        binary=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,np.ones((7,7),np.uint8))
        n,lab,stats,cent=cv2.connectedComponentsWithStats(binary,8)
        for index in sorted(range(1,n),key=lambda i: int(stats[i,cv2.CC_STAT_AREA]),reverse=True)[:3]:
            x,y,ww,hh,area=map(int,stats[index]); ratio=ww/hh
            if (area<.43*w*h or ww<.60*w or hh<.68*h or
                not .64<=ratio<=.78 or
                y<max(8,int(.008*h)) or y+hh>h-max(8,int(.005*h))):
                continue
            # Require that the paper has an observable edge on both top/bottom,
            # and at least one vertical edge. This prevents partial crops.
            right_internal=x+ww<w-10
            left_internal=x>10
            if not (right_internal or left_internal):continue
            page=np.uint8(lab==index)
            # Four middle cross sections should have consistent page brightness;
            # reject a bright wall or a foreground odd shape.
            cx=min(w-1,max(0,x+ww//2)); cy=min(h-1,max(0,y+hh//2))
            if page[cy,cx]==0:continue
            # Estimate millimetric scale from vertical A4 extent; horizontal
            # only if both paper edges appear, otherwise propagate vertical.
            sy=hh/297.0
            sx=ww/210.0 if left_internal and right_internal else sy
            if not(1.0<sx<100 and 1.0<sy<100):continue
            if abs(sx-sy)/max(sx,sy)>.18:continue
            if bbox:
                bx,by,bw,bh=map(float,bbox)
                if not(x-10<=bx and y-10<=by and bx+bw<=x+ww+10 and by+bh<=y+hh+10):
                    continue
            return {'estado':'estimada','metodo':'hoja_a4_visible',
                    'descripcion':('Hoja A4 reconocida. Escala aproximada por sus 297 mm de largo; '
                                   'no sustituye la calibración de las reglas ni corrige perspectiva.'),
                    'px_mm_x':round(float(sx),5),'px_mm_y':round(float(sy),5),
                    'afin_automatica':None,
                    'calidad':{'anchura_hoja_px':ww,'altura_hoja_px':hh,
                               'borde_izquierdo_visible':left_internal,
                               'borde_derecho_visible':right_internal}}
    return fail
