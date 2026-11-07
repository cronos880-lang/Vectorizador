/* Vectorizador V2.5.1 experimental - medición métrica e inteligente del STL REAL.
   No modifica el CAD ni el STL. Recupera sus aristas exteriores y de
   agujeros directamente de las paredes verticales de la malla binaria. */
'use strict';
window.VectorizadorMedidorSTL = (()=>{
  const MAX_FACES=160000, EPS=1e-4;
  function extraerPerfil(buffer){
    if(!(buffer instanceof ArrayBuffer)||buffer.byteLength<134)throw Error('STL de medición vacío.');
    const v=new DataView(buffer),n=v.getUint32(80,true);
    if(n<1||n>MAX_FACES||buffer.byteLength!==84+n*50)throw Error('Formato STL incoherente.');
    let min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
    for(let i=0;i<n;i++)for(let j=0;j<3;j++)for(let k=0;k<3;k++){
      const val=v.getFloat32(84+i*50+12+j*12+k*4,true);
      if(!Number.isFinite(val))throw Error('STL contiene coordenadas inválidas.');
      min[k]=Math.min(min[k],val);max[k]=Math.max(max[k],val);
    }
    if(max[2]-min[2]<EPS)throw Error('El STL no tiene grosor medible.');
    const segmentos=[];
    for(let i=0;i<n;i++){
      const start=84+i*50;
      if(Math.abs(v.getFloat32(start+8,true))>0.0001)continue; // Solo paredes verticales.
      const top=[];
      for(let j=0;j<3;j++){
        const x=v.getFloat32(start+12+j*12,true),y=v.getFloat32(start+16+j*12,true),z=v.getFloat32(start+20+j*12,true);
        if(Math.abs(z-max[2])<EPS)top.push([x,y]);
      }
      if(top.length===2 && Math.hypot(top[0][0]-top[1][0],top[0][1]-top[1][1])>1e-8)
        segmentos.push([top[0],top[1]]);
    }
    if(!segmentos.length)throw Error('No se encontraron los límites medibles del STL.');
    return {segmentos,bounds:[min[0],min[1],max[0],max[1]],medidas:[max[0]-min[0],max[1]-min[1],max[2]-min[2]]};
  }
  // Detecta huecos sobre LAS PAREDES DEL STL VISIBLE, no sobre la fotografía.
  // Si un perfil no cumple criterios geométricos estrictos, se clasifica
  // como libre en lugar de atribuirle un diámetro o longitud ficticios.
  function areaAnillo(pts){
    let area=0;
    for(let i=0;i<pts.length;i++){
      const a=pts[i],b=pts[(i+1)%pts.length];area+=a[0]*b[1]-b[0]*a[1];
    }
    return area/2;
  }
  function dentro(p,pts){
    let ok=false;
    for(let i=0,j=pts.length-1;i<pts.length;j=i++){
      const a=pts[i],b=pts[j];
      if((a[1]>p[1])!==(b[1]>p[1]) && p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])ok=!ok;
    }
    return ok;
  }
  function reconstruirAnillos(segmentos){
    // Los dos puntos de cada pared comparten los mismos float32 en el STL.
    // Cuantización a 0,1 μm para protegernos de pequeñas diferencias.
    const key=p=>Math.round(p[0]*1e4)+','+Math.round(p[1]*1e4);
    const nodos=new Map(),aristas=[],duplicadas=new Set();
    const nodo=p=>{
      const k=key(p);if(!nodos.has(k))nodos.set(k,{p,edges:[]});return k;
    };
    for(const [a,b] of segmentos){
      const ka=nodo(a),kb=nodo(b);if(ka===kb)continue;
      const ek=ka<kb?ka+'|'+kb:kb+'|'+ka;
      if(duplicadas.has(ek))continue;
      duplicadas.add(ek);
      const idx=aristas.length;aristas.push([ka,kb]);
      nodos.get(ka).edges.push(idx);nodos.get(kb).edges.push(idx);
    }
    const usados=new Uint8Array(aristas.length),anillos=[];
    for(let start=0;start<aristas.length;start++){
      if(usados[start])continue;
      const [begin]=aristas[start];let curr=begin,idx=start,pts=[],cerrado=false;
      for(let iter=0;iter<=aristas.length;iter++){
        if(usados[idx])break;
        const v=nodos.get(curr);
        // En nudos con más o menos de dos aristas no se adivinan perfiles.
        if(!v || v.edges.length!==2)break;
        usados[idx]=1;pts.push(v.p);
        const [a,b]=aristas[idx];curr=a===curr?b:a;
        if(curr===begin){cerrado=true;break}
        const siguiente=nodos.get(curr);
        if(!siguiente || siguiente.edges.length!==2)break;
        idx=siguiente.edges.find(id=>!usados[id]);
        if(idx===undefined)break;
      }
      if(cerrado&&pts.length>=3&&Math.abs(areaAnillo(pts))>0.005)anillos.push(pts);
    }
    return anillos;
  }
  function ajustarCirculo(pts){
    if(pts.length<12)return null;
    const n=pts.length,mx=pts.reduce((s,p)=>s+p[0],0)/n,
      my=pts.reduce((s,p)=>s+p[1],0)/n;
    let xx=0,xy=0,yy=0,xz=0,yz=0;
    for(const p of pts){
      const x=p[0]-mx,y=p[1]-my,z=(x*x+y*y)/2;
      xx+=x*x;xy+=x*y;yy+=y*y;xz+=x*z;yz+=y*z;
    }
    const det=xx*yy-xy*xy;
    if(det<=1e-10)return null;
    const c=[mx+(xz*yy-yz*xy)/det,my+(yz*xx-xz*xy)/det];
    const dist=pts.map(p=>Math.hypot(p[0]-c[0],p[1]-c[1]));
    const r=dist.reduce((s,x)=>s+x,0)/n;
    if(r<0.2)return null;
    let errorMax=0,errorSuma=0;
    for(const d of dist){const e=Math.abs(d-r);errorMax=Math.max(errorMax,e);errorSuma+=e*e}
    const per=pts.reduce((s,p,i)=>s+Math.hypot(p[0]-pts[(i+1)%n][0],p[1]-pts[(i+1)%n][1]),0);
    const circularidad=4*Math.PI*Math.abs(areaAnillo(pts))/(per*per);
    if(errorMax>Math.max(.012,r*.0025)||Math.sqrt(errorSuma/n)>Math.max(.005,r*.0012)||circularidad<.975)return null;
    return {tipo:'circulo',centro:c,diametro:2*r};
  }
  function ajustarRanura(pts){
    if(pts.length<14)return null;
    const l=pts.map((p,i)=>{
      const q=pts[(i+1)%pts.length];return {a:p,b:q,len:Math.hypot(p[0]-q[0],p[1]-q[1])};
    }).sort((a,b)=>b.len-a.len);
    if(l.length<4 || l[0].len<.5)return null;
    let mejor=null;
    for(let i=0;i<Math.min(6,l.length);i++)for(let j=i+1;j<Math.min(8,l.length);j++){
      const e=l[i],f=l[j],d1=[(e.b[0]-e.a[0])/e.len,(e.b[1]-e.a[1])/e.len],
        d2=[(f.b[0]-f.a[0])/f.len,(f.b[1]-f.a[1])/f.len];
      if(Math.abs(d1[0]*d2[0]+d1[1]*d2[1])<.995)continue;
      if(Math.abs(e.len-f.len)>Math.max(.05,e.len*.08))continue;
      const e0=e.a,e1=e.b;
      const same=Math.hypot(e0[0]-f.a[0],e0[1]-f.a[1])+Math.hypot(e1[0]-f.b[0],e1[1]-f.b[1]);
      const other=Math.hypot(e0[0]-f.b[0],e0[1]-f.b[1])+Math.hypot(e1[0]-f.a[0],e1[1]-f.a[1]);
      const f0=same<other?f.a:f.b,f1=same<other?f.b:f.a;
      const c0=[(e0[0]+f0[0])/2,(e0[1]+f0[1])/2],c1=[(e1[0]+f1[0])/2,(e1[1]+f1[1])/2];
      const largoCentros=Math.hypot(c1[0]-c0[0],c1[1]-c0[1]);
      const radio=(Math.hypot(e0[0]-f0[0],e0[1]-f0[1])+Math.hypot(e1[0]-f1[0],e1[1]-f1[1]))/4;
      if(radio<.2||largoCentros<radio*.8)continue;
      const ux=(c1[0]-c0[0])/largoCentros,uy=(c1[1]-c0[1])/largoCentros;
      let max=0,sum=0,atEnds=[0,0],atSides=0;
      for(const p of pts){
        const x=p[0]-c0[0],y=p[1]-c0[1],t=x*ux+y*uy,perp=Math.abs(x*uy-y*ux);
        const dist=t<0?Math.hypot(x,y):t>largoCentros?Math.hypot(p[0]-c1[0],p[1]-c1[1]):perp;
        const error=Math.abs(dist-radio);max=Math.max(max,error);sum+=error*error;
        if(t< -radio*.2)atEnds[0]++;
        else if(t>largoCentros+radio*.2)atEnds[1]++;
        else atSides++;
      }
      const rms=Math.sqrt(sum/pts.length);
      if(atEnds[0]<3||atEnds[1]<3||atSides<2||max>Math.max(.025,radio*.012)||rms>Math.max(.012,radio*.006))continue;
      const candidato={tipo:'ranura',centro:[(c0[0]+c1[0])/2,(c0[1]+c1[1])/2],
        ancho:radio*2,largo:largoCentros+radio*2,angulo:Math.atan2(uy,ux)*180/Math.PI,score:rms};
      if(!mejor||candidato.score<mejor.score)mejor=candidato;
    }
    if(mejor)delete mejor.score;
    return mejor;
  }
  function analizarHuecos(perfil){
    const anillos=reconstruirAnillos(perfil.segmentos),huecos=[];
    for(let i=0;i<anillos.length;i++){
      const pts=anillos[i];let depth=0;
      for(let j=0;j<anillos.length;j++){
        if(j!==i&&dentro(pts[0],anillos[j]))depth++;
      }
      if(depth%2!==1)continue;
      const forma=ajustarCirculo(pts)||ajustarRanura(pts)||{tipo:'libre'};
      huecos.push({...forma,puntos:pts,area:Math.abs(areaAnillo(pts))});
    }
    huecos.sort((a,b)=>Math.max(...b.puntos.map(p=>p[1]))-Math.max(...a.puntos.map(p=>p[1])) ||
      Math.min(...a.puntos.map(p=>p[0]))-Math.min(...b.puntos.map(p=>p[0])));
    huecos.forEach((h,i)=>{h.id=i+1});
    return huecos;
  }

  function abrir(canvas){
    const ctx=canvas.getContext('2d');if(!ctx)throw Error('No se puede abrir el plano de medición.');
    let original=null,actual=null,puntos=[],hover=null,arrastre=null,zoom=1,dx=0,dy=0,destruido=false,comparar=true;
    let modo='puntos',huecos=[],seleccionados=[],resaltar=null;
    let onHole=()=>{};
    let w=0,h=0,scale=1,cx=0,cy=0;
    let onMeasure=()=>{};
    function coord(p){return [cx+(p[0]+dx)*scale,cy-(p[1]+dy)*scale]}
    function inverse(px,py){return [(px-cx)/scale-dx,(cy-py)/scale-dy]}
    function actualizarTransform(){
      const b=actual?.bounds;if(!b)return;
      const both=comparar&&original?original.bounds:b;
      const loX=Math.min(b[0],both[0]),loY=Math.min(b[1],both[1]),hiX=Math.max(b[2],both[2]),hiY=Math.max(b[3],both[3]);
      const rx=Math.max(hiX-loX,0.5),ry=Math.max(hiY-loY,0.5);
      // Encuadre automatico REAL en funcion de la geometria y del tamano del lienzo.
      // Reservamos sitio para la cabecera flotante, las cotas y los botones inferiores.
      // El margen se calcula en pixeles de pantalla, no en milimetros del modelo.
      const margenIzq=Math.min(100,Math.max(36,w*0.12));
      const margenDer=Math.min(115,Math.max(55,w*0.13));
      // Si el texto de cabecera o las acciones flotantes ocupan mas espacio
      // (pantallas estrechas, etiquetas en varias lineas), respetar su altura REAL.
      const lienzo=canvas.getBoundingClientRect();
      const cabecera=canvas.parentElement?.querySelector('.stl-plan-head')?.getBoundingClientRect();
      const pie=canvas.parentElement?.querySelector('.stl-plan-footer')?.getBoundingClientRect();
      const supNecesario=cabecera?Math.max(0,cabecera.bottom-lienzo.top)+18:0;
      const infNecesario=pie?Math.max(0,lienzo.bottom-pie.top)+28:0;
      const margenSup=Math.min(h*0.43,Math.max(40,h*0.18,supNecesario));
      const margenInf=Math.min(h*0.43,Math.max(38,h*0.11,infNecesario));
      const anchoUtil=Math.max(1,w-margenIzq-margenDer);
      const altoUtil=Math.max(1,h-margenSup-margenInf);
      const base=Math.min(anchoUtil/rx,altoUtil/ry);
      const centroX=(margenIzq+w-margenDer)/2;
      const centroY=(margenSup+h-margenInf)/2;
      scale=base*zoom;
      cx=centroX-(loX+hiX)/2*scale;
      cy=centroY+(loY+hiY)/2*scale;
    }
    function texto(s,x,y,color='#e0e9f8',size=12){ctx.font=`${size}px system-ui, sans-serif`;ctx.textAlign='center';ctx.fillStyle=color;ctx.fillText(s,x,y)}
    function trazar(s,color,dash=[],lineWidth=1.5){
      if(!s)return;ctx.strokeStyle=color;ctx.lineWidth=lineWidth;ctx.setLineDash(dash);ctx.beginPath();
      for(const seg of s.segmentos){const a=coord(seg[0]),b=coord(seg[1]);ctx.moveTo(...a);ctx.lineTo(...b)}
      ctx.stroke();ctx.setLineDash([]);
    }
    function escalaLabel(){
      const b=actual.bounds;const a=coord([b[0],b[1]]),z=coord([b[2],b[3]]);
      const y=Math.max(19,Math.min(h-7,Math.max(a[1],z[1])+19));
      const x=Math.min(w-8,Math.max(8,(a[0]+z[0])/2));
      texto(actual.medidas[0].toFixed(2)+' mm',x,y,'#9adbd8');
      ctx.save();ctx.translate(Math.min(w-12,Math.max(12,Math.max(a[0],z[0])+23)),(a[1]+z[1])/2);ctx.rotate(-Math.PI/2);
      texto(actual.medidas[1].toFixed(2)+' mm',0,0,'#9adbd8');ctx.restore();
    }
    function pintar(){
      if(destruido)return;
      const dpr=Math.min(2,window.devicePixelRatio||1);
      const ww=Math.max(1,Math.round(canvas.clientWidth*dpr)),hh=Math.max(1,Math.round(canvas.clientHeight*dpr));
      if(canvas.width!==ww||canvas.height!==hh){canvas.width=ww;canvas.height=hh}
      ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#091524';ctx.fillRect(0,0,ww,hh);
      ctx.setTransform(dpr,0,0,dpr,0,0);w=ww/dpr;h=hh/dpr;
      if(!actual)return;
      actualizarTransform();
      // Retícula tenue cada 10 mm, con cantidad acotada.
      const bound=actual.bounds,unit=Math.pow(10,Math.ceil(Math.log10(28/Math.max(1e-6,scale))));
      const lo=inverse(0,h),hi=inverse(w,0);
      ctx.strokeStyle='#203449';ctx.lineWidth=1;ctx.beginPath();
      for(let xx=Math.ceil(lo[0]/unit)*unit,k=0;xx<hi[0]&&k<80;xx+=unit,k++){
        const pt=coord([xx,0]);ctx.moveTo(pt[0],0);ctx.lineTo(pt[0],h);
      }
      for(let yy=Math.ceil(lo[1]/unit)*unit,k=0;yy<hi[1]&&k<80;yy+=unit,k++){
        const pt=coord([0,yy]);ctx.moveTo(0,pt[1]);ctx.lineTo(w,pt[1]);
      }
      ctx.stroke();
      if(comparar&&original)trazar(original,'#a3abb9',[5,5],1.3);
      trazar(actual,'#45d4c9',[],1.9);
      escalaLabel();
      if(modo==='agujeros'){
        for(const hole of huecos){
          const elegido=seleccionados.includes(hole),hovered=resaltar===hole;
          if(!elegido&&!hovered)continue;
          ctx.save();ctx.beginPath();
          hole.puntos.forEach((p,i)=>{const [x,y]=coord(p);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y)});
          ctx.closePath();ctx.fillStyle=elegido?'#f7c86e35':'#f7c86e18';ctx.fill();
          ctx.strokeStyle=elegido?'#ffd483':'#d5a465';ctx.lineWidth=elegido?3:2;ctx.stroke();ctx.restore();
        }
        for(let i=0;i<seleccionados.length;i++){
          const hole=seleccionados[i];if(!hole.centro)continue;
          const [x,y]=coord(hole.centro);
          ctx.strokeStyle=i===0?'#ffd483':'#ff908a';ctx.lineWidth=1.6;ctx.beginPath();
          ctx.moveTo(x-6,y);ctx.lineTo(x+6,y);ctx.moveTo(x,y-6);ctx.lineTo(x,y+6);ctx.stroke();
          texto('H'+hole.id,x+17,y-10,i===0?'#ffd483':'#ff908a');
        }
        if(seleccionados.length===2&&seleccionados.every(x=>x.centro)){
          const [a,b]=seleccionados.map(x=>coord(x.centro));
          ctx.strokeStyle='#ffcd78';ctx.lineWidth=1.8;ctx.setLineDash([5,4]);ctx.beginPath();
          ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();ctx.setLineDash([]);
          const A=seleccionados[0].centro,B=seleccionados[1].centro;
          texto('≈ '+Math.hypot(A[0]-B[0],A[1]-B[1]).toFixed(3)+' mm',(a[0]+b[0])/2,(a[1]+b[1])/2-11,'#ffd483');
        }
        return;
      }
      if(hover){const p=coord(hover);ctx.beginPath();ctx.arc(p[0],p[1],4,0,Math.PI*2);ctx.fillStyle='#f7c86e';ctx.fill()}
      puntos.forEach((p,i)=>{const a=coord(p);ctx.beginPath();ctx.arc(a[0],a[1],5,0,Math.PI*2);ctx.fillStyle=i===0?'#ffd483':'#ff908a';ctx.fill();texto(i===0?'A':'B',a[0]+14,a[1]-12,'#fceac6')});
      if(puntos.length===2){const a=coord(puntos[0]),b=coord(puntos[1]);ctx.beginPath();ctx.setLineDash([4,3]);ctx.strokeStyle='#ffc676';ctx.lineWidth=2;ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();ctx.setLineDash([]);
        const d=Math.hypot(puntos[0][0]-puntos[1][0],puntos[0][1]-puntos[1][1]);
        const xx=(a[0]+b[0])/2,yy=(a[1]+b[1])/2-14;
        texto(d.toFixed(3)+' mm',xx,yy,'#f6db9c');
      }
    }
    function local(e){const r=canvas.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top]}
    function nearest(x,y){
      if(!actual)return null;
      const p=inverse(x,y);let best=null,bestD=Infinity;
      // El cursor se ajusta a las aristas reales del STL, incluso agujeros.
      for(const [a,b] of actual.segmentos){
        const ux=b[0]-a[0],uy=b[1]-a[1],len=ux*ux+uy*uy;
        const t=Math.max(0,Math.min(1,((p[0]-a[0])*ux+(p[1]-a[1])*uy)/len));
        const q=[a[0]+t*ux,a[1]+t*uy],d=Math.hypot(p[0]-q[0],p[1]-q[1])*scale;
        if(d<bestD){best=q;bestD=d}
      }
      return bestD<=14?best:null;
    }
    function down(e){
      if(e.button!==0&&e.button!==1)return;
      const [x,y]=local(e);arrastre={id:e.pointerId,x,y,moved:false,pan:e.button===1||e.shiftKey};canvas.setPointerCapture(e.pointerId);
    }
    function move(e){
      const [x,y]=local(e);
      if(arrastre?.id===e.pointerId){
        const moved=Math.hypot(x-arrastre.x,y-arrastre.y)>1.5;
        if(arrastre.pan){dx+=(x-arrastre.x)/scale;dy-=(y-arrastre.y)/scale;}
        arrastre={...arrastre,x,y,moved:arrastre.moved||moved};
      }
      if(modo==='agujeros'){
        const p=inverse(x,y);resaltar=huecos.filter(h=>dentro(p,h.puntos)).sort((a,b)=>a.area-b.area)[0]||null;
        hover=null;
      } else {hover=nearest(x,y);resaltar=null}
      pintar();
    }
    function up(e){
      if(!arrastre||arrastre.id!==e.pointerId)return;
      const a=arrastre;arrastre=null;
      if(e.button===0&&!a.pan&&!a.moved){
        const [x,y]=local(e),p=nearest(x,y);
        if(modo==='agujeros'){
          const real=inverse(x,y);
          const hole=huecos.filter(h=>dentro(real,h.puntos)).sort((a,b)=>a.area-b.area)[0];
          if(hole){
            if(seleccionados.length===2)seleccionados=[];
            if(seleccionados.includes(hole))seleccionados=seleccionados.filter(v=>v!==hole);
            else seleccionados.push(hole);
            onHole(seleccionados,huecos);
          }
        }else if(p){if(puntos.length===2)puntos=[];puntos.push(p);onMeasure(puntos)}
      }
      pintar();
    }
    function wheel(e){e.preventDefault();const [x,y]=local(e),before=inverse(x,y);zoom=Math.max(.3,Math.min(30,zoom*Math.exp(-e.deltaY*.001)));actualizarTransform();const after=inverse(x,y);dx+=after[0]-before[0];dy+=after[1]-before[1];pintar()}
    function reset(){zoom=1;dx=0;dy=0;pintar()}
    function cambiar(originalBuffer,actualBuffer){
      if(originalBuffer)original=extraerPerfil(originalBuffer);
      actual=extraerPerfil(actualBuffer);
      huecos=analizarHuecos(actual);seleccionados=[];resaltar=null;
      puntos=[];onMeasure([]);onHole([],huecos);pintar();
      return {original,actual};
    }
    function limpiar(){puntos=[];seleccionados=[];resaltar=null;onMeasure([]);onHole([],huecos);pintar()}
    function cambiarModo(nuevo){
      if(nuevo!=='agujeros'&&nuevo!=='puntos')return;
      modo=nuevo;limpiar();
    }
    function mostrarOriginal(on){comparar=!!on;pintar()}
    canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',move);
    canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);
    canvas.addEventListener('wheel',wheel,{passive:false});canvas.addEventListener('dblclick',reset);
    canvas.addEventListener('contextmenu',e=>e.preventDefault());window.addEventListener('resize',pintar);
    const observador=typeof ResizeObserver==='function'?new ResizeObserver(()=>pintar()):null;
    observador?.observe(canvas);
    return {cambiar,limpiar,reset,mostrarOriginal,extraerPerfil,repintar:pintar,cambiarModo,
      set onMeasure(cb){onMeasure=cb},
      set onHole(cb){onHole=cb},
      destruir(){destruido=true;canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',move);
        canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',up);
        canvas.removeEventListener('wheel',wheel);canvas.removeEventListener('dblclick',reset);window.removeEventListener('resize',pintar);
        observador?.disconnect();}
    };
  }
  return {abrir,extraerPerfil,analizarHuecos,reconstruirAnillos,ajustarCirculo,ajustarRanura};
})();
