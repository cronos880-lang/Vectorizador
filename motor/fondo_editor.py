"""Fotografía corregida al mismo sistema CAD que el DXF; SOLO visualización."""
from __future__ import annotations
import base64
import cv2
import numpy as np
from motor.exportar import _operador, _validar_puntos


def preparar_fondo(imagen, vector, sx, sy, afin=None, proyectiva=None, sin_escala=False):
    """Devuelve PNG y límites CAD. No modifica ni crea geometría DXF."""
    _validar_puntos(vector)
    if imagen is None or imagen.ndim not in (2, 3):
        raise ValueError('Fotografía inválida para el fondo CAD.')
    transformar, _ = _operador(1., 1.) if sin_escala else _operador(sx, sy, afin, proyectiva)
    foto_pts = np.vstack([np.asarray(c['puntos'], dtype=np.float64) for c in vector['contornos']])
    cad_pts = transformar(foto_pts)
    origen = cad_pts.min(axis=0)
    cad_pts -= origen
    if not np.isfinite(cad_pts).all():
        raise ValueError('Coordenadas de fondo CAD no finitas.')
    cad_min = cad_pts.min(axis=0)
    cad_max = cad_pts.max(axis=0)
    ancho, alto = cad_max - cad_min
    if not (.01 < ancho < 10000 and .01 < alto < 10000):
        raise ValueError('No se puede encuadrar el fondo.')

    # Cuatro correspondencias definidas sobre la región útil de la pieza,
    # sin extrapolar la homografía a zonas muy alejadas del papel.
    pmin = foto_pts.min(axis=0)
    pmax = foto_pts.max(axis=0)
    pspan = np.maximum(pmax-pmin, [30., 30.])
    margin = np.maximum(10., pspan*.2)
    x0,y0 = pmin - margin
    x1,y1 = pmax + margin
    src = np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]], dtype=np.float64)
    dst = transformar(src)-origen
    H, _ = cv2.findHomography(src, dst, 0)
    if H is None or not np.isfinite(H).all():
        raise ValueError('No se pudo alinear la fotografía con el CAD.')
    # Asegurar exactitud de proyección local, incluido ArUco.
    check = np.vstack([foto_pts.min(axis=0),foto_pts.mean(axis=0),foto_pts.max(axis=0)])
    projected = cv2.perspectiveTransform(check.reshape(-1,1,2), H).reshape(-1,2)
    expected = transformar(check)-origen
    err = float(np.max(np.linalg.norm(projected-expected,axis=1)))
    if err > max(.06, .005*max(ancho,alto)):
        raise ValueError('Alineación insuficiente entre fotografía y geometría.')

    margin_cad = max(2., .12*max(ancho,alto)) if not sin_escala else max(12., .12*max(ancho,alto))
    xmin = float(cad_min[0]-margin_cad)
    ymin = float(cad_min[1]-margin_cad)
    xmax = float(cad_max[0]+margin_cad)
    ymax = float(cad_max[1]+margin_cad)
    width, height = xmax-xmin, ymax-ymin
    px_density = max(float(pspan[0]/ancho), float(pspan[1]/alto))
    density = min(40., max(5., px_density*1.05))
    density = min(density, 1700./max(width,height))
    w,h = max(2,int(round(width*density))),max(2,int(round(height*density)))
    to_bitmap = np.array([[w/width,0,-xmin*w/width],
                          [0,-h/height,ymax*h/height],
                          [0,0,1]],dtype=np.float64)
    transform_bitmap = to_bitmap @ H

    if imagen.ndim == 2:
        rgba = cv2.cvtColor(imagen,cv2.COLOR_GRAY2BGRA)
    elif imagen.shape[2]==3:
        rgba = cv2.cvtColor(imagen,cv2.COLOR_BGR2BGRA)
    else:
        rgba = imagen.copy()
    rendered = cv2.warpPerspective(rgba,transform_bitmap,(w,h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=(255,255,255,0))
    ok, buf = cv2.imencode('.png',rendered,[cv2.IMWRITE_PNG_COMPRESSION,3])
    if not ok:raise ValueError('No se pudo crear el fondo PNG.')
    return {'fondo_png':'data:image/png;base64,'+base64.b64encode(buf).decode('ascii'),
            'limites_cad':[xmin,ymin,xmax,ymax],
            'resolucion':[w,h],
            'error_alineacion_mm':round(err,5),
            'unidades':'px' if sin_escala else 'mm'}
