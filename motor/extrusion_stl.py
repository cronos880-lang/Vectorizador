"""STL métrico de una o más siluetas CAD planas.

No modifica la geometría 2D de Vectorizador. Rechaza perfiles abiertos y
geometrías problemáticas en lugar de crear sólidos defectuosos silenciosamente.
"""
from __future__ import annotations

from collections import Counter
import math
import struct

from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from motor.editor_cad import validar_entidades

# Desviación máxima entre cada arco y su cuerda, en mm.
ERROR_CUERDA = 0.025
# Precisión geométrica OBJETIVO (flecha máxima de arco, en mm).
# NORMAL debe seguir exactamente la misma ruta que V2.0.25.
PRECISION_STL = {
    'normal': {'error_cuerda': 0.025, 'simplificacion': 0.005, 'buffer_quad': 16},
    'alta':   {'error_cuerda': 0.010, 'simplificacion': 0.002, 'buffer_quad': 32},
    'maxima': {'error_cuerda': 0.005, 'simplificacion': 0.001, 'buffer_quad': 64},
}
MAX_TRIANGULOS = 160000
MAX_PUNTOS = 14000


def _curva_bulge(a, b, bulge, error_cuerda=ERROR_CUERDA):
    x1, y1 = a[:2]
    x2, y2 = b[:2]
    bulge = float(bulge)
    if abs(bulge) < 1e-9:
        return [(x1, y1), (x2, y2)]
    dx, dy = x2-x1, y2-y1
    distancia = math.hypot(dx, dy)
    if distancia < 1e-8:
        raise ValueError('Arco CAD con extremos coincidentes.')
    cx = (x1+x2)/2 - dy*(1-bulge*bulge)/(4*bulge)
    cy = (y1+y2)/2 + dx*(1-bulge*bulge)/(4*bulge)
    radio = math.hypot(x1-cx, y1-cy)
    sweep = 4 * math.atan(bulge)
    max_step = 2*math.acos(max(-1., min(1., 1-error_cuerda/max(radio,1e-10))))
    steps = max(2, math.ceil(abs(sweep)/max(max_step, .001)))
    if steps > MAX_PUNTOS:
        raise ValueError('Arco demasiado complejo para extruir.')
    ang = math.atan2(y1-cy, x1-cx)
    return [(x1, y1)] + [
        (cx + radio*math.cos(ang+sweep*j/steps), cy + radio*math.sin(ang+sweep*j/steps))
        for j in range(1, steps)
    ] + [(x2, y2)]


def _vertices(entidad, error_cuerda=ERROR_CUERDA):
    tipo = entidad['tipo']
    if tipo == 'circle':
        cx,cy,r = entidad['cx'],entidad['cy'],entidad['radio']
        max_step = 2*math.acos(max(-1.,min(1.,1-error_cuerda/r)))
        n = max(32, min(MAX_PUNTOS, math.ceil(2*math.pi/max(max_step,.001))))
        return [(cx+r*math.cos(2*math.pi*j/n),cy+r*math.sin(2*math.pi*j/n)) for j in range(n)]
    if tipo == 'rectangle':
        (x1,y1),(x2,y2)=entidad['a'],entidad['b']
        return [(x1,y1),(x2,y1),(x2,y2),(x1,y2)]
    if tipo != 'polyline' or not entidad['cerrada']:
        raise ValueError(f"'{tipo}': hay un perfil abierto. Utiliza Unir y Cerrar antes de extruir; no se omite ninguna línea.")
    v=entidad['vertices']
    coords=[]
    for j,a in enumerate(v):
        b=v[(j+1)%len(v)]
        puntos=_curva_bulge(a,b,a[2],error_cuerda)
        coords.extend(puntos[:-1])
        if len(coords)>MAX_PUNTOS:
            raise ValueError('Contorno demasiado detallado para un STL seguro.')
    return coords


def _perfil(entidad, error_cuerda=ERROR_CUERDA, simplificacion=.005):
    points=_vertices(entidad, error_cuerda)
    # Cuantización submicrométrica para coincidir exactamente en triangulación y paredes.
    compact=[]
    for x,y in points:
        p=(round(x,7),round(y,7))
        if not compact or p != compact[-1]:compact.append(p)
    if len(compact)>1 and compact[0]==compact[-1]:compact.pop()
    if len(compact)<3:raise ValueError('Contorno sin superficie válida.')
    if len(compact)>MAX_PUNTOS:raise ValueError('Demasiados puntos en un contorno.')
    poly=Polygon(compact)
    if not poly.is_valid:
        raise ValueError('Un contorno se cruza a sí mismo o contiene vértices inválidos. Revísalo con Verificar.')
    if poly.area < .01:
        raise ValueError('La superficie es inferior a 0,01 mm²; puede ser un artefacto de la detección óptica.')
    # Reduce puntos espurios por fragmentación óptica sin desplazar el perfil > 0.005 mm.
    poly=poly.simplify(simplificacion,preserve_topology=True)
    if not isinstance(poly,Polygon) or not poly.is_valid or poly.area<.01:
        raise ValueError('No es posible crear un contorno sólido de esta geometría.')
    return poly


