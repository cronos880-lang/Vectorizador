"""Contraste metrológico independiente: marco ArUco V2.1 frente al borde físico A4.

Nunca utiliza el tamaño de la pieza para ajustar la escala. Solo corrige la
homografía si la hoja entera presenta cuatro bordes coherentes y contrastados.
Ante cualquier duda devuelve la calibración previa sin alterarla.
"""
from __future__ import annotations
import copy
import cv2
import numpy as np

_A4_W, _A4_H = 210.0, 297.0


def _detectar_limites(imagen, H):
    """Muestrear perfiles del borde A4 rectificados en coordenadas mm."""
    pixels_per_mm = 4.0
    margen = 12.0
    escala = np.array([[pixels_per_mm, 0., margen*pixels_per_mm],
                       [0., pixels_per_mm, margen*pixels_per_mm],
                       [0., 0., 1.]], dtype=float)
    w, h = int(round((210+2*margen)*pixels_per_mm)), int(round((297+2*margen)*pixels_per_mm))
    rect = cv2.warpPerspective(imagen, escala@H, (w,h), flags=cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(0,0,0))
    # No confundir el borde artificial del recorte de una foto con el papel.
    validez = cv2.warpPerspective(np.full(imagen.shape[:2],255,np.uint8),escala@H,(w,h),
                                  flags=cv2.INTER_NEAREST,borderValue=0)
    lab = cv2.GaussianBlur(cv2.cvtColor(rect, cv2.COLOR_BGR2LAB).astype(np.float32),(5,5),0)
    peso = np.array([1., 1.5, 1.5],np.float32)
    sep = int(pixels_per_mm)

    def examinar_vertical(x_mm, ys):
        muestras=[]
        for y_mm in ys:
            row=int(round((y_mm+margen)*pixels_per_mm))
            center=int(round((x_mm+margen)*pixels_per_mm))
            left=center-int(7*pixels_per_mm)-4
            right=center+int(7*pixels_per_mm)+5
            pix=lab[row-1:row+2,left:right].mean(axis=0)
            grad=np.linalg.norm((pix[2*sep:]-pix[:-2*sep])*peso,axis=1)
            n=int(np.argmax(grad))
            pixel=left+sep+n
            coord=pixel/pixels_per_mm-margen
            válido=(pixel-12>=0 and pixel+12<w and
                    bool(validez[row,pixel-12]) and bool(validez[row,pixel+12]))
            muestras.append((coord,float(grad[n]) if válido else 0.))
        return muestras

    def examinar_horizontal(y_mm, xs):
        muestras=[]
        for x_mm in xs:
            col=int(round((x_mm+margen)*pixels_per_mm))
            center=int(round((y_mm+margen)*pixels_per_mm))
            top=center-int(7*pixels_per_mm)-4
            bottom=center+int(7*pixels_per_mm)+5
            pix=lab[top:bottom,col-1:col+2].mean(axis=1)
            grad=np.linalg.norm((pix[2*sep:]-pix[:-2*sep])*peso,axis=1)
            n=int(np.argmax(grad))
            pixel=top+sep+n
            coord=pixel/pixels_per_mm-margen
            válido=(pixel-12>=0 and pixel+12<h and
                    bool(validez[pixel-12,col]) and bool(validez[pixel+12,col]))
            muestras.append((coord,float(grad[n]) if válido else 0.))
        return muestras

    ys=np.arange(35,263,12)
    xs=np.arange(40,175,10)
    perfiles={
        'izquierda':examinar_vertical(0,ys),
        'derecha':examinar_vertical(210,ys),
        'arriba':examinar_horizontal(0,xs),
        'abajo':examinar_horizontal(297,xs),
    }
    limites={};informes={}
    for lado, datos in perfiles.items():
        pos=np.array([t[0] for t in datos]);contraste=np.array([t[1] for t in datos])
        centro=float(np.median(pos))
        buenos=(np.abs(pos-centro)<1.5)&(contraste>10)
        if buenos.sum()<int(np.ceil(.80*len(pos))):
            return None, f'Borde {lado} no contrastado en suficientes zonas.'
        med=float(np.median(pos[buenos]))
        dispersion=float(np.median(abs(pos[buenos]-med)))
        fuerza=float(np.median(contraste[buenos]))
        if dispersion>.8 or fuerza<18:
            return None,f'Borde {lado} disperso o sin suficiente contraste.'
        limites[lado]=med
        informes[lado]={'mm':round(med,3),'dispersión_mm':round(dispersion,3),
                        'contraste':round(fuerza,2),'puntos':int(buenos.sum())}
    # Las cuatro orillas deben estar aproximadamente donde predice ArUco.
    esperado={'izquierda':0.,'derecha':210.,'arriba':0.,'abajo':297.}
    if any(abs(limites[k]-esperado[k])>7.0 for k in limites):
        return None,'Los bordes detectados quedan demasiado lejos de la posición A4 esperada.'
    ancho=limites['derecha']-limites['izquierda']
    alto=limites['abajo']-limites['arriba']
    if not (195<ancho<225 and 278<alto<318):
        return None,'Dimensiones del papel incompatibles con A4.'
    factor_x=_A4_W/ancho
    factor_y=_A4_H/alto
    # Debe ser una corrección casi uniforme: otro resultado puede indicar
    # una sombra, pliegue o perspectiva insuficientemente explicada.
    if not (.94<factor_x<1.06 and .94<factor_y<1.06 and
            abs(factor_x-factor_y)<.006):
        return None,'Medidas de X/Y inconsistentes: no se aplicó corrección.'
    return {'ancho_mm':ancho,'alto_mm':alto,'factor_x':factor_x,'factor_y':factor_y,
            'limites':limites,'pruebas':informes},None


