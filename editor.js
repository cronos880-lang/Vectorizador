/* Vectorizador V2.0.17 - puntos medios, escuadras y medición CAD. */
'use strict';
const cad={active:false,entities:[],original:[],units:'mm',tool:'select',selected:null,selectedSegment:null,selectedSegments:[],selectedIds:[],handle:null,snap:null,angleSnap:null,lastJoints:[],pendingJoints:[],measure:{mode:"points",start:null,end:null,entityId:null,result:""},
 view:{s:1,x:0,y:0},undo:[],redo:[],draft:null,mouse:null,drag:null,panning:null,
 photo:{zoom:1,panX:0,panY:0}, dirty:false, initialized:false,
 bg:{visible:false,opacity:.45,image:null,bounds:null,loading:false}};
const cadCopy=v=>JSON.parse(JSON.stringify(v));
const cadEl=id=>document.getElementById(id);
const cadToggleDisplay=(id,val)=>{cadEl(id).style.display=val?'':'none'};

async function cadIniciar(){
 if(!state.vector||state.busy)return;
 state.busy=true;buttons();
 try {
  if(!cad.initialized){
   const r=await fetch('/api/editor/iniciar',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({...payload(),sin_escala:!ready()})});
   const doc=await r.json();if(!r.ok)throw Error(doc.detail||'No se puede abrir el editor');
   cad.entities=cadCopy(doc.entidades);cad.original=cadCopy(doc.entidades);
   cad.units=doc.unidades;cad.undo=[];cad.redo=[];cad.draft=null;cad.drag=null;cad.selected=null;
   cad.dirty=false;cad.selectedSegment=null;cad.selectedSegments=[];cad.selectedIds=[];cad.snap=null;cad.angleSnap=null;cad.lastJoints=[];cad.pendingJoints=[];cad.photo={zoom:state.zoom,panX:state.panX,panY:state.panY};
   cad.tool='select';cad.view.s=1;cad.initialized=true;
   cad.bg={visible:false,opacity:.45,image:null,bounds:null,loading:false};
   cadEl('cadPhotoVisible').checked=false;cadEl('cadPhotoOpacity').value='45';
   cadEl('cadPhotoPct').textContent='45 %';
   cadEl('cadPhotoInfo').textContent='Opcional: fotografía alineada al plano CAD, no incluida en el DXF.';
  }
  cad.active=true;
  cadEl('cadbar').style.display='flex';cadEl('cadPanel').style.display='block';cadEl('vectorPanel').style.display='none';
  cadEl('cadToggle').textContent='Salir del editor';
  cadEl('viewPill').textContent=cad.units==='mm'?'Plano en mm':'Plano sin calibrar';
  cadSetTool('select');cadFit();cadRefresh();redraw();
 }catch(e){error('No se pudo iniciar el editor: '+e.message);cad.active=false;}
 finally{state.busy=false;buttons();}
}
function cadSalir(){
 if(!cad.active)return;
 cad.active=false;cad.draft=null;cad.drag=null;
 cadEl('cadbar').style.display='none';cadEl('cadPanel').style.display='none';cadEl('vectorPanel').style.display='block';
 cadEl('cadToggle').textContent='Editar CAD';
 cadEl('viewPill').textContent=cad.dirty?'Vista automática · CAD editado pendiente de exportar':'Contornos automáticos · DXF';
 state.zoom=cad.photo.zoom;state.panX=cad.photo.panX;state.panY=cad.photo.panY;
 cv.classList.remove('calibrating');cadRefresh();redraw();
}
function cadDisable(){
 cad.active=false;cad.initialized=false;cad.entities=[];cad.original=[];cad.undo=[];cad.redo=[];
 cad.selected=null;cad.selectedSegment=null;cad.selectedSegments=[];cad.selectedIds=[];cad.snap=null;cad.angleSnap=null;cad.lastJoints=[];cad.pendingJoints=[];cad.dirty=false;cad.drag=null;cad.draft=null;
 cad.bg={visible:false,opacity:.45,image:null,bounds:null,loading:false};
 cadEl('cadbar').style.display='none';cadEl('cadPanel').style.display='none';cadEl('vectorPanel').style.display='block';
 cadEl('cadToggle').textContent='Editar CAD';cv.classList.remove('calibrating');
}
async function cadFondoActivar(visible){
 cad.bg.visible=visible;
 if(!visible){redraw();return}
 if(cad.bg.image){redraw();return}
 if(cad.bg.loading||!state.file){cadEl('cadPhotoVisible').checked=false;return}
 cad.bg.loading=true;
 cadEl('cadPhotoInfo').textContent='Corrigiendo perspectiva y alineando fotografía...';
 try{
  const fd=new FormData();fd.append('archivo',state.file);
  fd.append('datos',JSON.stringify({...payload(),sin_escala:!ready()}));
  const r=await fetch('/api/editor/fondo',{method:'POST',body:fd});
  const d=await r.json();if(!r.ok)throw Error(d.detail||'No se puede alinear el fondo');
  const img=new Image();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('PNG de fondo inválido'));img.src=d.fondo_png});
  if(!cad.initialized)return;
  cad.bg.image=img;cad.bg.bounds=d.limites_cad;
  cadEl('cadPhotoInfo').textContent='Fotografía alineada con el DXF · solo visualización.';
 }catch(e){cad.bg.visible=false;cadEl('cadPhotoVisible').checked=false;cadEl('cadPhotoInfo').textContent='No se pudo alinear. Se mantiene el CAD sin fondo.';error(e.message)}
 finally{cad.bg.loading=false;redraw()}
}
function cadSnapshot(){cad.undo.push(cadCopy(cad.entities));if(cad.undo.length>80)cad.undo.shift();cad.redo=[];cad.dirty=true;}
function cadDeshacer(){if(!cad.undo.length)return;cad.redo.push(cadCopy(cad.entities));cad.entities=cad.undo.pop();cad.selected=null;cad.selectedSegment=null;cad.selectedSegments=[];cad.selectedIds=[];cad.snap=null;cad.angleSnap=null;cad.lastJoints=[];cad.pendingJoints=[];cad.dirty=true;cadRefresh();redraw()}
function cadRehacer(){if(!cad.redo.length)return;cad.undo.push(cadCopy(cad.entities));cad.entities=cad.redo.pop();cad.selected=null;cad.selectedSegment=null;cad.selectedSegments=[];cad.selectedIds=[];cad.snap=null;cad.angleSnap=null;cad.lastJoints=[];cad.pendingJoints=[];cad.dirty=true;cadRefresh();redraw()}
function cadSeleccion(){return cad.entities.find(e=>e.id===cad.selected)}
// Borrado múltiple: todos los cambios se guardan en una única entrada de Deshacer.
function cadBorrar(){
 if(cad.selectedSegments.length){cadBorrarTramos();return}
 const ids=cad.selectedIds.length?cad.selectedIds:(cad.selected===null?[]:[cad.selected]);
 if(!ids.length)return;
 cadSnapshot();cad.lastJoints=[];const remove=new Set(ids);
 cad.entities=cad.entities.filter(e=>!remove.has(e.id));
 cad.selected=null;cad.selectedIds=[];cad.selectedSegment=null;cad.selectedSegments=[];
 cadRefresh();redraw();
}
function cadRestaurar(){if(!confirm('¿Restaurar todos los contornos originales? Se perderán las ediciones actuales.'))return;
 cadSnapshot();cad.lastJoints=[];cad.entities=cadCopy(cad.original);cad.selected=null;cad.selectedSegment=null;cad.selectedSegments=[];cad.selectedIds=[];cadRefresh();cadFit()}
