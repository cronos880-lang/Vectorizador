"""Afinado conservador del trazado y reconocimiento de reglas en dos orientaciones.

No se sustituye la geometría real por rectas perfectas indiscriminadamente:
el error máximo de la polilínea simplificada queda limitado en píxeles.
"""
from __future__ import annotations
import cv2
import numpy as np


def contorno_ajustado(contorno: np.ndarray, bbox, interior: bool = False):
    w, h = int(bbox[2]), int(bbox[3])
    # Umbral absoluto acotado: reduce tramos de líneas largas y conserva detalles.
    epsilon = .55 if interior else float(np.clip(max(w, h) * .00255, .90, 2.05))
    pol = cv2.approxPolyDP(contorno, epsilon, True).reshape(-1,2)
    return pol


def calibracion_general(imagen, bbox=None):
    """Reconoce marcas largas de regla en borde izquierdo o derecho.

    Las rayas de 5 mm son de menor longitud: primero se intenta recuperar
    las marcas de centímetros largas. Si no hay señal suficiente, se utiliza
    sólo el eje confirmado y se indica una estimación para el otro.
    """
    from motor.vectorizar import _estimar_periodo
    gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    ed = cv2.Canny(gray, 45, 135)
    detected = cv2.HoughLinesP(ed, 1, np.pi/360, threshold=22,
                               minLineLength=max(32,round(min(w,h)*.027)),
                               maxLineGap=5)
    fallback={'estado':'no_fiable','metodo':'reglas_no_detectadas',
              'descripcion':'No se reconocen suficientes marcas de la regla. No se puede garantizar escala en mm.',
              'px_mm_x':None,'px_mm_y':None,'afin_automatica':None}
    if detected is None:
        return fallback
    # H: tramos horizontales de la regla vertical, a izquierda o derecha.
    # V: tramos verticales de la regla horizontal, arriba o abajo.
    hlong=[]; vlong=[]; vmedium=[]
    for x1,y1,x2,y2 in detected[:,0]:
        dx=abs(float(x2-x1));dy=abs(float(y2-y1))
        mx=(x1+x2)/2.;my=(y1+y2)/2.
        if dy<max(4.0,.065*dx) and dx>.075*w and (mx<.32*w or mx>.68*w):
            hlong.append(float(my))
        if dx<max(4.0,.065*dy) and (my<.32*h or my>.68*h) and .20*w<mx<.98*w:
            if dy>.061*h:
                vlong.append(float(mx))
            if dy>.035*h:
                vmedium.append(float(mx))
    sy=_estimar_periodo(hlong)
    sx=_estimar_periodo(vlong)
    # Desechar submúltiplos de 1 cm cuando coinciden con medio centímetro.
    # Solo se completa el eje X con suficiente consistencia geométrica.
    if sy and sx and abs(sx-sy)/max(sx,sy)>.23:
        if abs(2*sx-sy)/sy<.13: sx=2*sx
        elif abs(2*sy-sx)/sx<.13: sy=2*sy
    if sy and not sx:
        # La cadencia 5mm puede servir si la escala horizontal coincide con Y.
        sm=_estimar_periodo(vmedium)
        if sm:
            options=[sm,2*sm,sm/2]
            best=min(options,key=lambda p:abs(p-sy)/sy)
            if abs(best-sy)/sy<.12:sx=best
    if sy and not sx:
        # Escala provisional aproximada: una sola regla confirma el paso real.
        sx=sy
        estado='estimada'
        description='Se ha detectado la regla vertical; escala horizontal aproximada a partir de ella. Comprobar cotas.'
    elif sx and not sy:
        sy=sx
        estado='estimada'
        description='Se ha detectado la regla horizontal; escala vertical aproximada a partir de ella. Comprobar cotas.'
    elif sx and sy and abs(sx-sy)/max(sx,sy)<.24:
        estado='estimada'
        description='Marcas de 1 cm reconocidas en ambos ejes; escala orientativa sin corregir perspectiva.'
    else:
        return fallback
    # Proteger de submúltiplos o patrones de mesa/fondo absurdos.
    if not (.6<sx<100 and .6<sy<100):return fallback
    return {'estado':estado,'metodo':'reglas_auto_ambos_bordes',
            'descripcion':description,
            'px_mm_x':round(float(sx),5),'px_mm_y':round(float(sy),5),
            'afin_automatica':None,
            'calidad':{'marcas_detectadas_h':len(hlong),'marcas_detectadas_v':len(vlong)}}
