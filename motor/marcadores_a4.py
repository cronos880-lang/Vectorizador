"""Calibración de la plantilla física A4 V2 mediante ArUco 4x4 IDs 0-3.

Puntos métricos: coordenadas del PDF en mm, origen en esquina superior izquierda.
Transformación imagen -> hoja por homografía; no supone distancia a cámara.
"""
from __future__ import annotations
import cv2
import numpy as np

PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
MARKER_SIZE_MM = 18.0
# Esquinas superiores izquierdas exactas en la plantilla PDF original.
MARKER_ORIGINS_V2 = {
    0: (7.0, 7.0),
    1: (185.0, 7.0),
    2: (7.0, 272.0),
    3: (185.0, 272.0),
}
# Nueva plantilla V2.1: ID diferentes para evitar confundir geometrías
# con la primera edición impresa. No se mezclan los dos juegos.
MARKER_ORIGINS_V21 = {
    10: (10.0, 10.0),
    11: (182.0, 10.0),
    12: (10.0, 269.0),
    13: (182.0, 269.0),
}
MARKER_ORIGINS = {**MARKER_ORIGINS_V2, **MARKER_ORIGINS_V21}


def excluir_marcadores_plantilla(imagen: np.ndarray, found: dict, cal: dict):
    """Devuelve los cuadrados impresos que NUNCA deben considerarse piezas.

    Si hay >=3 marcadores, la homografía permite localizar incluso un
    marcador deteriorado o tapado por texto de la edición V2 original.
    """
    if not found:
        return {}
    regiones = {k: np.asarray(v, float) for k, v in found.items()}
    if cal.get('estado') != 'detectada' or not cal.get('proyectiva_automatica'):
        return regiones
    H = np.asarray(cal['proyectiva_automatica']['matriz'], dtype=np.float64)
    if H.shape != (3, 3) or not np.isfinite(H).all():
        return regiones
    try:
        inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return regiones
    config = MARKER_ORIGINS_V21 if cal.get('plantilla') == 'V2.1' else MARKER_ORIGINS_V2
    for mid, (x, y) in config.items():
        ref = np.array([[[x, y]], [[x + 18, y]],
                        [[x + 18, y + 18]], [[x, y + 18]]], np.float64)
        q = cv2.perspectiveTransform(ref, inv).reshape(4, 2)
        if np.isfinite(q).all():
            regiones[mid] = q
    return regiones


def detectar_marcadores(imagen: np.ndarray):
    """Devuelve diccionario ID->4 esquinas de imagen en orden ArUco."""
    aruco = getattr(cv2, 'aruco', None)
    if aruco is None:
        return {}
    gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen
    dic = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    params = aruco.DetectorParameters()
    params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    params.minMarkerPerimeterRate = 0.015
    detector = aruco.ArucoDetector(dic, params)
    corners, ids, _ = detector.detectMarkers(gray)
    found = {}
    if ids is None:
        return found
    for n, co in zip(ids.flatten(), corners):
        n = int(n)
        if n not in MARKER_ORIGINS or n in found:
            continue
        pts = co.reshape(4, 2).astype(np.float64)
        sides = np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1)
        if np.min(sides) < 9 or np.max(sides) / max(np.min(sides), 1) > 3.0:
            continue
        found[n] = pts
    return found


def _aplicar_h(puntos, H):
    a = cv2.perspectiveTransform(np.asarray(puntos, dtype=np.float64).reshape(-1, 1, 2), H)
    return a.reshape(-1, 2)