function cadSetTool(t){if(!['select','segment','line','circle','arc','curve','rectangle','pan','measure'].includes(t))return;
 cad.tool=t;cad.draft=null;cad.drag=null;cad.snap=null;cad.angleSnap=null;cad.pendingJoints=[];cad.selectedSegment=null;cad.selectedSegments=[];cad.selected=null;cad.selectedIds=[];
 for(const b of document.querySelectorAll('[data-cad-tool]'))b.classList.toggle('active',b.dataset.cadTool===t);
 cadEl('cadMode').textContent={select:'Seleccionar y editar',segment:'Marcar varios tramos; pulsar Borrar para eliminarlos juntos',line:'Línea: marca los dos extremos',circle:'Círculo: centro y radio',arc:'Arco 3P: marca el primer extremo',curve:'Curva: marca el punto inicial',rectangle:'Rectángulo: dos esquinas',pan:'Mover vista: arrastrar',measure:'Medir: distancia entre puntos o dimensiones de una entidad'}[t];
 cadEl('cadMeasurePanel').style.display=t==='measure'?'block':'none';if(t==='measure')cadMeasureReset(false);
 cadEl('view').classList.toggle('calibrating',t!=='select'&&t!=='pan'&&t!=='measure');cadRefresh();redraw();}
function cadBounds(padded=true){
 let l=Infinity,r=-Infinity,b=Infinity,t=-Infinity;
 const add=(x,y)=>{l=Math.min(l,x);r=Math.max(r,x);b=Math.min(b,y);t=Math.max(t,y)};
 for(const e of cad.entities){
  if(e.tipo==='circle'){add(e.cx-e.radio,e.cy-e.radio);add(e.cx+e.radio,e.cy+e.radio)}
  if(e.tipo==='polyline'||e.tipo==='arc'||e.tipo==='curve')for(const v of cadPathPoints(e))add(v[0],v[1]);
  if(e.tipo==='line'||e.tipo==='rectangle'){add(...e.a);add(...e.b)}
 }
 if(!isFinite(l))return{l:0,r:100,b:0,t:70};
 const pad=padded?Math.max(2,Math.max(r-l,t-b)*.1):0;return{l:l-pad,r:r+pad,b:b-pad,t:t+pad};
}
function cadBoundsRaw(){return cadBounds(false)}
function cadFit(){if(!cad.active)return;const v=cadBounds(),dpr=devicePixelRatio||1;
 const left=70*dpr,right=310*dpr,top=50*dpr,bot=50*dpr;
 const w=Math.max(200,cv.width-left-right),h=Math.max(200,cv.height-top-bot);
 cad.view.s=Math.min(w/Math.max(.1,v.r-v.l),h/Math.max(.1,v.t-v.b));
 const midX=(left+cv.width-right)/2,midY=(top+cv.height-bot)/2;
 cad.view.x=midX-(v.l+v.r)/2*cad.view.s;
 cad.view.y=midY+(v.b+v.t)/2*cad.view.s;redraw();}
function cadAt(x,y){return[(x-cad.view.x)/cad.view.s,(cad.view.y-y)/cad.view.s]}
function cadScreen(p){return[cad.view.x+p[0]*cad.view.s,cad.view.y-p[1]*cad.view.s]}
function cadCanvasPos(e){const r=cv.getBoundingClientRect(),dpr=devicePixelRatio||1;return[(e.clientX-r.left)*dpr,(e.clientY-r.top)*dpr]}
function cadDistanceSegment(q,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;
 const f=den>0?Math.max(0,Math.min(1,((q[0]-a[0])*dx+(q[1]-a[1])*dy)/den)):0;
 return Math.hypot(q[0]-a[0]-dx*f,q[1]-a[1]-dy*f)}
function cadSampleArc(a,b,bulge){
 const dx=b[0]-a[0],dy=b[1]-a[1],d=Math.hypot(dx,dy);
 if(d<1e-9||Math.abs(bulge)<1e-7)return[[a[0],a[1]],[b[0],b[1]]];
 const cx=(a[0]+b[0])/2-dy*(1-bulge*bulge)/(4*bulge);
 const cy=(a[1]+b[1])/2+dx*(1-bulge*bulge)/(4*bulge);
 const theta=4*Math.atan(bulge),start=Math.atan2(a[1]-cy,a[0]-cx),rad=d*(1+bulge*bulge)/(4*Math.abs(bulge));
 const n=Math.max(12,Math.min(96,Math.ceil(Math.abs(theta)*rad*cad.view.s/8)));
 return Array.from({length:n+1},(_,i)=>[cx+rad*Math.cos(start+theta*i/n),cy+rad*Math.sin(start+theta*i/n)]);
}
// Arco exacto por inicio, punto de paso y extremo: mismo convenio DXF CCW.
function cadArcGeometry(a,via,b){
 if(!a||!via||!b)return null;
 const ux=via[0]-a[0],uy=via[1]-a[1],vx=b[0]-a[0],vy=b[1]-a[1];
 const det=2*(ux*vy-uy*vx),scale=Math.max(Math.hypot(ux,uy),Math.hypot(vx,vy),Math.hypot(b[0]-via[0],b[1]-via[1]));
 if(scale<.001||Math.abs(det)<=2e-6*scale*scale)return null;
 const u2=ux*ux+uy*uy,v2=vx*vx+vy*vy;
 const cx=a[0]+(u2*vy-v2*uy)/det,cy=a[1]+(v2*ux-u2*vx)/det;
 const r=Math.hypot(a[0]-cx,a[1]-cy);
 if(![cx,cy,r].every(Number.isFinite)||r<.01||r>10000||Math.abs(cx)>20000||Math.abs(cy)>20000)return null;
 const mod=t=>(t%(Math.PI*2)+Math.PI*2)%(Math.PI*2);
 const angle=p=>mod(Math.atan2(p[1]-cy,p[0]-cx));
 let start=angle(a),end=angle(b),mid=angle(via);
 if(mod(mid-start)>=mod(end-start)) {[start,end]=[end,start];}
 return{cx,cy,r,start,sweep:mod(end-start)};
}
function cadArcPoints(a,via,b){
 const g=cadArcGeometry(a,via,b);if(!g)return[a,via,b];
 const n=Math.max(16,Math.min(240,Math.ceil(g.sweep*g.r*cad.view.s/6)));
 return Array.from({length:n+1},(_,i)=>[g.cx+g.r*Math.cos(g.start+g.sweep*i/n),g.cy+g.r*Math.sin(g.start+g.sweep*i/n)]);
}
// Curva Bezier cúbica exacta; al guardar se codifica como DXF SPLINE clamped degree=3.
function cadCurvePoints(a,c1,c2,b){
 const length=Math.hypot(c1[0]-a[0],c1[1]-a[1])+Math.hypot(c2[0]-c1[0],c2[1]-c1[1])+Math.hypot(b[0]-c2[0],b[1]-c2[1]);
 const n=Math.max(32,Math.min(240,Math.ceil(length*cad.view.s/6)));
 return Array.from({length:n+1},(_,i)=>{
  const t=i/n,v=1-t,w0=v*v*v,w1=3*v*v*t,w2=3*v*t*t,w3=t*t*t;
  return [w0*a[0]+w1*c1[0]+w2*c2[0]+w3*b[0], w0*a[1]+w1*c1[1]+w2*c2[1]+w3*b[1]];
 });
}
function cadPathPoints(e){
 if(e.tipo==='circle')return Array.from({length:97},(_,i)=>[e.cx+e.radio*Math.cos(i*Math.PI/48),e.cy+e.radio*Math.sin(i*Math.PI/48)]);
 if(e.tipo==='line')return[e.a,e.b];
 if(e.tipo==='arc')return cadArcPoints(e.a,e.paso,e.b);
 if(e.tipo==='curve')return cadCurvePoints(e.a,e.c1,e.c2,e.b);
 if(e.tipo==='rectangle'){const a=e.a,b=e.b;return[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]],[a[0],a[1]]]}
 if(e.tipo==='polyline'){
  const p=[],vs=e.vertices,n=e.cerrada?vs.length:vs.length-1;
  for(let i=0;i<n;i++){const a=vs[i],b=vs[(i+1)%vs.length],seg=cadSampleArc(a,b,a[2]);if(i)seg.shift();p.push(...seg)}
  if(!e.cerrada&&vs.length>1)p.push(vs[vs.length-1].slice(0,2));return p;
 }
 return[];
}
function cadHitEntity(q){const tol=10/(cad.view.s||1);let best=null,dist=tol;
 for(let i=cad.entities.length-1;i>=0;i--){let d=Infinity,e=cad.entities[i];
  if(e.tipo==='circle')d=Math.abs(Math.hypot(q[0]-e.cx,q[1]-e.cy)-e.radio);
  else{const p=cadPathPoints(e);for(let k=1;k<p.length;k++)d=Math.min(d,cadDistanceSegment(q,p[k-1],p[k]));}
  if(d<dist){dist=d;best=e.id}
 }return best}

