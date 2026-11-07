"""DXF ajustado V2.0.30: perfil exterior idéntico al que emplea el STL.

No cambia el DXF original ni reescala agujeros por tolerancias de impresión.
Mantiene las entidades CAD originales de los agujeros (círculos y arcos).
"""
from __future__ import annotations
import io
import math
import ezdxf
from shapely.geometry import Polygon
from motor.editor_cad import dxf_editado, validar_entidades
from motor.extrusion_stl import (
    PRECISION_STL, MAX_OFFSET_EXTERIOR_MM,
    _perfil, _poligonos_solidos, _offset_exterior_stl,
)


def construir_dxf_ajustado(entidades, offset_exterior: float, precision_stl: str = 'normal'):
    validar_entidades(entidades)
    if precision_stl not in PRECISION_STL:
        raise ValueError('Precisión STL no válida.')
    if (not isinstance(offset_exterior, (float, int)) or isinstance(offset_exterior, bool)
        or not math.isfinite(offset_exterior) or abs(offset_exterior) > MAX_OFFSET_EXTERIOR_MM):
        raise ValueError('Offset exterior fuera del rango -5 a +5 mm.')
    config = PRECISION_STL[precision_stl]
    originales = _poligonos_solidos(entidades,config['error_cuerda'],config['simplificacion'])
    desplazados = _offset_exterior_stl(originales, float(offset_exterior), config['buffer_quad'])
    raw = dxf_editado(entidades,False)
    # offset=0 conserva entidades CAD ORIGINALES (círculos, bulges y segmentos),
    # sin reemplazar ni discretizar ninguna de ellas.
    if offset_exterior == 0:
        return raw, {'contornos_ajustados':0, 'ancho_mm': _bounds(desplazados)[0],
                     'alto_mm':_bounds(desplazados)[1]}

    doc = ezdxf.read(io.StringIO(raw.decode('utf-8')))
    model = doc.modelspace()
    cad_entities = list(model)
    if len(cad_entities) != len(entidades):
        raise ValueError('Las entidades del DXF no corresponden con el editor. Exportación cancelada.')
    # Las superficies sólidas proceden del mismo motor de interpretación de
    # anidamiento que el STL. No confiar solo en el nombre de la capa CAD.
    indices_exteriores = set()
    for original in originales:
        anillo = Polygon(original.exterior)
        matches = [i for i,e in enumerate(entidades)
                   if i not in indices_exteriores and
                   _perfil(e, config['error_cuerda'],config['simplificacion']).equals(anillo)]
        if len(matches) != 1:
            raise ValueError('No es posible identificar unívocamente los contornos exteriores del DXF.')
        indices_exteriores.add(matches[0])
    for i in indices_exteriores:
        model.delete_entity(cad_entities[i])
    for nuevo in desplazados:
        puntos = list(nuevo.exterior.coords)[:-1]
        if len(puntos) < 3:
            raise ValueError('Contorno ajustado sin puntos suficientes.')
        model.add_lwpolyline(puntos, close=True, dxfattribs={'layer':'CONTORNO_EXTERIOR'})
    # Los interiores NO se convierten en segmentos: se preservan como CIRCLE o
    # LWPOLYLINE con bulges, por lo que se pueden editar en Onshape.
    if doc.audit().has_errors:
        raise ValueError('El DXF ajustado presenta errores estructurales.')
    out = io.StringIO()
    doc.write(out)
    a,h = _bounds(desplazados)
    return out.getvalue().encode('utf-8'), {'contornos_ajustados':len(indices_exteriores),
                                           'ancho_mm':a,'alto_mm':h}


def _bounds(solids):
    minx=min(s.bounds[0] for s in solids)
    miny=min(s.bounds[1] for s in solids)
    maxx=max(s.bounds[2] for s in solids)
    maxy=max(s.bounds[3] for s in solids)
    return maxx-minx,maxy-miny
