"""Motor CAD exclusivo DXF: coordenadas en milímetros, líneas y círculos reales."""
from __future__ import annotations
import io
import math
import numpy as np
import ezdxf
import cv2
from motor.precision import homografia_reglas, aplicar_homografia
from motor.marcadores_a4 import homografia_marcadores
from motor.arcos_cad import ajustar_tramos_cad
from motor.ranuras_cad import ajustar_capsula


def _validar_puntos(vector):
    loops=vector.get('contornos')
    if not isinstance(loops,list) or not loops or len(loops)>100:
        raise ValueError('Contornos inválidos.')
    for c in loops:
        p=np.asarray(c.get('puntos',[]),float)
        if p.ndim!=2 or p.shape[1]!=2 or len(p)<3 or len(p)>40000:
            raise ValueError('Contorno vacío o demasiado grande.')
        if not np.isfinite(p).all() or (np.abs(p)>1e6).any():
            raise ValueError('Coordenadas fuera de rango.')
        if c.get('tipo') not in ('exterior','interior'):
            raise ValueError('Tipo de contorno incorrecto.')


def _transformacion_affine(afin):
    if not isinstance(afin,dict):raise ValueError('Calibración afín inválida.')
    try:
        ori=np.asarray(afin['origen'],float)
        ax=np.asarray(afin['punto_x'],float)
        ay=np.asarray(afin['punto_y'],float)
        dx=float(afin['mm_x']);dy=float(afin['mm_y'])
    except (KeyError,ValueError,TypeError) as e:
        raise ValueError('Calibración afín incompleta.') from e
    if (ori.shape!=(2,) or ax.shape!=(2,) or ay.shape!=(2,) or
        not all(np.isfinite(v).all() for v in (ori,ax,ay)) or
        not 5<=dx<=250 or not 5<=dy<=250):
        raise ValueError('Calibración afín fuera de rango.')
    u=(ax-ori)/dx;v=(ay-ori)/dy
    mat=np.column_stack((u,v))
    if abs(float(np.linalg.det(mat)))<.1 or abs(float(u@v))/(np.linalg.norm(u)*np.linalg.norm(v))>.92:
        raise ValueError('Los puntos de calibración forman ejes inválidos.')
    return ori,np.linalg.inv(mat)


def _operador(sx,sy,afin=None,proyectiva=None):
    if proyectiva is not None:
        if afin is not None:raise ValueError('No combines dos calibraciones.')
        if isinstance(proyectiva,dict) and proyectiva.get('tipo')=='aruco_a4_v2':
            H,calidad=homografia_marcadores(proyectiva)
            def transformar(p):
                mm=cv2.perspectiveTransform(np.asarray(p,dtype=np.float64).reshape(-1,1,2),H).reshape(-1,2)
                if not np.isfinite(mm).all():raise ValueError('Coordenadas fuera de rango.')
                return np.column_stack((mm[:,0],-mm[:,1]))
            return transformar,calidad
        H,calidad=homografia_reglas(proyectiva)
        def transformar(p):return aplicar_homografia(p,H)
        return transformar,calidad
    if afin is not None:
        origen,inversa=_transformacion_affine(afin)
        def transformar(p):
            a=(np.asarray(p,dtype=float)-origen)@inversa.T
            return np.column_stack((-a[:,0],a[:,1]))
        return transformar,{'metodo':'afin'}
    if not (math.isfinite(sx) and math.isfinite(sy) and .1<sx<1000 and .1<sy<1000):
        raise ValueError('Escala no válida. Calibra la fotografía.')
    def transformar(p):
        a=np.asarray(p,dtype=float)
        return np.column_stack((a[:,0]/sx,-a[:,1]/sy))
    return transformar,{'metodo':'escala'}


def _forma_reconstruida(cont,transform,inicio,resumen):
    borde=cont.get('borde_px')
    if borde is not None and cont.get('puntos_px') is not None:
        arr=np.asarray(borde,float)
        if len(arr)>=12 and len(arr)<=20000:
            try:
                mm=transform(arr)-inicio
                puntos=ajustar_tramos_cad(cont['puntos_px'],borde,cont['puntos'],mm)
            except (ValueError,IndexError,TypeError,FloatingPointError,ArithmeticError):
                puntos=None
            if puntos:
                n=sum(abs(t[2])>.001 for t in puntos)
                resumen['arcos_cad']+=n
                resumen['tramos_rectos']+=len(puntos)-n
                return 'poly_bulge',puntos
    resumen['tramos_rectos']+=len(cont['puntos'])
    return 'poly',cont['puntos']