// Segmentos individuales, incluyendo arcos con bulge: suprimir uno no borra el contorno entero.
function cadNearestSegment(q){
 const tol=11/(cad.view.s||1);let best=null,dist=tol;
 for(let k=cad.entities.length-1;k>=0;k--){const e=cad.entities[k];
  if(e.tipo==='polyline'){
   const vs=e.vertices,n=e.cerrada?vs.length:vs.length-1;
   for(let i=0;i<n;i++){
    const curve=cadSampleArc(vs[i],vs[(i+1)%vs.length],vs[i][2]||0);
    for(let j=1;j<curve.length;j++){
     const d=cadDistanceSegment(q,curve[j-1],curve[j]);
     if(d<dist){dist=d;best={id:e.id,index:i}}
    }
   }
  }else if(e.tipo==='line'||e.tipo==='arc'||e.tipo==='curve'||e.tipo==='rectangle'){
   const pts=cadPathPoints(e);
   for(let i=1;i<pts.length;i++){
    const d=cadDistanceSegment(q,pts[i-1],pts[i]);
    if(d<dist){dist=d;best={id:e.id,index:e.tipo==='rectangle'?Math.floor((i-1)/Math.max(1,(pts.length-1)/4)):0}}
   }
  }
 }return best;
}
function cadSegmentEndpoints(e,index){
 if(e.tipo==='polyline'){
  const a=e.vertices[index],b=e.vertices[(index+1)%e.vertices.length];
  return cadSampleArc(a,b,a[2]||0)
 }
 if(e.tipo==='rectangle'){const pts=cadPathPoints(e);return [pts[index],pts[index+1]]}
 return cadPathPoints(e);
}
// Reconstruye polilíneas ABIERTAS a partir de segmentos conservados, sin alterar vértices o bulges de arcos restantes.
function cadTramosConservados(e,borrados){
 let vertices=e.tipo==='polyline'?e.vertices.map(v=>[...v]):[];
 if(e.tipo==='rectangle'){
  const a=e.a,b=e.b;
  vertices=[[a[0],a[1],0],[b[0],a[1],0],[b[0],b[1],0],[a[0],b[1],0]];
 }
 const closed=e.tipo==='rectangle'||e.cerrada;
 const n=vertices.length, total=closed?n:n-1;
 if(total<=0)return[];
 const ids=Array.from({length:total},(_,i)=>i);
 // Al abrir un ciclo, iniciar justo DESPUÉS de una arista eliminada.
 if(closed){const cut=ids.find(i=>borrados.has(i));if(cut!==undefined){ids.splice(0,ids.length,...Array.from({length:total},(_,j)=>(cut+1+j)%total));}}
 const paths=[];let current=[];
 function flush(){if(current.length>=2){current[current.length-1][2]=0;paths.push(current)}current=[]}
 for(const i of ids){
  if(borrados.has(i)){flush();continue}
  const a=vertices[i],b=vertices[(i+1)%n];
  if(!current.length)current=[[...a]];
  current.push([...b]);
 }
 flush();return paths;
}
function cadBorrarTramos(){
 if(!cad.selectedSegments.length)return;
 const byId=new Map();
 for(const sel of cad.selectedSegments){if(!byId.has(sel.id))byId.set(sel.id,new Set());byId.get(sel.id).add(sel.index)}
 cadSnapshot();cad.lastJoints=[];
 const updated=[];let suffix=0;
 for(const e of cad.entities){
  const cuts=byId.get(e.id);if(!cuts){updated.push(e);continue}
  if(e.tipo==='polyline'||e.tipo==='rectangle'){
   const paths=cadTramosConservados(e,cuts);
   paths.forEach((vs,i)=>updated.push({id:i===0?e.id:`${e.id}-parte-${++suffix}-${Date.now().toString(36)}`,
       tipo:'polyline',capa:e.capa,cerrada:false,vertices:vs}));
  }else{
   // Una LINE, ARC o SPLINE es un único tramo: eliminar la entidad.
  }
 }
 cad.entities=updated;
 cad.selectedSegment=null;cad.selectedSegments=[];cad.selected=null;cad.selectedIds=[];
 cadEl('cadMode').textContent='Tramos borrados. Puedes crear nuevas líneas o arcos ajustados a sus extremos.';
 cadRefresh();redraw();
}
// Imantado CAD: primero vértices y extremos, después el punto MÁS CERCANO
// sobre rectas, polilíneas, arcos analíticos, círculos y curvas Bézier.
// El punto devuelto se usa directamente al CREAR la entidad (no solo al pintar).
function cadClosestSegment(q,a,b){
 const dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy;
 const t=den>1e-18?Math.max(0,Math.min(1,((q[0]-a[0])*dx+(q[1]-a[1])*dy)/den)):0;
 const point=[a[0]+t*dx,a[1]+t*dy];return{point,dist:Math.hypot(q[0]-point[0],q[1]-point[1])};
}
function cadClosestCircleAngle(q,cx,cy,r,start,sweep){
 const pi2=2*Math.PI,mod=a=>(a%pi2+pi2)%pi2;
 const angle=Math.atan2(q[1]-cy,q[0]-cx);
 let t=mod(angle-start);
 if(t>sweep){const a=[cx+r*Math.cos(start),cy+r*Math.sin(start)];
  const b=[cx+r*Math.cos(start+sweep),cy+r*Math.sin(start+sweep)];
  return Math.hypot(q[0]-a[0],q[1]-a[1])<Math.hypot(q[0]-b[0],q[1]-b[1])?{point:a}:{point:b};
 }
 return{point:[cx+r*Math.cos(angle),cy+r*Math.sin(angle)]};
}
function cadClosestBulge(q,a,b,bulge){
 if(Math.abs(bulge)<1e-10)return cadClosestSegment(q,a,b);
 const dx=b[0]-a[0],dy=b[1]-a[1],chord=Math.hypot(dx,dy);
 if(chord<1e-10)return cadClosestSegment(q,a,b);
 const cx=(a[0]+b[0])/2-dy*(1-bulge*bulge)/(4*bulge);
 const cy=(a[1]+b[1])/2+dx*(1-bulge*bulge)/(4*bulge);
 const r=chord*(1+bulge*bulge)/(4*Math.abs(bulge));
 const theta=4*Math.atan(bulge);
 const angleA=Math.atan2(a[1]-cy,a[0]-cx),start=theta>0?angleA:angleA+theta;
 const point=cadClosestCircleAngle(q,cx,cy,r,start,Math.abs(theta)).point;
 return{point,dist:Math.hypot(q[0]-point[0],q[1]-point[1])};
}
function cadBezierPoint(e,t){
 const u=1-t;return[0,1].map(k=>u*u*u*e.a[k]+3*u*u*t*e.c1[k]+3*u*t*t*e.c2[k]+t*t*t*e.b[k]);
}
function cadClosestBezier(q,e){
 let best=0,dist=Infinity;
 for(let i=0;i<=64;i++){const t=i/64,p=cadBezierPoint(e,t),d=Math.hypot(q[0]-p[0],q[1]-p[1]);if(d<dist){dist=d;best=t}}
 let lo=Math.max(0,best-1/64),hi=Math.min(1,best+1/64);
 for(let i=0;i<32;i++){
  const t1=lo+(hi-lo)/3,t2=hi-(hi-lo)/3;
  const p1=cadBezierPoint(e,t1),p2=cadBezierPoint(e,t2);
  const d1=(q[0]-p1[0])**2+(q[1]-p1[1])**2,d2=(q[0]-p2[0])**2+(q[1]-p2[1])**2;
  if(d1<d2)hi=t2;else lo=t1;
 }
 const point=cadBezierPoint(e,(lo+hi)/2);return{point,dist:Math.hypot(q[0]-point[0],q[1]-point[1])};
}
function cadClosestOnEntity(q,e){
 let best=null,dist=Infinity;
 const consider=v=>{if(!v||!v.point)return;const d=v.dist??Math.hypot(q[0]-v.point[0],q[1]-v.point[1]);if(d<dist){dist=d;best={point:v.point,dist:d}}};
 if(e.tipo==='line')consider(cadClosestSegment(q,e.a,e.b));
 else if(e.tipo==='circle'){
  const a=Math.atan2(q[1]-e.cy,q[0]-e.cx),point=[e.cx+e.radio*Math.cos(a),e.cy+e.radio*Math.sin(a)];consider({point});
 }else if(e.tipo==='arc'){
  const g=cadArcGeometry(e.a,e.paso,e.b);if(g)consider(cadClosestCircleAngle(q,g.cx,g.cy,g.r,g.start,g.sweep));
 }else if(e.tipo==='curve')consider(cadClosestBezier(q,e));
 else if(e.tipo==='rectangle'){
  const a=e.a,b=e.b,vs=[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]]];
  for(let i=0;i<4;i++)consider(cadClosestSegment(q,vs[i],vs[(i+1)%4]));
 }else if(e.tipo==='polyline'){
  const n=e.cerrada?e.vertices.length:e.vertices.length-1;
  for(let i=0;i<n;i++)consider(cadClosestBulge(q,e.vertices[i],e.vertices[(i+1)%e.vertices.length],e.vertices[i][2]||0));
 }
 return best;
}
// Puntos medios reales por segmento: no se añaden al DXF ni se divide la geometría.
function cadMidpoints(e){
 const out=[];
 const midpoint=(a,b)=>[(a[0]+b[0])/2,(a[1]+b[1])/2];
 const push=(p)=>{if(p&&p.every(Number.isFinite))out.push(p)};
 if(e.tipo==='line')push(midpoint(e.a,e.b));
 else if(e.tipo==='rectangle'){
  const a=e.a,b=e.b,v=[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]]];
  for(let i=0;i<4;i++)push(midpoint(v[i],v[(i+1)%4]));
 }else if(e.tipo==='polyline'){
  const n=e.cerrada?e.vertices.length:e.vertices.length-1;
  for(let i=0;i<n;i++){
   const a=e.vertices[i],b=e.vertices[(i+1)%e.vertices.length],bulge=a[2]||0;
   if(Math.abs(bulge)<1e-10)push(midpoint(a,b));
   else{
    const dx=b[0]-a[0],dy=b[1]-a[1],chord=Math.hypot(dx,dy);
    if(chord<1e-10)continue;
    const cx=(a[0]+b[0])/2-dy*(1-bulge*bulge)/(4*bulge);
    const cy=(a[1]+b[1])/2+dx*(1-bulge*bulge)/(4*bulge);
    const r=chord*(1+bulge*bulge)/(4*Math.abs(bulge));
    const ang=Math.atan2(a[1]-cy,a[0]-cx)+2*Math.atan(bulge);
    push([cx+r*Math.cos(ang),cy+r*Math.sin(ang)]);
   }
  }
 }else if(e.tipo==='arc'){
  const g=cadArcGeometry(e.a,e.paso,e.b);
  if(g)push([g.cx+g.r*Math.cos(g.start+g.sweep/2),g.cy+g.r*Math.sin(g.start+g.sweep/2)]);
 }else if(e.tipo==='curve')push(cadBezierPoint(e,.5));
 return out;
}
function cadSnapPoint(q,excludeId=null){
 const tol=12*(devicePixelRatio||1)/(cad.view.s||1);
 const vertexTol=8*(devicePixelRatio||1)/(cad.view.s||1);
 const midTol=10*(devicePixelRatio||1)/(cad.view.s||1);
 let nearVertex=null,vertexDist=vertexTol,nearMid=null,midDist=midTol,nearTrace=null,traceDist=tol;
 const vertex=(p,label,id)=>{const d=Math.hypot(q[0]-p[0],q[1]-p[1]);
  if(d<vertexDist){vertexDist=d;nearVertex={point:[p[0],p[1]],label,id,kind:'vertice'}};
 };
 for(const e of cad.entities){if(e.id===excludeId)continue;
  if(e.tipo==='polyline'){for(const p of e.vertices)vertex(p,'Vértice',e.id);}
  else if(['line','arc','curve'].includes(e.tipo)){
   vertex(e.a,'Extremo',e.id);vertex(e.b,'Extremo',e.id);
  }else if(e.tipo==='rectangle'){
   const a=e.a,b=e.b;
   for(const p of [[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]]])vertex(p,'Esquina',e.id);
  }else if(e.tipo==='circle'){
   if(cad.tool==='circle'||cad.tool==='measure')vertex([e.cx,e.cy],'Centro',e.id);
  }
  for(const p of cadMidpoints(e)){
   const d=Math.hypot(q[0]-p[0],q[1]-p[1]);
   if(d<midDist){midDist=d;nearMid={point:p,label:'Punto medio',id:e.id,kind:'medio'}};
  }
  const c=cadClosestOnEntity(q,e);
  if(c&&c.dist<traceDist){traceDist=c.dist;nearTrace={point:c.point,label:e.tipo==='circle'?'Sobre círculo':e.tipo==='arc'?'Sobre arco':e.tipo==='curve'?'Sobre curva':'Sobre línea',id:e.id,kind:'trazado'}};
 }
 return nearVertex||nearMid||nearTrace;
}
// Escuadra respecto a rectas existentes que pasan por el primer extremo.
function cadRectasEnPunto(origin){
 const dirs=[],eps=Math.max(1e-6,1.6/(cad.view.s||1));
 const check=(a,b)=>{
  const seg=cadClosestSegment(origin,a,b),len=Math.hypot(b[0]-a[0],b[1]-a[1]);
  if(seg.dist>eps||len<.005)return;
  const ux=(b[0]-a[0])/len,uy=(b[1]-a[1])/len;
  if(!dirs.some(d=>Math.abs(d[0]*ux+d[1]*uy)>.9999))dirs.push([ux,uy]);
 };
 for(const e of cad.entities){
  if(e.tipo==='line')check(e.a,e.b);
  else if(e.tipo==='rectangle'){
   const a=e.a,b=e.b,vs=[[a[0],a[1]],[b[0],a[1]],[b[0],b[1]],[a[0],b[1]]];
   for(let i=0;i<4;i++)check(vs[i],vs[(i+1)%4]);
  }else if(e.tipo==='polyline'){
   const n=e.cerrada?e.vertices.length:e.vertices.length-1;
   for(let i=0;i<n;i++){
    const a=e.vertices[i],b=e.vertices[(i+1)%e.vertices.length];
    if(Math.abs(a[2]||0)<1e-10)check(a,b);
   }
  }
 }
 return dirs;
}
function cadResolverPunto(q){
 const snap=cadSnapPoint(q,cad.drag?.base?.id||null);
 const chosen=snap?snap.point:q;
 let angle=null;
 if(cad.tool==='line'&&cad.draft&&cad.draft.first){
  const a=cad.draft.first,tol=10*(devicePixelRatio||1)/(cad.view.s||1);
  let best=null,score=Infinity;
  for(const d of cadRectasEnPunto(a)){
   const perp=[-d[1],d[0]],r=[chosen[0]-a[0],chosen[1]-a[1]];
   const along=r[0]*perp[0]+r[1]*perp[1],off=Math.abs(r[0]*d[0]+r[1]*d[1]);
   if(Math.abs(along)*cad.view.s<8*(devicePixelRatio||1)||off>tol||off>=score)continue;
   score=off;best={point:[a[0]+perp[0]*along,a[1]+perp[1]*along],origin:a.slice(),dir:d};
  }
  if(best){
   // No romper uniones que ya son exactas: preferencia de extremos/vértices.
   if(snap&&['vertice','medio'].includes(snap.kind)){
    if(score<.00001)angle={...best,point:chosen.slice()};
   }else if(!snap||snap.kind==='trazado')angle=best;
  }
 }
 if(angle)return{point:angle.point,snap:(!snap||snap.kind==='trazado')?null:snap,angle};
 return{point:chosen,snap,angle:null};
}
function cadConfirmarUniones(){
 cad.lastJoints=cad.pendingJoints.map(v=>({point:v.point.slice(),label:v.label}));
 cad.pendingJoints=[];
 if(cad.lastJoints.length){
  cadEl('cadJoinStatus').textContent='✓ '+cad.lastJoints.length+' unión(es) CAD exacta(s)';
  cadEl('cadJoinStatus').style.display='block';
 }else{cadEl('cadJoinStatus').textContent='';cadEl('cadJoinStatus').style.display='none'}
}
function cadHitHandle(q){const e=cadSeleccion();if(!e)return null;
 const tol=10/(cad.view.s||1),pairs=[];
 if(e.tipo==='circle')pairs.push(['center',[e.cx,e.cy]],['radius',[e.cx+e.radio,e.cy]]);
 if(e.tipo==='line'||e.tipo==='rectangle')pairs.push(['a',e.a],['b',e.b]);
 if(e.tipo==='arc')pairs.push(['a',e.a],['paso',e.paso],['b',e.b]);
 if(e.tipo==='curve')pairs.push(['a',e.a],['c1',e.c1],['c2',e.c2],['b',e.b]);
 if(e.tipo==='polyline')e.vertices.forEach((v,i)=>pairs.push([i,v]));
 for(const [handle,p] of pairs)if(Math.hypot(q[0]-p[0],q[1]-p[1])<=tol)return handle;
 return null}
