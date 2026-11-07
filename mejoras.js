/* Vectorizador V2.0.18 — módulos opcionales. Mantiene intacto el motor estable. */
'use strict';
const av={mode:null,first:null,marks:[],multi:[],warn:[]};
const avId=()=>`av-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;
const avDist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const avMsg=(s)=>{const el=document.getElementById('avMsg');if(el)el.textContent=s;const bubble=document.getElementById('avFloatStatus');if(bubble){bubble.textContent=s;bubble.style.display=cad.active?'block':'none';}};
const avNum=(id,def=0)=>{const e=document.getElementById(id),n=Number(e?.value);return Number.isFinite(n)?n:def};
function avSelected(){return cad.entities.filter(e=>cad.selectedIds.includes(e.id));}
function avNotifySelection(ids){cad.selectedIds=ids;cad.selected=ids.at(-1)||null;cad.selectedSegments=[];cadRefresh();redraw();}

// Unir LINE, ARC y LWPOLYLINE abiertas con bulges CAD exactos.
function avSegments(e){
 if(e.tipo==='line')return[[...e.a,0],[...e.b,0]];
 if(e.tipo==='polyline'&&!e.cerrada)return cadCopy(e.vertices);
 if(e.tipo==='arc'){
  const g=cadArcGeometry(e.a,e.paso,e.b);if(!g)return null;
  const tau=2*Math.PI;const mod=x=>(x%tau+tau)%tau;
  const angle=p=>Math.atan2(p[1]-g.cy,p[0]-g.cx);
  const aa=angle(e.a),mid=angle(e.paso),end=angle(e.b);
  const ccw=mod(mid-aa)<mod(end-aa);
  const sweep=ccw?mod(end-aa):mod(aa-end);
  const bulge=(ccw?1:-1)*Math.tan(sweep/4);
  return[[...e.a,bulge],[...e.b,0]];
 }
 return null;
}
function avReverse(points){return points.slice().reverse().map((p,i)=>[p[0],p[1],i<points.length-1?-(points[points.length-2-i][2]||0):0]);}
function avUnir(){
 avCancelMode();
 let sel=avSelected();if(sel.length<2){avMsg('Selecciona dos o más líneas, arcos o contornos abiertos.');return;}
 const tol=Math.max(.001,avNum('avJoinTol',.08));
 let chains=[];for(const e of sel){const s=avSegments(e);if(!s){avMsg('Unir admite líneas, arcos y polilíneas abiertas; no círculos, curvas SPLINE ni contornos cerrados.');return;}chains.push(s)}
 let linked=true;
 while(chains.length>1&&linked){linked=false;outer:for(let i=0;i<chains.length;i++)for(let j=i+1;j<chains.length;j++){
  const a=chains[i],b=chains[j];let c=null;
  const variants=[[a,b],[a,avReverse(b)],[avReverse(a),b],[avReverse(a),avReverse(b)]];
  for(const [x,y] of variants){if(avDist(x.at(-1),y[0])<=tol){
    // No incorporar un hueco oculto: el punto de la junta se mantiene exacto, se avisa de holgura.
    c=x.slice(0,-1).concat([[...x.at(-1).slice(0,2),y[0][2]||0]],y.slice(1));break;
  }}
  if(c){chains[i]=c;chains.splice(j,1);linked=true;break outer;}
 }}
 if(chains.length>1){avMsg('Algunos extremos no coinciden dentro de la tolerancia; no se ha realizado ningún cambio.');return}
 const vs=chains[0];if(vs.length<2){avMsg('Contorno no válido.');return;}
 const newEnt={id:avId(),tipo:'polyline',capa:sel[0].capa,cerrada:false,vertices:vs};
 cadSnapshot();const ids=new Set(sel.map(e=>e.id));cad.entities=cad.entities.filter(e=>!ids.has(e.id));cad.entities.push(newEnt);avNotifySelection([newEnt.id]);avMsg('Elementos unidos en una polilínea CAD abierta.');
}
function avCerrar(){
 avCancelMode();
 const ent=avSelected();if(ent.length!==1||ent[0].tipo!=='polyline'||ent[0].cerrada){avMsg('Selecciona una sola polilínea abierta.');return}
 const e=ent[0],a=e.vertices[0],b=e.vertices.at(-1);const gap=avDist(a,b),tol=Math.max(.001,avNum('avJoinTol',.08));
 if(gap>tol&&!confirm(`Los extremos están separados ${gap.toFixed(3)} mm. ¿Crear el segmento de cierre?`))return;
 if(e.vertices.length-(gap<.00001?1:0)<3){avMsg('Se necesitan tres vértices para cerrar.');return}
 cadSnapshot();if(gap<.00001)e.vertices.pop();e.cerrada=true;cadRefresh();redraw();avMsg('Contorno cerrado con un segmento recto final.');
}
function avIntersection(a,b,c,d){
 const rx=b[0]-a[0],ry=b[1]-a[1],sx=d[0]-c[0],sy=d[1]-c[1],det=rx*sy-ry*sx;
 if(Math.abs(det)<1e-9)return null;
 const t=((c[0]-a[0])*sy-(c[1]-a[1])*sx)/det, u=((c[0]-a[0])*ry-(c[1]-a[1])*rx)/det;
 return {point:[a[0]+t*rx,a[1]+t*ry],t,u};
}
// Recortar/prolongar: modificar una LINE independiente o el tramo recto
// TERMINAL de una polilínea abierta; usar como límite cualquier segmento recto
// visible (también de los contornos CAD cerrados). Nunca alterar curvas/bulges.
function avStraightPart(hit,asSource=false){
 const e=cad.entities.find(x=>x.id===hit?.id);if(!e)return{error:'No se encontró la geometría.'};
 if(e.tipo==='line')return{e,a:e.a,b:e.b,index:0,terminal:null};
 if(e.tipo==='rectangle'&&!asSource){
  const pts=cadPathPoints(e);return{e,a:pts[hit.index],b:pts[hit.index+1],index:hit.index};
 }
 if(e.tipo==='polyline'){
  const i=hit.index,n=e.cerrada?e.vertices.length:e.vertices.length-1;
  if(i<0||i>=n)return{error:'Selecciona uno de los tramos del contorno.'};
  const a=e.vertices[i],b=e.vertices[(i+1)%e.vertices.length];
  if(Math.abs(a[2]||0)>1e-9)return{error:'El tramo seleccionado es curvo. Elige un tramo recto.'};
  if(asSource&&(e.cerrada||!(i===0||i===n-1))){
   return{error:'Para modificar, selecciona una línea independiente o el primer/último tramo recto de un contorno ABIERTO. Un contorno cerrado no se recorta automáticamente.'};
  }
  return{e,a,b,index:i,terminal:asSource?(n===1?'either':i===0?'a':'b'):null};
 }
 return{error:asSource?'Solo se modifican líneas y extremos rectos de contornos abiertos.':'El límite debe ser una línea o un tramo recto del contorno.'};
}
function avFindHit(p){return cadNearestSegment(p)}
function avLineOperation(first,second){
 const src=avStraightPart(first,true),target=avStraightPart(second,false);
 if(src.error||target.error){avMsg(src.error||target.error);return false}
 if(src.e.id===target.e.id){avMsg('El límite tiene que pertenecer a otra entidad CAD.');return false}
 const inter=avIntersection(src.a,src.b,target.a,target.b);
 if(!inter){avMsg('Esas rectas son paralelas: no se cruzan.');return false}
 const {point,t,u}=inter;
 if(u< -1e-7||u>1+1e-7){avMsg('Las rectas se cruzan, pero fuera del tramo límite elegido. Escoge un tramo que alcance la intersección.');return false}
 let endpoint;
 if(av.mode==='trim'){
  if(t<=1e-7||t>=1-1e-7){avMsg('Recortar: el límite debe cruzar el INTERIOR de la línea que quieres acortar.');return false}
  endpoint=src.terminal||(avDist(first.click,src.a)<avDist(first.click,src.b)?'a':'b');
  // Se modifica el extremo más próximo al clic del usuario, no toda la figura.
 }else if(av.mode==='extend'){
  if(t>=-1e-7&&t<=1+1e-7){avMsg('Prolongar: la línea ya llega al límite (o lo cruza). Elige otro límite exterior.');return false}
  endpoint=t<0?'a':'b';
  if(src.terminal&&src.terminal!=='either'&&src.terminal!==endpoint){avMsg('El extremo que llegaría al límite está unido al contorno. Para no deformarlo, solo se prolonga el extremo libre.');return false}
 }else return false;
 if(src.terminal&&src.terminal!=='either'&&src.terminal!==endpoint){avMsg('Solo puede modificarse el extremo libre de una polilínea abierta.');return false}
 if(avDist(point,src[endpoint])<1e-7){avMsg('El extremo ya coincide con el límite.');return false}
 cadSnapshot();
 if(src.e.tipo==='line')src.e[endpoint]=point;
 else{
  const v=endpoint==='a'?src.e.vertices[0]:src.e.vertices.at(-1);
  v[0]=point[0];v[1]=point[1];
 }
 cadRefresh();redraw();
 avMsg(av.mode==='trim'?'✓ Línea recortada. Deshacer: Ctrl+Z.':'✓ Línea prolongada hasta el límite. Deshacer: Ctrl+Z.');
 return true;
}
function avSetMode(mode){
 cadSetTool('select');av.mode=mode;av.first=null;
 const e=document.getElementById(mode==='trim'?'avTrim':'avExtend');e?.classList.add('active');
 avMsg(mode==='trim'?'RECORTAR — 1) Clic cerca del EXTREMO de la línea que quieres quitar. 2) Clic en la recta que hace de límite.':'PROLONGAR — 1) Clic en la línea que quieres alargar. 2) Clic en la recta a la que debe llegar.');
}
function avCanvasCapture(ev){
 if(!cad.active||!av.mode||cad.tool!=='select'||ev.button!==0)return;
 ev.preventDefault();ev.stopImmediatePropagation();
 const p=cadAt(...cadCanvasPos(ev)),hit=avFindHit(p);
 if(!hit){avMsg('No hay ninguna línea cerca. Acércate con el zoom y pulsa sobre el TRAZO.');return}
 const s=avStraightPart(hit,!av.first);
 if(s.error){avMsg(s.error);return}
 if(!av.first){av.first={...hit,click:p};cad.selectedSegments=[{id:hit.id,index:hit.index}];cad.selectedSegment=cad.selectedSegments[0];avMsg('✓ Línea marcada. Ahora pulsa sobre la LÍNEA LÍMITE (también sirve un tramo recto del contorno de la pieza).');redraw();return}
 const first=av.first;
 const ok=avLineOperation(first,{...hit,click:p});
 if(ok){cad.selectedSegments=[];cad.selectedSegment=null;avCancelMode();avMsg('✓ Operación aplicada. Puedes continuar con otra herramienta o pulsar Ctrl+Z para deshacer.');}else{av.first=null;cad.selectedSegments=[];cad.selectedSegment=null;avMsg((document.getElementById('avMsg')?.textContent||'No se ha cambiado la geometría.')+' Marca otra línea para repetir.');}
 redraw();
}

async function avVerificar(){avCancelMode();if(!cad.initialized){avMsg('Abre primero el editor.');return}
 try{const r=await fetch('/api/editor/verificar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload(),entidades_editadas:cad.entities,sin_escala:cad.units!=='mm'})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Falló verificación');
 const box=document.getElementById('avWarnings');box.innerHTML='';document.getElementById('avReviewDetails').open=true;const msg=document.createElement('div');msg.className='avVerifySummary';msg.textContent=`${d.entidades} entidades · ${d.cerradas} contornos cerrados · ${d.avisos.length} posibles problemas`;box.append(msg);
 for(const a of d.avisos.slice(0,30)){const el=document.createElement('button');el.className='avWarn';el.textContent=`${a.tipo}: ${a.mensaje}`;el.onclick=()=>{avNotifySelection([a.id]);cadFit();cerrarAyuda()};box.append(el)}
 if(!d.avisos.length){const info=document.createElement('div');info.textContent='✓ Sin avisos en las pruebas básicas. Las líneas sueltas no se consideran error. Comprueba los perfiles en Onshape.';box.append(info);avMsg('Verificación completada: consulta el informe en esta ventana.')}else avMsg(`${d.avisos.length} posibles problemas: pulsa un aviso para localizarlo en el plano.`);
 abrirAyuda();
 }catch(e){avMsg('No se pudo verificar: '+e.message);abrirAyuda()}
}

// --- Vista fotográfica: superposición, calidad y recuperación de proyectos ---
async function avActualizarVista(){
 const s=state.scale,el=document.getElementById('avQuality');if(!el)return;
 if(!state.vector){el.textContent='Sin vectorización';return}
 const method=s?.metodo||s?.proyectiva_automatica?.tipo||'desconocido',ok=ready();
 const n=state.vector.contornos.filter(c=>c.revision_recomendada).length;
 el.textContent=(ok?`Escala: ${method} · medición orientativa`:'⚠ Sin escala métrica fiable')+(n?` · ${n} borde(s)/hueco(s) para revisar`: '')+(s?.control_papel_a4?.estado==='corregida'?' · A4 contrastado con el borde físico':'');
 const dim=document.getElementById('avDimStatus');if(!dim)return;
 if(!ok){dim.textContent='Dimensiones en mm no disponibles: escala pendiente';return}
 try{
  const cur=state.vector;
  const r=await fetch('/api/medidas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});
  const data=await r.json();if(!r.ok||state.vector!==cur)throw Error();
  const [ancho,alto]=data.dimensiones_mm;
  dim.textContent=`Ancho ${ancho.toFixed(3)} mm · Alto ${alto.toFixed(3)} mm · Medidas orientativas`;
 }catch(e){dim.textContent='No se pudieron medir las dimensiones';}
}

async function avDetectarMulti(){if(!state.file)return avMsg('Importa una fotografía primero.');
 try{avMsg('Buscando piezas separadas...');const fd=new FormData();fd.append('archivo',state.file);fd.append('umbral',document.getElementById('threshold').value);
 const r=await fetch('/api/piezas/detectar',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw Error(d.detail||'No se pudieron detectar piezas');
 av.multi=d.piezas;const box=document.getElementById('avMultiList');box.innerHTML='';for(const [i,p] of av.multi.entries()){
  const label=document.createElement('label');label.style.display='block';const input=document.createElement('input');input.type='checkbox';input.checked=i<Math.min(av.multi.length,4);input.dataset.piece=p.id;
  label.append(input,document.createTextNode(` Pieza ${i+1} · ${p.bbox[2]-p.bbox[0]}×${p.bbox[3]-p.bbox[1]} px`));box.append(label);
 }avMsg(`${av.multi.length} candidatos: desmarca reglas, letras o manchas que no sean piezas.`);
 }catch(e){avMsg(e.message)}
}
async function avVectorizarMulti(){if(!state.file||!av.multi.length)return avMsg('Detecta primero las piezas.');
 const selected=av.multi.filter(p=>document.querySelector(`[data-piece="${p.id}"]`)?.checked);
 if(!selected.length)return avMsg('Selecciona al menos una pieza.');
 if(cad.dirty&&!confirm('Este cálculo reemplazará los cambios CAD. ¿Continuar?'))return;
 let results=[];for(const p of selected){
  const fd=new FormData();fd.append('archivo',state.file);fd.append('umbral',document.getElementById('threshold').value);fd.append('recuperar',document.getElementById('recoverHoles').checked?'true':'false');fd.append('recorte',JSON.stringify(p.recorte));
  const r=await fetch('/api/vectorizar',{method:'POST',body:fd});const d=await r.json();if(!r.ok){avMsg(`Fallo de ${p.id}: ${d.detail||'no detectada'}. Prueba delimitarla por separado.`);return}results.push(d);
 }
 const first=results[0];let contornos=[],xs=[],ys=[];
 for(const d of results){contornos.push(...d.contornos);xs.push(d.bbox_px[0],d.bbox_px[0]+d.bbox_px[2]);ys.push(d.bbox_px[1],d.bbox_px[1]+d.bbox_px[3]);}
 cadDisable();state.vector={...first,contornos,bbox_px:[Math.min(...xs),Math.min(...ys),Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)],silueta_png:null,agujeros_recuperados:results.reduce((a,d)=>a+(d.agujeros_recuperados||0),0)};
 state.scale=first.calibracion;state.manual=null;state.binary=null;
 document.getElementById('cadToggle').style.display='block';document.getElementById('cadToggle').textContent='Editar CAD';
 document.getElementById('viewPill').textContent=`${selected.length} piezas · DXF conjunto`;
 updateScale();buttons();redraw();avActualizarVista();avMsg(`${selected.length} piezas combinadas en un único plano CAD/DXF. Comprueba cada contorno antes de exportar.`);
}
async function avGuardarHistorial(silent=false){if(!state.file||!state.vector)return;
 const fd=new FormData();fd.append('archivo',state.file);fd.append('datos',JSON.stringify({vector:state.vector,scale:state.scale,manual:state.manual,entidades:cad.initialized?cad.entities:null}));
 try{const r=await fetch('/api/historial/guardar',{method:'POST',body:fd});const d=await r.json();if(!r.ok)throw Error(d.detail||'No se pudo guardar');if(!silent)avMsg(`Trabajo guardado: ${d.nombre}`)}catch(e){if(!silent)avMsg('Error de historial: '+e.message)}
}
async function avAbrirHistorial(){const box=document.getElementById('avHistList');box.innerHTML='';
 try{const r=await fetch('/api/historial/listar');const d=await r.json();if(!r.ok)throw Error();
 for(const item of d.trabajos){const b=document.createElement('button');b.className='avWarn';b.textContent=`${item.fecha.slice(0,16).replace('T',' ')} · ${item.nombre}`;b.onclick=()=>avRestaurar(item.id);box.append(b)}if(!d.trabajos.length)box.textContent='Todavía no hay trabajos guardados.';
 }catch(e){avMsg('No se pudo abrir historial.')}
}
async function avRestaurar(id){
 try{const r=await fetch(`/api/historial/abrir/${id}`),d=await r.json();if(!r.ok)throw Error(d.detail);
 const rr=await fetch(`/api/historial/foto/${id}`),blob=await rr.blob();if(!rr.ok)throw Error('No se encuentra la fotografía guardada.');
 const file=new File([blob],d.nombre,{type:blob.type||'image/jpeg'}),u=URL.createObjectURL(blob),im=new Image();
 await new Promise((resolve,reject)=>{im.onload=resolve;im.onerror=reject;im.src=u});URL.revokeObjectURL(u);
 reset();state.file=file;state.img=im;state.vector=d.trabajo.vector;state.scale=d.trabajo.scale;state.manual=d.trabajo.manual;state.binary=null;
 document.getElementById('empty').style.display='none';document.getElementById('controls').style.display='block';document.getElementById('filename').textContent=d.nombre;
 document.getElementById('cadToggle').style.display='block';document.getElementById('cadToggle').textContent='Editar CAD';
 if(d.trabajo.entidades){cad.initialized=true;cad.dirty=true;cad.entities=cadCopy(d.trabajo.entidades);cad.original=cadCopy(d.trabajo.entidades);cad.units=ready()?'mm':'px';cad.selectedIds=[];cad.selected=null;cad.undo=[];cad.redo=[];}
 updateScale();fit();buttons();avActualizarVista();avMsg('Trabajo recuperado. Puedes seguir editando y exportar.');
 }catch(e){avMsg('No se pudo restaurar: '+e.message)}
}
function avCancelMode(){
 av.mode=null;av.first=null;
 const bubble=document.getElementById('avFloatStatus');if(bubble)bubble.style.display='none';
 document.getElementById('avTrim')?.classList.remove('active');
 document.getElementById('avExtend')?.classList.remove('active');
}
// Las operaciones avanzadas son temporales: elegir CUALQUIER otra herramienta
// debe devolver el control del ratón al editor normal.
const avOriginalSetTool=cadSetTool;
cadSetTool=function(tool){
 avCancelMode();
 return avOriginalSetTool(tool);
};
const avOriginalSalir=cadSalir;
cadSalir=function(){avCancelMode();return avOriginalSalir()};

function avInit(){
 const b=document.getElementById('cadbar');const toolsHost=document.getElementById('cadbarTools')||b;const sep=document.getElementById('cadbarInsertBefore')||toolsHost.querySelector('hr');
 const floating=document.createElement('div');floating.id='avFloatStatus';floating.className='avFloatStatus';floating.style.display='none';document.getElementById('viewport').append(floating);
 const controls=[
  ['avJoin','⛓','Unir',avUnir,'Unir líneas y arcos seleccionados (con extremos coincidentes)'],
  ['avClose','◻','Cerrar',avCerrar,'Cerrar una polilínea abierta seleccionada'],
  ['avTrim','✂','Recortar',()=>avSetMode('trim'),'1º línea a acortar (clic cerca del extremo que quitas), 2º límite recto'],
  ['avExtend','↗','Prolongar',()=>avSetMode('extend'),'1º línea a alargar, 2º límite recto'],
  ['avVerify','✓','Verificar',avVerificar,'Buscar posibles contornos abiertos, duplicados y cruces']
 ];
 for(const [id,icon,label,fn,help] of controls){const el=document.createElement('button');el.id=id;el.title=help;el.innerHTML=`<span>${icon}</span>${label}`;el.onclick=fn;toolsHost.insertBefore(el,sep)}
 document.getElementById('view').addEventListener('pointerdown',avCanvasCapture,{capture:true});
 // Vista 2D: exactamente los controles de V2.0.14, salvo comparación opcional.
 const panel=document.getElementById('vectorPanel');
 const comparison=document.createElement('div');comparison.className='avTools';comparison.id='avComparison';
 comparison.innerHTML=`<div class="avSection"><b>Comparar foto y contorno</b><label for="comparisonAlpha">Visibilidad del trazado <span id="avAlphaNum">100 %</span></label><input id="comparisonAlpha" type="range" min="0" max="100" value="100" step="5" aria-label="Visibilidad del contorno sobre la fotografía"></div>`;
 panel.append(comparison);
 document.getElementById('comparisonAlpha').addEventListener('input',e=>{
  document.getElementById('avAlphaNum').textContent=e.target.value+' %';redraw();
 });
}
// V2.0.22: orden fijo de lectura por columnas, validado por el usuario.
// Deja intactos todos los manejadores y funciones de edición: solo mueve nodos DOM.
function avOrdenarBotonesCad(){
 const panel=document.getElementById('cadbarTools');
 const orden=[
   '[data-cad-tool="select"]', '[data-cad-tool="pan"]',
   '[data-cad-tool="measure"]', '#avJoin', '#avClose',
   '#avVerify', '#avExtend', '#avTrim',
   '[data-cad-tool="line"]', '[data-cad-tool="rectangle"]',
   '[data-cad-tool="circle"]', '[data-cad-tool="arc"]',
   '[data-cad-tool="curve"]', '[data-cad-tool="segment"]'
 ];
 if(!panel)return;
 for(const selector of orden){
   const boton=panel.querySelector(selector);
   if(boton)panel.appendChild(boton);
 }
 const sep=document.getElementById('cadbarInsertBefore');
 if(sep)sep.remove();
}
avInit();
avOrdenarBotonesCad();