def _poligonos_solidos(entidades, error_cuerda=ERROR_CUERDA, simplificacion=.005):
    validar_entidades(entidades)
    if not entidades:raise ValueError('El editor CAD está vacío.')
    # No omitimos ni alteramos perfiles automáticamente: una detección óptica
    # puede ser un agujero real. Informar la entidad permite corregirla en CAD.
    loops=[]
    for indice, entidad in enumerate(entidades, 1):
        try:
            loops.append(_perfil(entidad,error_cuerda,simplificacion))
        except ValueError as exc:
            identificador=entidad.get('id', f'entidad-{indice}')
            tipo=entidad.get('tipo', 'desconocido')
            if tipo=='circle':
                detalle=(f"círculo con centro ({entidad['cx']:.3f}, "
                         f"{entidad['cy']:.3f}) mm y radio {entidad['radio']:.4f} mm")
            else:
                detalle=f"perfil {tipo}"
            raise ValueError(
                f"Entidad {indice} ({identificador}; {detalle}): {exc} "
                'Revisa o elimina el elemento en el editor 2D antes de extruir. '
                'No se ha modificado la geometría original.'
            ) from exc
    if sum(len(poly.exterior.coords) for poly in loops)>MAX_PUNTOS:
        raise ValueError('Demasiados puntos para generar un STL seguro.')
    parents=[None]*len(loops)
    for i,poly in enumerate(loops):
        containing=[]
        for j,other in enumerate(loops):
            if i==j:continue
            if other.contains(poly):
                containing.append(j)
            elif not poly.contains(other) and not poly.disjoint(other):
                raise ValueError(
                    f'Contornos {i+1} y {j+1} ({entidades[i].get("id", "sin-id")} / '
                    f'{entidades[j].get("id", "sin-id")}) se cruzan o tocan: '
                    'uno de los agujeros puede sobresalir del exterior. '
                    'Revisa los perfiles en el editor 2D; no se han desplazado ni recortado.'
                )
        if containing:parents[i]=min(containing,key=lambda j:loops[j].area)
    def depth(i):
        n=0
        while parents[i] is not None:
            n+=1;i=parents[i]
        return n
    solids=[]
    for i,outer in enumerate(loops):
        if depth(i)%2:continue
        holes=[list(loops[j].exterior.coords)[:-1] for j,p in enumerate(parents) if p==i and depth(j)%2]
        solid=orient(Polygon(list(outer.exterior.coords)[:-1],holes=holes),sign=1.0)
        if not solid.is_valid or solid.area<.01:
            raise ValueError('Los agujeros no forman un contorno sólido válido.')
        solids.append(solid)
    if not solids:raise ValueError('No se han identificado superficies cerradas para extruir.')
    return solids



# V2.0.28: offset MÉTRICO solo de perfiles exteriores del STL.
# La distancia es radial (por lado), no un aumento total del ancho.
MAX_OFFSET_EXTERIOR_MM = 5.0


def _offset_exterior_stl(solids, distancia_mm, buffer_quad=16):
    """Desplaza los bordes EXTERIORES en +/-mm, conservando los agujeros.

    Un contorno pequeño o estrecho puede desaparecer, dividirse o alcanzar un
    hueco. Se rechaza tal caso en vez de generar un STL diferente silenciosamente.
    """
    if distancia_mm == 0:
        return solids  # Ruta V2.0.26 EXACTA, sin reprocesar nada.
    result=[]
    for solid in solids:
        exterior=Polygon(solid.exterior)
        # Esquinas CAD conservadas como esquinas (mitre limitado para evitar
        # puntas muy largas en geometría óptica aguda).
        desplazado=exterior.buffer(
            distancia_mm, quad_segs=buffer_quad, join_style='mitre', mitre_limit=2)
        if (not isinstance(desplazado, Polygon) or desplazado.is_empty
                or not desplazado.is_valid or len(desplazado.interiors)):
            raise ValueError('El offset exterior divide, elimina o invalida un contorno. Reduce la distancia.')
        if desplazado.area < .01 or len(desplazado.exterior.coords)>MAX_PUNTOS:
            raise ValueError('El offset hace desaparecer la pieza o genera demasiados vértices. Reduce la distancia.')
        agujeros=[]
        for interior in solid.interiors:
            hole=Polygon(interior)
            if (not desplazado.contains(hole) or
                    desplazado.boundary.distance(hole) <= 1e-6):
                raise ValueError('El offset exterior alcanza un agujero o ranura. Reduce la distancia negativa.')
            agujeros.append(list(interior.coords))
        pieza=orient(Polygon(list(desplazado.exterior.coords), holes=agujeros),sign=1.0)
        if not pieza.is_valid or pieza.area < .01:
            raise ValueError('El offset deja una geometría inválida o sin material. Reduce la distancia.')
        result.append(pieza)
    # Las piezas aisladas o islas dentro de huecos no pueden unirse entre sí.
    for i,a in enumerate(result):
        for b in result[i+1:]:
            if not a.disjoint(b):
                raise ValueError('El offset hace que dos piezas se toquen o se solapen. Reduce la distancia positiva.')
    return result