function cadMove(ent,dx,dy){
 if(ent.tipo==='circle'){ent.cx+=dx;ent.cy+=dy}
 else if(ent.tipo==='polyline'){for(const v of ent.vertices){v[0]+=dx;v[1]+=dy}}
 else if(ent.tipo==='arc'||ent.tipo==='curve'){for(const p of (ent.tipo==='arc'?[ent.a,ent.paso,ent.b]:[ent.a,ent.c1,ent.c2,ent.b])){p[0]+=dx;p[1]+=dy}}
 else{for(const p of [ent.a,ent.b]){p[0]+=dx;p[1]+=dy}}
}
function cadEditHandle(ent,handle,q){
 if(ent.tipo==='circle'){
  if(handle==='center'){ent.cx=q[0];ent.cy=q[1]}
  else ent.radio=Math.max(.01,Math.hypot(q[0]-ent.cx,q[1]-ent.cy));
 } else if(ent.tipo==='polyline'&&Number.isInteger(handle)){
  const n=ent.vertices.length;
  ent.vertices[handle][0]=q[0];ent.vertices[handle][1]=q[1];
  // Al mover un vértice de una primitiva curva, no fingir que sigue siendo el mismo arco.
  ent.vertices[handle][2]=0;
  ent.vertices[(handle-1+n)%n][2]=0;
 } else if(ent.tipo==='curve'&&['a','c1','c2','b'].includes(handle)){
  ent[handle]=q.slice();
 } else if(ent.tipo==='arc'&&['a','paso','b'].includes(handle)){
  const previous=ent[handle];ent[handle]=q.slice();
  if(!cadArcGeometry(ent.a,ent.paso,ent.b))ent[handle]=previous;
 } else if((ent.tipo==='line'||ent.tipo==='rectangle')&&(handle==='a'||handle==='b')){
  ent[handle]=q.slice();
 }
}
function cadGrid(ctx){const {s,x,y}=cad.view;
 ctx.fillStyle='#101720';ctx.fillRect(0,0,cv.width,cv.height);
 const dpr=devicePixelRatio||1,major=10;
 if(s>.8){ctx.save();
  const grid=s>12?1:10,spacing=s*grid;
  if(spacing>10){
   ctx.lineWidth=1*dpr;ctx.strokeStyle='#293646';ctx.beginPath();
   const x0=((x%spacing)+spacing)%spacing,y0=((y%spacing)+spacing)%spacing;
   for(let xx=x0;xx<cv.width;xx+=spacing){ctx.moveTo(xx,0);ctx.lineTo(xx,cv.height)}
   for(let yy=y0;yy<cv.height;yy+=spacing){ctx.moveTo(0,yy);ctx.lineTo(cv.width,yy)}ctx.stroke();
  }ctx.restore()}

}
// Mediciones informativas: leen entidades CAD y nunca modifican el DXF.
function cadMedidaNumero(x){return Number(x).toFixed(3)}
function cadMedirEntidad(e){
 const u=cad.units==='mm'?'mm':'px',length=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
 const polyLen=vs=>{let n=0;for(let i=1;i<vs.length;i++)n+=length(vs[i-1],vs[i]);return n};
 if(e.tipo==='line')return`Línea · longitud ${cadMedidaNumero(length(e.a,e.b))} ${u}`;
 if(e.tipo==='circle')return`Círculo · Ø ${cadMedidaNumero(2*e.radio)} ${u}`;
 if(e.tipo==='rectangle')return`Rectángulo · ancho ${cadMedidaNumero(Math.abs(e.b[0]-e.a[0]))} ${u} · alto ${cadMedidaNumero(Math.abs(e.b[1]-e.a[1]))} ${u} · perímetro ${cadMedidaNumero(2*(Math.abs(e.b[0]-e.a[0])+Math.abs(e.b[1]-e.a[1])))} ${u}`;
 if(e.tipo==='arc'){
  const g=cadArcGeometry(e.a,e.paso,e.b);return g?`Arco · longitud ${cadMedidaNumero(g.r*g.sweep)} ${u} · radio ${cadMedidaNumero(g.r)} ${u} · ángulo ${cadMedidaNumero(g.sweep*180/Math.PI)}°`:'Arco sin medición válida';
 }
 if(e.tipo==='polyline'){
  const vs=e.vertices,n=e.cerrada?vs.length:vs.length-1;let l=0;
  for(let i=0;i<n;i++){
   const a=vs[i],b=vs[(i+1)%vs.length],c=length(a,b),bulge=a[2]||0;
   l+=Math.abs(bulge)<1e-12?c:(c*(1+bulge*bulge)/(4*Math.abs(bulge)))*Math.abs(4*Math.atan(bulge));
  }
  return`Contorno · ${e.vertices.length} vértices · L ${cadMedidaNumero(l)} ${u}`;
 }
 if(e.tipo==='curve')return`Curva SPLINE · longitud aprox. ${cadMedidaNumero(polyLen(Array.from({length:401},(_,i)=>cadBezierPoint(e,i/400))))} ${u}`;
 return'Geometría no medible';
}
function cadMeasureReset(redrawCanvas=true){
 cad.measure={mode:cadEl('cadMeasureMode')?.value||'points',start:null,end:null,entityId:null,result:''};
 cadEl('cadMeasureResult').textContent='Selecciona dos puntos o una entidad, según el modo.';
 if(redrawCanvas)redraw();
}
function cadMeasureClick(raw){
 const m=cad.measure;
 if(m.mode==='entity'){
  const id=cadHitEntity(raw);
  if(id){const e=cad.entities.find(x=>x.id===id);m.entityId=id;m.start=null;m.end=null;m.result=cadMedirEntidad(e);}
  else {m.entityId=null;m.result='No hay geometría bajo el cursor.';}
 }else{
  const p=cadSnapPoint(raw)?.point||raw;
  if(!m.start||m.end){m.start=p.slice();m.end=null;m.entityId=null;m.result='Primer punto fijado. Marca el segundo.';}
  else{m.end=p.slice();const dx=m.end[0]-m.start[0],dy=m.end[1]-m.start[1],d=Math.hypot(dx,dy),u=cad.units==='mm'?'mm':'px';
   m.result=`Distancia ${cadMedidaNumero(d)} ${u}`;
  }
 }
 cadEl('cadMeasureResult').textContent=m.result;redraw();
}
function cadMedirCambiarModo(){cadMeasureReset();}
function cadDraw(){const dpr=devicePixelRatio||1;cadGrid(ctx);
 if(cad.bg.visible&&cad.bg.image&&cad.bg.bounds){
  const [xmin,ymin,xmax,ymax]=cad.bg.bounds;
  ctx.save();ctx.globalAlpha=cad.bg.opacity;
  ctx.translate(cad.view.x,cad.view.y);ctx.scale(cad.view.s,-cad.view.s);
  ctx.scale(1,-1);ctx.drawImage(cad.bg.image,xmin,-ymax,xmax-xmin,ymax-ymin);
  ctx.restore();
 }
 ctx.save();ctx.translate(cad.view.x,cad.view.y);ctx.scale(cad.view.s,-cad.view.s);
 ctx.lineWidth=Math.max(1.8*dpr/cad.view.s,.007);ctx.lineJoin='round';ctx.lineCap='round';
 for(const e of cad.entities){const pts=cadPathPoints(e);if(!pts.length)continue;
  ctx.strokeStyle=cad.selectedIds.includes(e.id)?'#f6c36e':e.capa==='AGUJEROS'?'#78bbff':e.capa==='DIBUJO'?'#d3a5fe':'#61e1ad';
  ctx.beginPath();ctx.moveTo(pts[0][0],pts[0][1]);for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i][0],pts[i][1]);
  if(e.tipo==='polyline'&&e.cerrada)ctx.closePath();ctx.stroke();
 }
 if(cad.draft){const p=cad.draft.first,q=cad.mouse||p;
  ctx.setLineDash([5/cad.view.s,5/cad.view.s]);ctx.strokeStyle='#eacb71';ctx.beginPath();
  if(cad.tool==='curve'){
   const points=[...(cad.draft.points||[p]),q];
   if(points.length===2){ctx.moveTo(...points[0]);ctx.lineTo(...points[1]);}
   else if(points.length===3){ctx.moveTo(...points[0]);ctx.quadraticCurveTo(...points[1],...points[2]);}
   else {ctx.moveTo(...points[0]);ctx.bezierCurveTo(...points[1],...points[2],...points[3]);}
  }else if(cad.tool==='arc'){
   const pts=cad.draft.points||[p];
   const samples=pts.length===2?cadArcPoints(pts[0],q,pts[1]):[pts[0],q];
   ctx.moveTo(...samples[0]);for(let i=1;i<samples.length;i++)ctx.lineTo(...samples[i]);
  }
  else if(cad.tool==='circle'){ctx.arc(p[0],p[1],Math.hypot(p[0]-q[0],p[1]-q[1]),0,Math.PI*2)}
  else if(cad.tool==='rectangle')ctx.rect(Math.min(p[0],q[0]),Math.min(p[1],q[1]),Math.abs(q[0]-p[0]),Math.abs(q[1]-p[1]));
  else{ctx.moveTo(...p);ctx.lineTo(...q)}ctx.stroke();ctx.setLineDash([]);
 }
 // Los vértices permanecen visibles también cuando hay selección múltiple.
 for(const id of cad.selectedIds){const sel=cad.entities.find(e=>e.id===id);if(!sel)continue;
  const handles=[];
  if(sel.tipo==='circle')handles.push([sel.cx,sel.cy],[sel.cx+sel.radio,sel.cy]);
  if(sel.tipo==='arc')handles.push(sel.a,sel.paso,sel.b);
  if(sel.tipo==='curve')handles.push(sel.a,sel.c1,sel.c2,sel.b);
  if(sel.tipo==='polyline')for(const v of sel.vertices)handles.push(v);
  if(sel.tipo==='line'||sel.tipo==='rectangle')handles.push(sel.a,sel.b);
  for(const v of handles){const rad=4.5*dpr/cad.view.s;ctx.fillStyle='#a7ffc6';ctx.fillRect(v[0]-rad,v[1]-rad,rad*2,rad*2)}
 }
 ctx.restore();
 if(cad.selectedSegments.length){
  ctx.save();ctx.strokeStyle='#ff856d';ctx.lineWidth=4*dpr;ctx.lineCap='round';
  for(const sel of cad.selectedSegments){
   const ent=cad.entities.find(e=>e.id===sel.id);if(!ent)continue;
   const points=cadSegmentEndpoints(ent,sel.index);ctx.beginPath();
   points.forEach((p,i)=>{const q=cadScreen(p);if(i)ctx.lineTo(...q);else ctx.moveTo(...q)});ctx.stroke();
  }
  ctx.restore();
 }
 // Cota DINÁMICA junto al cursor: solo mientras se dibuja una línea.
 // Es una indicación visual, NO un objeto DXF y NO queda en el plano.
 if(cad.tool==='line'&&cad.draft?.first&&cad.mouse){
  const a=cad.draft.first,b=cad.mouse,mm=Math.hypot(b[0]-a[0],b[1]-a[1]);
  const c=cadScreen(b),dpr=devicePixelRatio||1;
  const label=mm.toFixed(3)+' '+cad.units;
  ctx.save();ctx.font=`bold ${13*dpr}px system-ui`;ctx.textAlign='left';ctx.textBaseline='middle';
  const px=Math.min(Math.max(8*dpr,c[0]+15*dpr),cv.width-ctx.measureText(label).width-18*dpr),
        py=Math.min(Math.max(18*dpr,c[1]-20*dpr),cv.height-18*dpr);
  const width=ctx.measureText(label).width+16*dpr;
  ctx.fillStyle='#14273bf0';ctx.strokeStyle='#f1d88b';ctx.lineWidth=1*dpr;
  ctx.fillRect(px,py-12*dpr,width,24*dpr);ctx.strokeRect(px,py-12*dpr,width,24*dpr);
  ctx.fillStyle='#ffe6a1';ctx.fillText(label,px+8*dpr,py);ctx.restore();
 }
 // Marcas verdes en los extremos de TODOS los tramos seleccionados.
 if(cad.selectedSegments.length){
  ctx.save();ctx.strokeStyle='#68ffc0';ctx.fillStyle='#1c644a';ctx.lineWidth=1.6*dpr;
  for(const sel of cad.selectedSegments){const ent=cad.entities.find(e=>e.id===sel.id);if(!ent)continue;
   const points=cadSegmentEndpoints(ent,sel.index);
   for(const v of [points[0],points[points.length-1]]){const p=cadScreen(v);ctx.beginPath();ctx.arc(p[0],p[1],5.5*dpr,0,2*Math.PI);ctx.fill();ctx.stroke();}
  }ctx.restore();
 }
 // Confirmación persistente de las uniones de la última geometría creada.
 if(cad.lastJoints?.length){ctx.save();ctx.lineWidth=2*dpr;ctx.fillStyle='#1f805b';ctx.strokeStyle='#73ffbd';
  for(const j of cad.lastJoints){const p=cadScreen(j.point);ctx.beginPath();ctx.arc(p[0],p[1],6*dpr,0,2*Math.PI);ctx.fill();ctx.stroke();
   ctx.fillStyle='#effff7';ctx.font=`bold ${10*dpr}px system-ui`;ctx.fillText('✓',p[0]-3.5*dpr,p[1]+3.5*dpr);ctx.fillStyle='#1f805b';
  }ctx.restore();}
 // Vista de medición: marcas y cota entre dos puntos (sin guardar entidades).
 if(cad.tool==='measure'&&cad.measure){
  const m=cad.measure,dpr=devicePixelRatio||1;
  if(m.start){const a=cadScreen(m.start),b=cadScreen(m.end||cad.mouse||m.start);
   ctx.save();ctx.strokeStyle='#ffe18c';ctx.fillStyle='#ffe18c';ctx.lineWidth=2*dpr;ctx.setLineDash([5*dpr,4*dpr]);
   ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();ctx.setLineDash([]);
   for(const p of [a,...(m.end?[b]:[])]){ctx.beginPath();ctx.arc(p[0],p[1],5*dpr,0,Math.PI*2);ctx.fill();}ctx.restore();
  }
 }
 if(cad.angleSnap&&cad.tool==='line'){
  const a=cadScreen(cad.angleSnap.origin),b=cadScreen(cad.angleSnap.point),d=cad.angleSnap.dir;
  ctx.save();ctx.fillStyle='#7affc2';ctx.strokeStyle='#7affc2';ctx.lineWidth=2*dpr;
  const sz=12*dpr,step=[d[0]*sz,-d[1]*sz],other=[-(b[0]-a[0]),-(b[1]-a[1])];
  const len=Math.hypot(...other)||1,v=[other[0]/len*sz,other[1]/len*sz];
  ctx.beginPath();ctx.moveTo(a[0]+step[0],a[1]+step[1]);ctx.lineTo(a[0]+step[0]+v[0],a[1]+step[1]+v[1]);ctx.lineTo(a[0]+v[0],a[1]+v[1]);ctx.stroke();
  ctx.font=`bold ${12*dpr}px system-ui`;ctx.fillText('90°',b[0]+11*dpr,b[1]-12*dpr);ctx.restore();
 }
 if(cad.snap&&['line','arc','curve','rectangle','circle','select','measure'].includes(cad.tool)){
  const p=cadScreen(cad.snap.point),r=7*dpr;
  ctx.save();ctx.strokeStyle='#4dffad';ctx.fillStyle='#4dffad';ctx.lineWidth=2*dpr;
  ctx.beginPath();ctx.arc(p[0],p[1],r,0,2*Math.PI);ctx.stroke();
  ctx.beginPath();ctx.arc(p[0],p[1],2.3*dpr,0,2*Math.PI);ctx.fill();
  ctx.font=`${11*dpr}px system-ui`;ctx.fillText(cad.snap.kind==='medio'?'◆ PUNTO MEDIO':'● UNIÓN · '+cad.snap.label,p[0]+10*dpr,p[1]-11*dpr);ctx.restore();
 }
}
function cadScreenDown(e){if(!cad.active||e.button!==0&&e.button!==1)return;
 const s=cadCanvasPos(e),raw=cadAt(...s);
 const drawing=['line','arc','curve','rectangle','circle'].includes(cad.tool);
 const found=drawing?cadResolverPunto(raw):null;const hitSnap=found?.snap||null;
 const q=found?found.point:raw;cad.angleSnap=found?.angle||null;
 if(drawing){if(!cad.draft)cad.pendingJoints=[];if(hitSnap)cad.pendingJoints.push({point:q.slice(),label:hitSnap.label});}
 if(cad.tool==='pan'||e.button===1||e.altKey){cad.panning={x:s[0],y:s[1],ox:cad.view.x,oy:cad.view.y};cv.setPointerCapture(e.pointerId);return}
 if(cad.tool==='measure'){cadMeasureClick(raw);return;}
 if(cad.tool==='segment'){
  const hit=cadNearestSegment(raw);
  if(hit){
   const at=cad.selectedSegments.findIndex(sel=>sel.id===hit.id&&sel.index===hit.index);
   if(at>=0)cad.selectedSegments.splice(at,1);else cad.selectedSegments.push(hit);
  }else{cad.selectedSegments=[];}
  cad.selectedSegment=cad.selectedSegments.at(-1)||null;
  cad.selected=null;cad.selectedIds=[];cadRefresh();redraw();return;
 }
 if(cad.tool==='select'){
  cad.selectedSegment=null;cad.selectedSegments=[];
  const oldId=cad.selected;
  const handle=cad.selectedIds.length===1?cadHitHandle(q):null;
  const item=handle!==null?oldId:cadHitEntity(q);
  if(item===null){cad.selected=null;cad.selectedIds=[];cadRefresh();redraw();return}
  const already=cad.selectedIds.includes(item);
  if(handle===null&&already){
   // Un segundo clic sobre la misma entidad la desmarca. Con Mayús, siempre se puede alternar.
   cad.selectedIds=cad.selectedIds.filter(id=>id!==item);
   cad.selected=cad.selectedIds.at(-1)||null;
   cadRefresh();redraw();return;
  }
  if(!already)cad.selectedIds.push(item);
  cad.selected=item;
  cad.drag={start:q,base:cadCopy(cadSeleccion()),handle,changed:false};
  cv.setPointerCapture(e.pointerId);cadRefresh();redraw();return;
 }
 if(cad.tool==='curve'){
  if(!cad.draft){cad.draft={first:q,points:[q]};cadEl('cadMode').textContent='Curva: marca control 1';redraw();return}
  const pts=cad.draft.points;
  if(pts.length<3){pts.push(q);cadEl('cadMode').textContent=pts.length===2?'Curva: marca control 2':'Curva: marca punto final';redraw();return}
  const [a,c1,c2]=pts;
  if(Math.hypot(a[0]-q[0],a[1]-q[1])<=.005){cadEl('cadMode').textContent='Los extremos de la curva deben ser distintos.';return}
  const id='curva-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8);
  cadSnapshot();cad.entities.push({id,tipo:'curve',capa:'DIBUJO',a,c1,c2,b:q});cad.selected=id;cad.selectedIds=[id];
  cad.draft=null;cad.mouse=null;cadConfirmarUniones();cadEl('cadMode').textContent='Curva creada · marca el siguiente punto inicial';cadRefresh();redraw();return;
 }
 if(cad.tool==='arc'){
  if(!cad.draft){cad.draft={first:q,points:[q]};cadEl('cadMode').textContent='Arco 3P: marca el segundo extremo';redraw();return}
  if(cad.draft.points.length===1){
   if(Math.hypot(q[0]-cad.draft.first[0],q[1]-cad.draft.first[1])<.005){cadEl('cadMode').textContent='Los dos extremos deben ser distintos.';return}
   cad.draft.points.push(q);cadEl('cadMode').textContent='Arco 3P: marca el punto de paso sobre la curva';redraw();return;
  }
  const [a,b]=cad.draft.points;
  if(!cadArcGeometry(a,q,b)){cadEl('cadMode').textContent='Arco inválido: el punto de paso no puede alinearse con los extremos.';redraw();return}
  const id='arco-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8);
  cadSnapshot();cad.entities.push({id,tipo:'arc',capa:'DIBUJO',a,paso:q,b});
  cad.selected=id;cad.selectedIds=[id];
  cad.draft=null;cad.mouse=null;cadConfirmarUniones();cadEl('cadMode').textContent='Arco creado · marca el siguiente primer extremo';
  cadRefresh();redraw();return;
 }
 if(!cad.draft){cad.draft={first:q};cad.mouse=q;cad.angleSnap=null;redraw();return}
 const p=cad.draft.first;cad.draft=null;cad.mouse=null;cad.angleSnap=null;
 const id='dibujado-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8);
 let entity;
 if(cad.tool==='line'&&Math.hypot(p[0]-q[0],p[1]-q[1])>.005)
  entity={id,tipo:'line',capa:'DIBUJO',a:p,b:q};
 if(cad.tool==='circle'&&Math.hypot(p[0]-q[0],p[1]-q[1])>.01)
  entity={id,tipo:'circle',capa:'AGUJEROS',cx:p[0],cy:p[1],radio:Math.hypot(p[0]-q[0],p[1]-q[1])};
 if(cad.tool==='rectangle'&&Math.abs(p[0]-q[0])>.005&&Math.abs(p[1]-q[1])>.005)
  entity={id,tipo:'rectangle',capa:'DIBUJO',a:p,b:q};
 if(entity){cadSnapshot();cad.entities.push(entity);cad.selected=id;cad.selectedIds=[id];cadConfirmarUniones();cadRefresh();}else cadEl('cadSelection').textContent='Geometría demasiado pequeña.';
 redraw();
}
function cadScreenMove(e){if(!cad.active)return;
 const p=cadCanvasPos(e),raw=cadAt(...p);
 const snapping=['line','arc','curve','rectangle','circle','measure'].includes(cad.tool)||(cad.tool==='select'&&cad.drag?.handle!==null&&cad.drag?.handle!==undefined);
 const found=cad.panning||!snapping?null:cadResolverPunto(raw);
 cad.snap=found?.snap||null;cad.angleSnap=found?.angle||null;
 const q=found?found.point:raw;cad.mouse=q;
 if(cad.panning){cad.view.x=cad.panning.ox+p[0]-cad.panning.x;cad.view.y=cad.panning.oy+p[1]-cad.panning.y;redraw();return}
 if(cad.drag){const d=cad.drag,start=d.start,ent=cadCopy(d.base);
  const dx=q[0]-start[0],dy=q[1]-start[1];
  if(d.handle!==null)cadEditHandle(ent,d.handle,q);else {cadMove(ent,raw[0]-start[0],raw[1]-start[1]);cad.mouse=raw;}
  cad.entities[cad.entities.findIndex(e=>e.id===ent.id)]=ent;
  d.changed=(d.handle!==null?Math.hypot(dx,dy):Math.hypot(raw[0]-start[0],raw[1]-start[1]))>.001;redraw();return}
 cad.mouse=q;redraw();
}
function cadScreenUp(){if(cad.drag){const d=cad.drag;cad.drag=null;
 if(d.changed){cad.entities[cad.entities.findIndex(e=>e.id===d.base.id)]=d.base;cadSnapshot();
  const ent=cadCopy(d.base);if(d.handle!==null)cadEditHandle(ent,d.handle,cad.mouse||d.start);
  else if(cad.mouse)cadMove(ent,cad.mouse[0]-d.start[0],cad.mouse[1]-d.start[1]);
  cad.entities[cad.entities.findIndex(e=>e.id===ent.id)]=ent;
  cadRefresh();redraw()}}
 cad.panning=null;
}
function cadWheel(e){const p=cadCanvasPos(e),w=cadAt(...p),fac=e.deltaY>0?.87:1.15;
 cad.view.s=Math.min(3000,Math.max(.1,cad.view.s*fac));cad.view.x=p[0]-w[0]*cad.view.s;
 cad.view.y=p[1]+w[1]*cad.view.s;redraw();}