def verificar_y_corregir(imagen,cal):
    """Resultado (calibración, diagnóstico): nunca corrige si no hay pruebas."""
    if (not isinstance(cal,dict) or cal.get('estado')!='detectada' or
        cal.get('plantilla')!='V2.1' or cal.get('marcadores_encontrados')!=4 or
        not isinstance(cal.get('proyectiva_automatica'),dict)):
        return cal,{'estado':'no_aplicable','motivo':'Sin cuatro marcadores de plantilla V2.1.'}
    try:
        H=np.asarray(cal['proyectiva_automatica']['matriz'],float)
        if H.shape!=(3,3) or not np.isfinite(H).all():
            raise ValueError('Matriz de marcadores no válida.')
        prueba,problema=_detectar_limites(imagen,H)
        if prueba is None:
            return cal,{'estado':'no_aplicada','motivo':problema}
        fx,fy=prueba['factor_x'],prueba['factor_y']
        # La homografía se corrige de acuerdo con los cuatro bordes físicos.
        # El origen de la hoja se traslada coherentemente; el DXF usa luego
        # su propio origen local como en las versiones anteriores.
        x0=prueba['limites']['izquierda'];y0=prueba['limites']['arriba']
        ajuste=np.array([[fx,0.,-x0*fx],[0.,fy,-y0*fy],[0.,0.,1.]])
        Hn=ajuste@H
        Hn/=Hn[2,2]
        result=copy.deepcopy(cal)
        result['proyectiva_automatica']['matriz']=Hn.tolist()
        result['proyectiva_automatica']['origen_calibracion']='bordes_a4_con_aruco_v21'
        # Evitar metadatos contradictorios cuando se usan los mm manualmente.
        result['px_mm_x']=round(float(cal['px_mm_x'])/fx,6)
        result['px_mm_y']=round(float(cal['px_mm_y'])/fy,6)
        result['metodo']='aruco_v21_papel_a4_verificado'
        result['descripcion']=(f'Plantilla V2.1: A4 físico comprobado '
            f'({prueba["ancho_mm"]:.2f} × {prueba["alto_mm"]:.2f} mm según ArUco). '
            f'Corrección X {fx:.5f}, Y {fy:.5f}; verificación en Onshape recomendada.')
        result['control_papel_a4']={'estado':'corregida',
            'ancho_detectado_mm':round(prueba['ancho_mm'],3),
            'alto_detectado_mm':round(prueba['alto_mm'],3),
            'factor_x':round(fx,7),'factor_y':round(fy,7)}
        return result,{'estado':'corregida',**result['control_papel_a4']}
    except (ValueError, TypeError,cv2.error, np.linalg.LinAlgError) as exc:
        return cal,{'estado':'no_aplicada','motivo':str(exc)}