def _holgura_stl(solids, incremento_diametro, buffer_quad=16):
    """Ensancha únicamente los vacíos interiores, sin mover el contorno exterior.

    incremento_diametro expresa un AUMENTO del diámetro/anchura total, no del radio.
    Se hace después de interpretar los perfiles para no alterar ni DXF ni CAD.
    """
    if incremento_diametro == 0:
        return solids  # Ruta idéntica, bit por bit, a V2.0.23.
    radio_extra = incremento_diametro / 2.
    ajustados=[]
    for solid in solids:
        shell=Polygon(solid.exterior)
        agujeros=[]
        for interior in solid.interiors:
            # Los contornos arbitrarios (incluidas ranuras) tienen una holgura uniforme.
            # buffer redondea únicamente las esquinas del hueco, no las de la pieza.
            nuevo=Polygon(interior).buffer(radio_extra, quad_segs=buffer_quad, join_style='round')
            if not isinstance(nuevo, Polygon) or nuevo.is_empty or not nuevo.is_valid:
                raise ValueError('La compensación produce un agujero inválido; disminuye la holgura STL.')
            if not shell.contains(nuevo) or shell.boundary.distance(nuevo) <= 1e-7:
                raise ValueError('La holgura de un agujero alcanza el contorno exterior. Reduce la compensación.')
            if len(nuevo.exterior.coords) > MAX_PUNTOS:
                raise ValueError('La compensación produce demasiados vértices en un agujero.')
            for anterior in agujeros:
                if not nuevo.disjoint(anterior):
                    raise ValueError('Con esta holgura dos agujeros se tocan o se solapan. Reduce la compensación.')
            agujeros.append(nuevo)
        modificado=orient(Polygon(solid.exterior.coords,
                                  holes=[list(h.exterior.coords) for h in agujeros]), sign=1.0)
        if not modificado.is_valid or modificado.area < .01:
            raise ValueError('La holgura genera una pieza con geometría inválida o demasiado fina.')
        ajustados.append(modificado)
    return ajustados