function cadRefresh(){
 if(!cad.lastJoints.length){cadEl('cadJoinStatus').style.display='none';cadEl('cadJoinStatus').textContent='';}
 cadEl('cadUndo').disabled=!cad.undo.length;cadEl('cadRedo').disabled=!cad.redo.length;
 const ent=cad.selectedIds.length===1?cadSeleccion():null;const nseg=cad.selectedSegments.length,nent=cad.selectedIds.length;cadEl('cadDelete').disabled=nseg===0&&nent===0;
 cadEl('cadDelete').title=nseg?'Borrar los '+nseg+' tramos seleccionados':'Eliminar las entidades seleccionadas';
 const unit=cad.units==='mm'?'mm':'px';
 cadEl('cadSelection').textContent=nseg?`${nseg} tramos seleccionados`:nent>1?`${nent} entidades seleccionadas`:ent?(ent.tipo==='polyline'?`Contorno · ${ent.vertices.length} vértices`:ent.tipo==='circle'?`Círculo · Ø ${(2*ent.radio).toFixed(3)} ${unit}`:ent.tipo==='line'?`Línea · ${Math.hypot(ent.b[0]-ent.a[0],ent.b[1]-ent.a[1]).toFixed(3)} ${unit}`:ent.tipo==='arc'?'Arco CAD':ent.tipo==='curve'?'Curva CAD': 'Rectángulo CAD'):cad.units==='mm'?'':'Sin calibrar · medidas en px';
 cadEl('cadUnit').textContent=cad.units==='mm'?'Unidad: milímetros':'SIN ESCALA: coordenadas en píxeles';
 const b=cadBoundsRaw();cadEl('cadEntityCount').textContent=cad.entities.length+' entidades CAD · '+(b.r-b.l).toFixed(2)+' × '+(b.t-b.b).toFixed(2)+' '+cad.units+(cad.dirty?' · modificado':'');
 cadEl('cadCircleForm').style.display=ent&&ent.tipo==='circle'?'block':'none';
 if(ent&&ent.tipo==='circle'){
  // Un círculo recién creado queda seleccionado y ofrece aquí su diámetro exacto.
  cadEl('cadDiameterUnit').textContent=unit;
  cadEl('cadDiameter').value=(2*ent.radio).toFixed(3);
  cadEl('cadCX').value=ent.cx.toFixed(3);cadEl('cadCY').value=ent.cy.toFixed(3);
 }
}
function cadAplicarCirculo(){
 const ent=cad.selectedIds.length===1?cadSeleccion():null;
 if(!ent||ent.tipo!=='circle'){error('Selecciona un círculo para modificar su diámetro.');return}
 const diameter=Number(cadEl('cadDiameter').value);
 const x=Number(cadEl('cadCX').value),y=Number(cadEl('cadCY').value);
 if(![x,y,diameter].every(Number.isFinite)||diameter<=0.02){error('Introduce un diámetro válido mayor que 0,02.');return}
 const radio=diameter/2;
 if(Math.abs(ent.cx-x)<1e-10&&Math.abs(ent.cy-y)<1e-10&&Math.abs(ent.radio-radio)<1e-10)return;
 cadSnapshot();ent.cx=x;ent.cy=y;ent.radio=radio;
 cadRefresh();redraw();
}
function cadAplicarMover(){const ent=cadSeleccion();if(!ent){error('Selecciona una entidad primero.');return}
 const dx=Number(cadEl('cadMoveX').value),dy=Number(cadEl('cadMoveY').value);
 if(![dx,dy].every(Number.isFinite)){error('Desplazamiento inválido.');return}
 if(dx===0&&dy===0)return;
 cadSnapshot();cadMove(ent,dx,dy);cadEl('cadMoveX').value='0';cadEl('cadMoveY').value='0';cadRefresh();redraw()}
function cadKey(e){if(!cad.active||['INPUT','TEXTAREA'].includes(document.activeElement.tagName))return false;
 const ctrl=e.ctrlKey||e.metaKey,key=e.key.toLowerCase();
 if(ctrl&&key==='z'){e.preventDefault();if(e.shiftKey)cadRehacer();else cadDeshacer();return true}
 if(ctrl&&key==='y'){e.preventDefault();cadRehacer();return true}
 if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();cadBorrar();return true}
 if(e.key==='Escape'){cad.drag=null;cad.draft=null;cad.selected=null;cad.selectedIds=[];cad.selectedSegments=[];cad.selectedSegment=null;cadSetTool('select');cadRefresh();redraw();return true}
 return false}
