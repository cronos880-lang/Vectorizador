/* Vectorizador V2.6: proyecto editable autocontenido; no modifica STL/DXF. */
'use strict';
(() => {
  const $p = id => document.getElementById(id);
  const MAX_PROYECTO = 90 * 1024 * 1024;
  let ultimasXY = null;
  let xyPendientes = null;
  let ultimoNombre = '';
  const copiar = v => JSON.parse(JSON.stringify(v));
  const redondear = v => Number.isFinite(Number(v)) ? Number(v) : null;
  const textoSeguro = s => String(s || '').replace(/[\\/:*?"<>|\x00-\x1f]/g, '_').slice(0,100);
  const leerFichero = file => new Promise((ok,fail) => {
    const fr = new FileReader(); fr.onload = () => ok(fr.result);
    fr.onerror = () => fail(Error('No se ha podido leer el archivo.'));
    fr.readAsDataURL(file);
  });
  const cargarImagen = src => new Promise((ok,fail) => {
    const img = new Image(); img.onload = () => ok(img);
    img.onerror = () => fail(Error('No se puede reconstruir la fotografía del proyecto.'));
    img.src = src;
  });
  const sha256 = async text => {
    const buffer = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buffer)).map(v => v.toString(16).padStart(2,'0')).join('');
  };
  function cotasActuales(){
    if($p('stlTargetWidth').value && $p('stlTargetHeight').value && stlBaseDims){
      return [$p('stlTargetWidth').value, $p('stlTargetHeight').value];
    }
    return ultimasXY ? ultimasXY.slice() : null;
  }
  function ajusteActual(){
    const vista = $p('stlPreviewBackdrop').style.display==='flex';
    return {
      grosor: $p('extrudeThickness').value,
      offset: vista ? $p('stlLiveOffset').value : $p('extrudeOffset').value,
      objetivosXY: cotasActuales(),
      modoMedida: $p('stlMeasureMode').value,
      contornoOriginal: $p('stlShowOriginal').checked,
    };
  }
  function asegurarGuardable(){
    if(state.busy || stlGuardando || stlCambioAbort || stlCambioTimer || !motorCompatible)
      throw Error('Termina la operación o espera a que se actualicen las cotas antes de guardar.');
    if(!state.img || !state.file) throw Error('Primero importa una fotografía.');
    if(cad.draft || cad.drag) throw Error('Termina la herramienta CAD que estás utilizando antes de guardar.');
  }
  async function construir(){
    asegurarGuardable();
    const dataURL = await leerFichero(state.file);
    const datos = {
      formato: 'VectorizadorProyecto', versionFormato: 1,
      guardadoCon: 'V2.6', fecha: new Date().toISOString(),
      foto: {nombre: state.file.name, tipo: state.file.type, dataURL},
      vector: state.vector ? copiar(state.vector) : null,
      scale: state.scale ? copiar(state.scale) : null,
      manual: state.manual ? copiar(state.manual) : null,
      crop: state.crop ? copiar(state.crop) : null,
      cad: {
        initialized: !!cad.initialized, active: !!cad.active,
        entities: cad.initialized ? copiar(cad.entities) : [],
        original: cad.initialized ? copiar(cad.original) : [],
        undo: cad.initialized ? copiar(cad.undo) : [],
        redo: cad.initialized ? copiar(cad.redo) : [],
        dirty: !!cad.dirty, units: cad.units,
        photo: copiar(cad.photo),
        bg: {visible:!!cad.bg.visible,opacity:cad.bg.opacity},
      },
      ui: {
        threshold: $p('threshold').value,
        showOverlay: $p('showOverlay').checked,
        showBinary: $p('showBinary').checked,
        recoverHoles: $p('recoverHoles').checked,
        comparisonAlpha: $p('comparisonAlpha')?.value ?? null,
        zoom: state.zoom, panX: state.panX, panY: state.panY,
        extrusion: ajusteActual(),
      },
    };
    const payload = JSON.stringify(datos);
    if(payload.length > MAX_PROYECTO) throw Error('El proyecto excede el tamaño admitido (90 MB).');
    const hash = await sha256(payload);
    const texto = JSON.stringify({tipo:'VECT1',sha256:hash,datos});
    return new Blob([texto],{type:'application/json'});
  }
  async function guardar(){
    let handle=null;
    try{
      asegurarGuardable();
      const base = textoSeguro(ultimoNombre || state.file.name.replace(/\.[^.]+$/,'')) || 'Pieza';
      const nombre = (base.replace(/\.vect$/i,'')+'.vect');
      if(typeof window.showSaveFilePicker==='function'){
        try{
          handle = await window.showSaveFilePicker({suggestedName:nombre,
            types:[{description:'Proyecto editable Vectorizador',accept:{'application/json':['.vect']}}],
            excludeAcceptAllOption:true});
        }catch(e){if(e.name==='AbortError')return;throw e;}
      }
      const blob = await construir();
      if(handle){
        const writable = await handle.createWritable();
        try{await writable.write(blob);await writable.close()}
        catch(e){try{await writable.abort()}catch(_){}throw e;}
        ultimoNombre=handle.name.replace(/\.vect$/i,'');
      }else{
        const u=URL.createObjectURL(blob),a=document.createElement('a');
        a.href=u;a.download=nombre;document.body.append(a);a.click();a.remove();
        setTimeout(()=>URL.revokeObjectURL(u),20000);ultimoNombre=base;
      }
      setProgress(100,'Proyecto editable guardado: '+(handle?.name || nombre));
    }catch(e){error('No se pudo guardar el proyecto: '+e.message);}
  }
  function validar(datos){
    if(!datos || datos.formato!=='VectorizadorProyecto' || datos.versionFormato!==1)
      throw Error('Formato de proyecto desconocido o no compatible.');
    if(!datos.foto || typeof datos.foto.dataURL!=='string' ||
       !/^data:image\/(jpeg|png);base64,[A-Za-z0-9+/=]+$/.test(datos.foto.dataURL) ||
       !['image/jpeg','image/png'].includes(datos.foto.tipo))
      throw Error('La fotografía del proyecto no es válida.');
    if(!datos.foto.nombre || typeof datos.foto.nombre!=='string' || datos.foto.nombre.length>200)
      throw Error('Nombre de fotografía no válido.');
    if(datos.vector!==null && (!datos.vector || !Array.isArray(datos.vector.contornos) || datos.vector.contornos.length>50000))
      throw Error('Los contornos del proyecto no son válidos.');
    if(!datos.cad || typeof datos.cad!=='object' || !datos.ui || typeof datos.ui!=='object')
      throw Error('El proyecto no contiene el estado necesario.');
    for(const k of ['entities','original','undo','redo']){
      if(!Array.isArray(datos.cad[k]) || datos.cad[k].length>50000)
        throw Error('Datos CAD inválidos: '+k);
    }
    if(datos.cad.initialized && !datos.vector)
      throw Error('El proyecto editado carece de la vectorización original.');
    if(!datos.ui.extrusion || !Number.isFinite(Number(datos.ui.extrusion.grosor)) ||
       !Number.isFinite(Number(datos.ui.extrusion.offset)))
      throw Error('Los ajustes de extrusión no son válidos.');
    if(datos.ui.extrusion.objetivosXY !== null && datos.ui.extrusion.objetivosXY !== undefined &&
       (!Array.isArray(datos.ui.extrusion.objetivosXY) || datos.ui.extrusion.objetivosXY.length!==2 ||
        datos.ui.extrusion.objetivosXY.some(x=>!Number.isFinite(Number(x))||Number(x)<=0)))
      throw Error('Las medidas X/Y guardadas no son válidas.');
    return datos;
  }
  async function leerProyecto(file){
    if(!file || file.size>MAX_PROYECTO || file.size<80)throw Error('Tamaño de archivo de proyecto inválido.');
    let env;
    try{env=JSON.parse(await file.text())}catch(e){throw Error('El archivo no contiene un proyecto JSON válido.');}
    if(env?.tipo!=='VECT1' || !/^[a-f0-9]{64}$/.test(env.sha256||''))throw Error('No es un proyecto del Vectorizador.');
    const bytes=JSON.stringify(env.datos), hash=await sha256(bytes);
    if(hash!==env.sha256)throw Error('El archivo está modificado, dañado o incompleto (integridad SHA-256).');
    const datos=validar(env.datos);
    const imagen=await cargarImagen(datos.foto.dataURL);
    const contenido=await (await fetch(datos.foto.dataURL)).blob();
    if(contenido.size>20*1024*1024)throw Error('La fotografía supera el límite de 20 MB.');
    const original=new File([contenido],datos.foto.nombre,{type:datos.foto.tipo});
    return {datos,imagen,original};
  }
  async function abrir(file){
    try{
      if(state.busy || stlGuardando)throw Error('Termina la operación actual antes de abrir otro proyecto.');
      if(!file)return;
      const cargado=await leerProyecto(file); // Verificar antes de cambiar la pieza abierta
      if(state.img && !confirm('¿Abrir este proyecto? Se sustituirá el trabajo actual que no hayas guardado.'))return;
      if(stlPreviewBackdrop.style.display==='flex')cerrarVistaSTL();
      extrudeBackdrop.style.display='none';
      reset();
      const {datos,imagen,original}=cargado;
      state.file=original;state.img=imagen;
      state.vector=datos.vector;state.scale=datos.scale;state.manual=datos.manual;state.crop=datos.crop;
      const ui=datos.ui;state.zoom=redondear(ui.zoom)||1;
      state.panX=redondear(ui.panX)||0;state.panY=redondear(ui.panY)||0;
      $p('filename').textContent=original.name;
      $p('empty').style.display='none';$p('controls').style.display='block';
      $p('threshold').value=ui.threshold??'120';$p('thresholdNum').textContent=$p('threshold').value;
      $p('showOverlay').checked=!!ui.showOverlay;$p('showBinary').checked=!!ui.showBinary;
      $p('recoverHoles').checked=!!ui.recoverHoles;
      if($p('comparisonAlpha') && ui.comparisonAlpha!==null)$p('comparisonAlpha').value=ui.comparisonAlpha;
      $p('cadToggle').style.display=state.vector?'block':'none';
      if(state.vector){
        $p('viewPill').textContent='Contornos recuperados · DXF';
        $p('diagnosticInfo').textContent=state.vector.diagnostico?.mensaje||'';
        if(state.scale?.px_mm_x)$p('manualX').value=Number(state.scale.px_mm_x).toFixed(4);
        if(state.scale?.px_mm_y)$p('manualY').value=Number(state.scale.px_mm_y).toFixed(4);
        updateScale();
      }
      if(state.vector?.silueta_png){
        const b=new Image();b.onload=()=>{if(state.vector===datos.vector){state.binary=b;redraw()}};
        b.src=state.vector.silueta_png;
      }
      if(datos.cad.initialized){
        cad.initialized=true;cad.entities=copiar(datos.cad.entities);cad.original=copiar(datos.cad.original);
        cad.undo=copiar(datos.cad.undo);cad.redo=copiar(datos.cad.redo);
        cad.dirty=!!datos.cad.dirty;cad.units=datos.cad.units==='px'?'px':'mm';
        cad.photo=datos.cad.photo||{zoom:1,panX:0,panY:0};
        cad.bg={visible:false,opacity:datos.cad.bg?.opacity??.45,image:null,bounds:null,loading:false};
        $p('cadPhotoOpacity').value=String(Math.round(cad.bg.opacity*100));
        $p('cadPhotoPct').textContent=$p('cadPhotoOpacity').value+' %';
        cad.draft=null;cad.drag=null;cad.selected=null;cad.selectedIds=[];
        cad.selectedSegment=null;cad.selectedSegments=[];cad.tool='select';
        if(datos.cad.active){
          await cadIniciar();
          if(datos.cad.bg?.visible)await cadFondoActivar(true);
          $p('cadPhotoVisible').checked=!!cad.bg.visible;
        }
      }
      const x=ui.extrusion;
      $p('extrudeThickness').value=String(x.grosor);
      $p('extrudeSlider').value=String(x.grosor);
      $p('extrudeOffset').value=String(x.offset);
      $p('stlLiveOffset').value=String(x.offset);
      $p('stlOffsetSlider').value=String(x.offset);
      $p('stlMeasureMode').value=x.modoMedida==='agujeros'?'agujeros':'puntos';
      $p('stlShowOriginal').checked=x.contornoOriginal!==false;
      ultimasXY=Array.isArray(x.objetivosXY)?x.objetivosXY.slice():null;
      xyPendientes=ultimasXY?ultimasXY.slice():null;
      if(ultimasXY){$p('stlTargetWidth').value=ultimasXY[0];$p('stlTargetHeight').value=ultimasXY[1];}
      ultimoNombre=file.name.replace(/\.vect$/i,'');
      buttons();redraw();
      setProgress(100,'Proyecto abierto: '+file.name+' · CAD y ajustes editables');
    }catch(e){error('No se pudo abrir el proyecto: '+e.message);}
  }
  function reiniciar(){
    ultimasXY=null;xyPendientes=null;ultimoNombre='';
    $p('stlTargetWidth').value='';$p('stlTargetHeight').value='';
    $p('extrudeThickness').value='2';$p('extrudeSlider').value='2';
    $p('extrudeOffset').value='0';$p('stlLiveOffset').value='0';$p('stlOffsetSlider').value='0';
  }
  function alAbrirVista(){
    if(!xyPendientes)return;
    const xy=xyPendientes.slice();xyPendientes=null;
    if(xy.some(v=>!Number.isFinite(Number(v)) || Number(v)<=0))return;
    $p('stlTargetWidth').value=String(xy[0]);$p('stlTargetHeight').value=String(xy[1]);
    setTimeout(()=>{
      if(stlVista && stlRender && stlPreviewBackdrop.style.display==='flex')
        programarOffsetVista(Number($p('stlLiveOffset').value));
    },0);
  }
  for(const id of ['stlTargetWidth','stlTargetHeight']){
    $p(id).addEventListener('input',()=>{
      const x=$p('stlTargetWidth').value,y=$p('stlTargetHeight').value;
      if(x&&y)ultimasXY=[x,y];
    });
  }
  const resetDimAnterior=$p('stlDimReset').onclick;
  $p('stlDimReset').onclick=e=>{
    if(resetDimAnterior)resetDimAnterior.call($p('stlDimReset'),e);
    ultimasXY=null;xyPendientes=null;
  };
  $p('projectSave').addEventListener('click',guardar);
  $p('stlProjectSave').addEventListener('click',guardar);
  $p('projectOpen').addEventListener('click',()=>{$p('projectFileInput').value='';$p('projectFileInput').click();});
  $p('projectFileInput').addEventListener('change',e=>abrir(e.target.files?.[0]));
  window.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&!e.shiftKey){
      e.preventDefault();e.stopImmediatePropagation();guardar();
    }
  },true);
  window.VectorizadorProyectos={construir,abrir,leerProyecto,alAbrirVista,reiniciar};
})();