def geometria(vector,sx,sy,afin=None,proyectiva=None):
    _validar_puntos(vector)
    transform,calidad=_operador(sx,sy,afin,proyectiva)
    loops=[]
    for cont in vector['contornos']:
        p=transform(cont['puntos'])
        loops.append({'tipo':cont['tipo'],'puntos':p,'circulo':cont.get('circulo'),
                      'puntos_px':cont.get('puntos'), 'borde_px':cont.get('borde_px')})
    # normalizar a cuadrante positivo sin depender de la coordenada de la hoja
    puntos=np.concatenate([c['puntos'] for c in loops])
    inicio=puntos.min(axis=0)
    for c in loops:c['puntos']-=inicio
    resumen={'contornos_exteriores':0,'agujeros_polilinea':0,'agujeros_circulares':0,
             'arcos_cad':0, 'tramos_rectos':0, 'ranuras_cad':0,
             'calidad_calibracion':calidad}
    piezas=[]
    for c in loops:
        if c['tipo']=='exterior':
            piezas.append(('exterior',*_forma_reconstruida(c,transform,inicio,resumen)))
            resumen['contornos_exteriores']+=1
            continue
        circ=c.get('circulo')
        if circ:
            cp=np.asarray(circ['centro_px'],float)
            r=float(circ['radio_px'])
            if cp.shape==(2,) and np.isfinite(cp).all() and .2<r<500:
                angulos=np.linspace(0,2*np.pi,64,endpoint=False)
                foto=cp+np.column_stack((r*np.cos(angulos),r*np.sin(angulos)))
                mundo=transform(foto)-inicio
                centro=mundo.mean(axis=0)
                dist=np.linalg.norm(mundo-centro,axis=1)
                radio=float(dist.mean())
                # La proyección puede producir una elipse. No la llamaríamos
                # círculo si la dispersión angular de radios es relevante.
                if radio>.05 and float(np.std(dist)/radio)<.035:
                    piezas.append(('interior','circle',(centro,radio)))
                    resumen['agujeros_circulares']+=1
                    continue
                # Si no queda circular, se mantiene el borde curvo discretizado
                # con 64 segmentos, no se falsifica una primitiva CIRCLE.
                piezas.append(('interior','poly',mundo))
                resumen['agujeros_polilinea']+=1
                continue
        # Solo los interiores alargados que son verdaderas cápsulas se convierten
        # en ranuras CAD: ajuste sobre TODO el borde real ya calibrado.
        borde=c.get('borde_px')
        ajuste=None
        if borde is not None:
            try:ajuste=ajustar_capsula(transform(np.asarray(borde,float))-inicio)
            except (ValueError,ArithmeticError,FloatingPointError,np.linalg.LinAlgError):ajuste=None
        if ajuste is not None:
            vertices,validacion=ajuste
            piezas.append(('interior','poly_bulge',vertices))
            resumen['ranuras_cad']+=1
            resumen['arcos_cad']+=2
            resumen['tramos_rectos']+=2
        else:
            piezas.append(('interior',*_forma_reconstruida(c,transform,inicio,resumen)))
        resumen['agujeros_polilinea']+=1
    ancho=float(np.max(puntos[:,0])-np.min(puntos[:,0]))
    alto=float(np.max(puntos[:,1])-np.min(puntos[:,1]))
    if not (.01<ancho<10000 and .01<alto<10000):
        raise ValueError('Dimensiones del contorno fuera de rango.')
    resumen['dimensiones_mm']=[round(ancho,3),round(alto,3)]
    return piezas,resumen


def convertir_puntos(vector,sx,sy,afin=None,proyectiva=None):
    # Interfaz de compatibilidad con los ensayos previos.
    operaciones,_=geometria(vector,sx,sy,afin,proyectiva)
    return [(tipo,[(float(x),float(y)) for x,y in data])
            for tipo,clase,data in operaciones if clase in ('poly','poly_bulge')]


def dimensiones(vector,sx,sy,afin=None,proyectiva=None):
    return geometria(vector,sx,sy,afin,proyectiva)[1]['dimensiones_mm']


def dxf(vector,sx,sy,afin=None,proyectiva=None,sin_escala:bool=False):
    if sin_escala:
        # Pixel coordinates exported without inventing millimetres.
        formas,_=geometria(vector,1.0,1.0)
    else:
        formas,_=geometria(vector,sx,sy,afin,proyectiva)
    doc=ezdxf.new('R2010')
    doc.units=0 if sin_escala else 4
    doc.header['$INSUNITS']=0 if sin_escala else 4
    doc.layers.new('CONTORNO_EXTERIOR',dxfattribs={'color':7})
    doc.layers.new('AGUJEROS',dxfattribs={'color':3})
    space=doc.modelspace()
    for tipo,clase,coords in formas:
        layer='AGUJEROS' if tipo=='interior' else 'CONTORNO_EXTERIOR'
        if clase=='circle':
            centro,radio=coords
            space.add_circle((float(centro[0]),float(centro[1])),float(radio),dxfattribs={'layer':layer})
        else:
            space.add_lwpolyline(coords,format='xyb' if clase=='poly_bulge' else 'xy',
                                 close=True,dxfattribs={'layer':layer})
    if doc.audit().has_errors:
        raise ValueError('El archivo DXF generado presenta inconsistencias.')
    f=io.StringIO()
    doc.write(f)
    return f.getvalue().encode('utf-8')
