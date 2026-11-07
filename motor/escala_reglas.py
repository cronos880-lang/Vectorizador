"""Lectura alternativa de reglas de 1 cm próximas a dos ejes impresos.

Sin posiciones fijas: localiza líneas base y una retícula perpendicular de marcas;
los resultados se rechazan cuando no hay cadencia y calidad verificables.
No calcula perspectiva ni garantiza medidas físicas exactas.
"""
from __future__ import annotations
import cv2
import numpy as np


def _clusters(items, max_gap=5):
    # Hough puede producir varios bordes de la misma raya: fusionar en grupos.
    groups=[]
    for x,length in sorted(items):
        if groups and x-groups[-1][-1][0]<=max_gap:
            groups[-1].append((float(x),float(length)))
        else:
            groups.append([(float(x),float(length))])
    return [(float(np.median([v for v,_ in group])),float(max(s for _,s in group))) for group in groups]


def _lattice(points, prior=None):
    """Ajusta centímetros completos, penalizando medias marcas de 5 mm."""
    if len(points)<5:return None
    arr=np.array(points,float)
    pos,lens=arr.T
    strong=lens>=max(35.0, float(np.percentile(lens,85))*.73)
    if np.count_nonzero(strong)<4:
        strong=lens>=np.percentile(lens,67)
    sp=pos[strong]
    if len(sp)<4:return None
    proposals=[]
    if prior is not None:
        proposals.extend(np.linspace(prior*.89,prior*1.11,90))
    else:
        for i in range(len(sp)):
            for j in range(i+1,len(sp)):
                distance=sp[j]-sp[i]
                for n in range(1,16):
                    p=distance/n
                    if 34.0<=p<=230.0:proposals.append(p)
    if not proposals:return None
    solutions=[]
    for p in proposals:
        best=None
        for seed in sp:
            k=np.rint((pos-seed)/p).astype(int)
            residual=np.abs(pos-seed-k*p)
            match=residual<max(4.0,.057*p)
            strong_hits=np.count_nonzero(match & strong)
            n=np.unique(k[match]).size
            if strong_hits<3 or n<5:continue
            score=(strong_hits,n,-np.median(residual[match]),p)
            if best is None or score>best[0]:best=(score,k,match)
        if best is None:continue
        _,k,match=best
        if np.ptp(k[match])<5:continue
        try:
            slope,intercept=np.polyfit(k[match],pos[match],1,w=np.sqrt(lens[match]))
        except np.linalg.LinAlgError:continue
        if not (abs(slope-p)/p<.065):continue
        rms=float(np.sqrt(np.mean((slope*k[match]+intercept-pos[match])**2)))
        if rms>max(2.8,.032*p):continue
        # Fit with all points on grid; avoid aliasing half-centimetre ticks.
        residual=np.abs(pos-(intercept+np.rint((pos-intercept)/slope)*slope))
        strong_ok=(residual<max(4.0,.052*p))&strong
        ns=int(np.count_nonzero(strong_ok))
        if ns<4:continue
        ratio=ns/max(1,int(strong.sum()))
        # Count strong marks first, prefer larger spacing among aliases.
        solutions.append((ns,round(ratio,3),-rms,round(slope,5),rms, int(np.count_nonzero(match)),float(slope)))
    if not solutions:return None
    # Prefer large true centimetre spacing when two harmonics explain equally
    # many long marks. This defeats a frequent 5mm/10mm ambiguity.
    max_strong=max(s[0] for s in solutions)
    solutions=[s for s in solutions if s[0]>=max_strong-1]
    solutions.sort(key=lambda s:(s[1],s[0],s[6],s[2]),reverse=True)
    best=solutions[0]
    return {'periodo_px_cm':round(float(best[6]),4),'marcas':best[5],
            'marcas_fuertes':best[0],'error_px':round(best[4],3)}