def calibracion_marcadores(imagen: np.ndarray, bbox_px=None, found=None):
    """Homografía completa con >=3 marcadores y verificación geométrica.

    Cuando faltan marcadores o no pasan el control de coherencia, devuelve
    no_fiable y el motor podrá utilizar las reglas de V1.6.
    """
    found = detectar_marcadores(imagen) if found is None else found
    grupos = [set(found).intersection(MARKER_ORIGINS_V2),
              set(found).intersection(MARKER_ORIGINS_V21)]
    grupo = max(grupos, key=len)
    config = MARKER_ORIGINS_V21 if grupo is grupos[1] else MARKER_ORIGINS_V2
    plantilla = 'V2.1' if config is MARKER_ORIGINS_V21 else 'V2'
    ids = sorted(grupo)
    fallo = {
        'estado': 'no_fiable', 'metodo': 'marcadores_aruco_v2',
        'marcadores_encontrados': len(ids),
        'descripcion': ('Plantilla V2: hacen falta al menos tres marcadores visibles y nítidos.'
                        if ids else 'No se han reconocido suficientes marcadores V2.'),
    }
    if len(ids) < 3:
        return fallo
    src, dst = [], []
    for mid in ids:
        src.extend(found[mid].tolist())
        ox, oy = config[mid]
        dst.extend(((ox, oy), (ox + 18, oy), (ox + 18, oy + 18), (ox, oy + 18)))
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    H, inliers = cv2.findHomography(src, dst, cv2.RANSAC, ransacReprojThreshold=.75)
    if H is None or not np.isfinite(H).all() or abs(float(np.linalg.det(H))) < 1e-12:
        return {**fallo, 'descripcion': 'Los marcadores no permiten obtener una perspectiva fiable.'}
    H /= H[2, 2]
    projected = _aplicar_h(src, H)
    diff = np.linalg.norm(projected - dst, axis=1)
    rms = float(np.sqrt(np.mean(diff**2)))
    worst = float(np.max(diff))
    if rms > .55 or worst > 1.1 or np.count_nonzero(inliers) < int(.80 * len(src)):
        return {**fallo, 'descripcion': 'Los marcadores son inconsistentes. Repite la fotografía más nítida.'}
    try:
        inv = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return fallo
    if bbox_px is None:
        ref = np.array([105., 148.5])
    else:
        x, y, w, h = map(float, bbox_px)
        ref = _aplicar_h([[x + w/2, y + h/2]], H)[0]
    if not (np.isfinite(ref).all() and -15 <= ref[0] <= 225 and -15 <= ref[1] <= 312):
        return fallo
    reference = _aplicar_h([ref, ref+[10., 0], ref+[0,10.]], inv)
    scale_x = float(np.linalg.norm(reference[1]-reference[0]) / 10)
    scale_y = float(np.linalg.norm(reference[2]-reference[0]) / 10)
    # Rechaza escalas físicamente absurdas y proyección casi singular.
    if not (1.0 < scale_x < 150 and 1.0 < scale_y < 150):
        return fallo
    # Derivadas de perspectiva sanas dentro de toda la superficie imprimible.
    surface = _aplicar_h([[0,0],[210,0],[0,297],[210,297],[105,148]],inv)
    if not np.isfinite(surface).all() or np.max(np.abs(surface)) > 100000:
        return fallo
    return {
        'estado': 'detectada', 'metodo': 'marcadores_aruco_v2', 'plantilla': plantilla,
        'marcadores_encontrados': len(ids),
        'px_mm_x': round(scale_x, 6), 'px_mm_y': round(scale_y, 6),
        'afin_automatica': None,
        'proyectiva_automatica': {
            'tipo': 'aruco_a4_v2', 'matriz': H.tolist(), 'plantilla': plantilla,
            'marcadores': len(ids), 'rms_mm': round(rms, 4),
        },
        'calidad': {'marcadores': len(ids), 'rms_mm': round(rms, 4),
                    'error_max_mm': round(worst, 4)},
        'descripcion': (f'Plantilla {plantilla}: {len(ids)} marcadores detectados. '
                        'Perspectiva corregida automáticamente; comprueba la impresión al 100%.'),
    }


def homografia_marcadores(datos: dict):
    """Verifica los coeficientes recibidos por la API antes de exportar DXF."""
    if not isinstance(datos, dict) or datos.get('tipo') != 'aruco_a4_v2':
        raise ValueError('Calibración de marcadores incorrecta.')
    H = np.asarray(datos.get('matriz'), dtype=np.float64)
    if H.shape != (3,3) or not np.isfinite(H).all():
        raise ValueError('Matriz de perspectiva incompleta.')
    if abs(float(np.linalg.det(H))) < 1e-12 or abs(H[2,2]) < 1e-12:
        raise ValueError('Matriz de perspectiva singular.')
    H = H / H[2,2]
    count = int(datos.get('marcadores', 0))
    if not 3 <= count <= 4:
        raise ValueError('Número de marcadores inválido.')
    return H, {'metodo': 'marcadores_aruco_v2', 'marcadores': count,
               'rms_mm': float(datos.get('rms_mm', 0))}