def construir_stl(entidades:list[dict],grosor:float,compensacion_agujeros:float=0.0,
                  precision_stl:str='normal',offset_exterior:float=0.0):
    """Devuelve (STL binario, metadatos) tras comprobar cierre, caras y volumen."""
    if not isinstance(grosor,(int,float)) or isinstance(grosor,bool) or not math.isfinite(grosor) or not 1<=grosor<=3:
        raise ValueError('El grosor debe estar entre 1 y 3 mm.')
    if (not isinstance(compensacion_agujeros, (int,float)) or isinstance(compensacion_agujeros,bool)
            or not math.isfinite(compensacion_agujeros) or not 0<=compensacion_agujeros<=1):
        raise ValueError('La compensación de diámetro debe estar entre 0 y +1,00 mm.')
    # No se permite una calidad desconocida ni interpretar valores arbitrarios.
    if not isinstance(precision_stl,str) or precision_stl not in PRECISION_STL:
        raise ValueError('La precisión STL debe ser Normal, Alta o Máxima.')
    if (not isinstance(offset_exterior,(int,float)) or isinstance(offset_exterior,bool)
            or not math.isfinite(offset_exterior) or abs(offset_exterior)>MAX_OFFSET_EXTERIOR_MM):
        raise ValueError('El offset exterior debe estar entre -5 y +5 mm.')
    config=PRECISION_STL[precision_stl]
    solids=_holgura_stl(
        _offset_exterior_stl(
            _poligonos_solidos(entidades,config['error_cuerda'],config['simplificacion']),
            float(offset_exterior),config['buffer_quad']),
        float(compensacion_agujeros),config['buffer_quad'])
    vertices=[]
    ids={}
    caras=[]
    def vid(x,y,z):
        p=(round(float(x),7),round(float(y),7),float(z))
        if p not in ids:
            ids[p]=len(vertices);vertices.append(p)
        return ids[p]
    def triangulo(a,b,c):
        va,vb,vc=(vertices[x] for x in (a,b,c))
        nx=(vb[1]-va[1])*(vc[2]-va[2])-(vb[2]-va[2])*(vc[1]-va[1])
        ny=(vb[2]-va[2])*(vc[0]-va[0])-(vb[0]-va[0])*(vc[2]-va[2])
        nz=(vb[0]-va[0])*(vc[1]-va[1])-(vb[1]-va[1])*(vc[0]-va[0])
        if nx*nx+ny*ny+nz*nz<1e-17:
            raise ValueError('El contorno genera caras 3D degeneradas. Revísalo.')
        caras.append((a,b,c))
        if len(caras)>MAX_TRIANGULOS:raise ValueError('El STL es demasiado complejo; simplifica el contorno.')
    for solid in solids:
        triangles=constrained_delaunay_triangles(solid)
        area=0.
        for t in triangles.geoms:
            if t.area<1e-12:continue
            if not solid.covers(t.representative_point()):
                raise ValueError('Triangulación fuera de la pieza; no se exporta el STL.')
            pts=list(t.exterior.coords)[:3]
            signed=(pts[1][0]-pts[0][0])*(pts[2][1]-pts[0][1])-(pts[1][1]-pts[0][1])*(pts[2][0]-pts[0][0])
            if signed<0:pts=[pts[0],pts[2],pts[1]]
            top=[vid(x,y,grosor) for x,y in pts]
            bot=[vid(x,y,0.) for x,y in pts]
            triangulo(*top)
            triangulo(bot[2],bot[1],bot[0])
            area+=t.area
        if abs(area-solid.area)>max(.00001,solid.area*.00005):
            raise ValueError('La triangulación de la pieza deja huecos. STL cancelado.')
        for ring in [solid.exterior,*solid.interiors]:
            pts=list(ring.coords)
            for p,q in zip(pts,pts[1:]):
                a0=vid(*p,0.);b0=vid(*q,0.)
                a1=vid(*p,grosor);b1=vid(*q,grosor)
                triangulo(a0,b0,b1)
                triangulo(a0,b1,a1)
    # Superficie cerrada y orientación consistente de todas las aristas.
    edges=Counter()
    directed=Counter()
    for a,b,c in caras:
        for u,v in ((a,b),(b,c),(c,a)):
            edges[(min(u,v),max(u,v))]+=1
            directed[(u,v)]+=1
    if not edges or any(n!=2 for n in edges.values()) or any(directed[(a,b)]!=1 or directed[(b,a)]!=1 for a,b in edges):
        raise ValueError('La extrusión contiene bordes abiertos o geometría no manifold. STL cancelado.')
    volumen=0.
    for a,b,c in caras:
        p,q,r=vertices[a],vertices[b],vertices[c]
        volumen+=(p[0]*(q[1]*r[2]-q[2]*r[1])+
                  p[1]*(q[2]*r[0]-q[0]*r[2])+
                  p[2]*(q[0]*r[1]-q[1]*r[0]))/6.
    esperado=sum(x.area for x in solids)*grosor
    if volumen<=0 or abs(volumen-esperado)>max(.005,.002*esperado):
        raise ValueError('Volumen 3D incoherente; revisa contornos y agujeros.')
    # STL binario estándar: 80 bytes de cabecera + uint32 número de triángulos.
    data=bytearray(b'Vectorizador STL mm / extrusion experimental'.ljust(80,b' '))
    data+=struct.pack('<I',len(caras))
    for a,b,c in caras:
        p,q,r=vertices[a],vertices[b],vertices[c]
        ux,uy,uz=(q[i]-p[i] for i in range(3))
        vx,vy,vz=(r[i]-p[i] for i in range(3))
        normal=(uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx)
        norm=math.sqrt(sum(v*v for v in normal))
        n=tuple(v/norm for v in normal)
        data+=struct.pack('<12fH',*(n+p+q+r),0)
    bounds=(min(p[0] for p in vertices),min(p[1] for p in vertices),
            max(p[0] for p in vertices),max(p[1] for p in vertices))
    return bytes(data),{'piezas':len(solids),'triangulos':len(caras),'volumen_mm3':round(volumen,3),
                        'ancho_mm':round(bounds[2]-bounds[0],3),'alto_mm':round(bounds[3]-bounds[1],3),
                        'grosor_mm':float(grosor), 'compensacion_agujeros_mm':float(compensacion_agujeros),
                        'precision_stl':precision_stl, 'error_cuerda_mm':config['error_cuerda'],
                        'offset_exterior_mm':float(offset_exterior)}