def calibracion_reglas_generica(imagen,bbox=None):
    fail={'estado':'no_fiable','metodo':'reglas_sin_reticula',
          'descripcion':'No se identificó una secuencia fiable de marcas de 1 cm.',
          'px_mm_x':None,'px_mm_y':None,'afin_automatica':None}
    gray=cv2.cvtColor(imagen,cv2.COLOR_BGR2GRAY)
    h,w=gray.shape;unit=min(h,w)
    edges=cv2.Canny(gray,50,150)
    large=cv2.HoughLinesP(edges,1,np.pi/360,threshold=65,
                         minLineLength=max(120,round(unit*.16)),maxLineGap=14)
    if large is None:return fail
    # Baselines H/V en cualquier cuadrante: debe haber una intersección
    # geométrica cercana y gran longitud en ambos ejes.
    hb=[];vb=[]
    for x1,y1,x2,y2 in large[:,0]:
        dx,dy=abs(x2-x1),abs(y2-y1)
        if dx>.38*unit and dy<=max(6,dx*.045):
            hb.append((dx,(y1+y2)/2,min(x1,x2),max(x1,x2)))
        if dy>.38*unit and dx<=max(6,dy*.045):
            vb.append((dy,(x1+x2)/2,min(y1,y2),max(y1,y2)))
    if not hb or not vb:return fail
    # Longest baselines can be paper borders or ruler guides; use closest
    # physically intersecting pair whose ticks can be validated afterwards.
    hb=sorted(hb,reverse=True)[:15];vb=sorted(vb,reverse=True)[:20]
    candidates=[]
    for _,hy,xmin,xmax in hb[:8]:
        for _,vx,ymin,ymax in vb[:12]:
            if (xmin-.26*unit<=vx<=xmax+.26*unit and ymin-.26*unit<=hy<=ymax+.26*unit and
                0<=vx<w and 0<=hy<h):
                candidates.append((hy,vx))
    if not candidates:return fail
    ticks=cv2.HoughLinesP(edges,1,np.pi/360,threshold=18,
                         minLineLength=max(27,round(unit*.026)),maxLineGap=7)
    if ticks is None:return fail
    seen=set()
    for hy,vx in candidates:
        # Avoid expensive repeated Hough candidate comparisons.
        key=(round(hy/15),round(vx/15))
        if key in seen:continue
        seen.add(key)
        raw_x,raw_y=[],[]
        for x1,y1,x2,y2 in ticks[:,0]:
            dx,dy=abs(x2-x1),abs(y2-y1)
            mx=(x1+x2)/2;my=(y1+y2)/2
            if (dx<max(4,dy*.045) and dy>=unit*.029 and
                min(abs(y1-hy),abs(y2-hy))<unit*.045 and abs(mx-vx)>unit*.085 and
                abs(mx-vx)<unit*1.0):
                raw_x.append((mx,dy))
            if (dy<max(4,dx*.045) and dx>=unit*.029 and
                min(abs(x1-vx),abs(x2-vx))<unit*.045 and abs(my-hy)>unit*.085 and
                abs(my-hy)<unit*1.0):
                raw_y.append((my,dx))
        # Distance from spine may be in either direction; avoid spurious
        # patterns on the far side by evaluating both sides separately.
        for xsign in (-1,1):
            for ysign in (-1,1):
                xs=_clusters([(p,l) for p,l in raw_x if (p-vx)*xsign>0])
                ys=_clusters([(p,l) for p,l in raw_y if (p-hy)*ysign>0])
                xfit=_lattice(xs)
                if not xfit or xfit['marcas_fuertes']<4:continue
                yfit=_lattice(ys,prior=xfit['periodo_px_cm'])
                if yfit is None or yfit['marcas']<5:continue
                px=xfit['periodo_px_cm']/10
                py=yfit['periodo_px_cm']/10
                if (not(.8<px<50 and .8<py<50) or
                    abs(px-py)/max(px,py)>.22):continue
                confidence=(xfit['marcas_fuertes']+yfit['marcas_fuertes'],
                            xfit['marcas']+yfit['marcas'])
                details={'estado':'estimada','metodo':'reticula_reglas_1cm',
                    'descripcion':'Marcas de 1 cm reconocidas en ambos ejes. Escala estimada sin corregir perspectiva; comprueba dimensiones.',
                    'px_mm_x':round(px,5),'px_mm_y':round(py,5),'afin_automatica':None,
                    'calidad':{'eje_x':xfit,'eje_y':yfit}}
                if 'best' not in locals() or confidence>best[0]:best=(confidence,details)
    return best[1] if 'best' in locals() else fail
