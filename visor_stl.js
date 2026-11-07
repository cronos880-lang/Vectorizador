/* Vectorizador V2.0.25 — vista STL 3D sin bibliotecas externas.
 * Renderiza EXACTAMENTE los triángulos recibidos del motor STL, nunca una
 * extrusión aproximada de los contornos 2D. Solo lectura: no modifica CAD/STL.
 */
'use strict';
window.VectorizadorVisorSTL = (() => {
  const VERTICES_MAX = 160000 * 3;
  function exigir(ok, mensaje) { if (!ok) throw Error(mensaje); }
  function compilar(gl, tipo, codigo) {
    const s=gl.createShader(tipo); gl.shaderSource(s,codigo); gl.compileShader(s);
    if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) {
      const e=gl.getShaderInfoLog(s); gl.deleteShader(s);throw Error('Error del visor 3D (shader): '+e);
    }
    return s;
  }

  // Si WebGL no está disponible, rasterizar la misma malla STL en Canvas 2D.
  // Adecuado para piezas habituales; se limita el trabajo en mallas extremas.
  function abrirCanvas2D(canvas,vertices,n,min,max) {
    exigir(n<=30000,'Esta malla supera las 30.000 caras. Para previsualizarla activa la aceleración WebGL del navegador.');
    const ctx=canvas.getContext('2d');
    exigir(ctx,'No se pudo crear un visor 3D en este navegador.');
    const ancho=max[0]-min[0],alto=max[1]-min[1],grosor=max[2]-min[2];
    const centro=min.map((v,j)=>(v+max[j])/2),radio=Math.hypot(ancho,alto,grosor)/2;
    let az=-0.60,el=0.95,zoom=1,grab=null,eliminado=false;
    const caras=[];
    for(let i=0;i<n;i++){
      const off=i*18;
      const a=[vertices[off]-centro[0],vertices[off+1]-centro[1],vertices[off+2]-centro[2]];
      const b=[vertices[off+6]-centro[0],vertices[off+7]-centro[1],vertices[off+8]-centro[2]];
      const c=[vertices[off+12]-centro[0],vertices[off+13]-centro[1],vertices[off+14]-centro[2]];
      const norma=[vertices[off+3],vertices[off+4],vertices[off+5]];
      const light=.34+.52*Math.max(0,-.35*norma[0]-.48*norma[1]+.81*norma[2])+
        .14*Math.max(0,.62*norma[0]+.38*norma[1]+.50*norma[2]);
      const clr=v=>Math.max(0,Math.min(255,Math.round(v*light)));
      caras.push({a,b,c,norma,color:`rgb(${clr(95)},${clr(171)},${clr(250)})`});
    }
    function pintar(){
      if(eliminado)return;
      const dpr=Math.min(2,window.devicePixelRatio||1),w=Math.max(1,Math.round(canvas.clientWidth*dpr)),h=Math.max(1,Math.round(canvas.clientHeight*dpr));
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
      ctx.fillStyle='#0b1320';ctx.fillRect(0,0,w,h);
      const sa=Math.sin(az),ca=Math.cos(az),se=Math.sin(el),ce=Math.cos(el);
      const right=[ca,-sa,0],up=[-se*sa,-se*ca,ce],front=[ce*sa,ce*ca,se];
      const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
      const scale=.84*zoom/radio*h/2;
      const proyectar=p=>[w/2+dot(p,right)*scale,h/2-dot(p,up)*scale];
      const frente=[];
      for(const f of caras){
        if(dot(f.norma,front)<=.00001)continue;
        const dep=(dot(f.a,front)+dot(f.b,front)+dot(f.c,front))/3;
        frente.push({f,dep});
      }
      frente.sort((a,b)=>a.dep-b.dep);
      ctx.lineJoin='round';ctx.lineWidth=Math.max(.5,dpr*.45);
      for(const {f} of frente){
        const a=proyectar(f.a),b=proyectar(f.b),c=proyectar(f.c);
        ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(c[0],c[1]);ctx.closePath();
        ctx.fillStyle=f.color;ctx.strokeStyle=f.color;ctx.fill();ctx.stroke();
      }
    }
    function pointerDown(e){if(e.button!==0&&e.pointerType==='mouse')return;grab={x:e.clientX,y:e.clientY,id:e.pointerId};canvas.setPointerCapture(e.pointerId);}
    function pointerMove(e){if(!grab||grab.id!==e.pointerId)return;
      az+=(e.clientX-grab.x)*.008;el=Math.max(-1.48,Math.min(1.48,el+(e.clientY-grab.y)*.008));
      grab={x:e.clientX,y:e.clientY,id:e.pointerId};pintar();
    }
    function pointerUp(e){if(grab&&grab.id===e.pointerId)grab=null;}
    function wheel(e){e.preventDefault();zoom=Math.max(.3,Math.min(6,zoom*Math.exp(-e.deltaY*.001)));pintar();}
    function reset(){az=-0.60;el=0.95;zoom=1;pintar();}
    canvas.addEventListener('pointerdown',pointerDown);
    canvas.addEventListener('pointermove',pointerMove);
    canvas.addEventListener('pointerup',pointerUp);
    canvas.addEventListener('pointercancel',pointerUp);
    canvas.addEventListener('lostpointercapture',pointerUp);
    canvas.addEventListener('wheel',wheel,{passive:false});
    canvas.addEventListener('dblclick',reset);
    window.addEventListener('resize',pintar);
    requestAnimationFrame(pintar);
    return {triangulos:n,medidas:[ancho,alto,grosor],reset,
      destruir(){if(eliminado)return;eliminado=true;
        canvas.removeEventListener('pointerdown',pointerDown);
        canvas.removeEventListener('pointermove',pointerMove);
        canvas.removeEventListener('pointerup',pointerUp);
        canvas.removeEventListener('pointercancel',pointerUp);
        canvas.removeEventListener('lostpointercapture',pointerUp);
        canvas.removeEventListener('wheel',wheel);
        canvas.removeEventListener('dblclick',reset);
        window.removeEventListener('resize',pintar);
      }
    };
  }
  function abrir(canvas, datos) {
    exigir(datos instanceof ArrayBuffer, 'No se recibieron datos binarios STL.');
    exigir(datos.byteLength>=134, 'STL vacío o incompleto.');
    const vista=new DataView(datos);
    const n=vista.getUint32(80,true);
    exigir(n>0 && n*3<=VERTICES_MAX && 84+n*50===datos.byteLength,
      'STL con tamaño o número de triángulos inconsistente.');
    const vertices=new Float32Array(n*3*6);
    let min=[Infinity,Infinity,Infinity], max=[-Infinity,-Infinity,-Infinity];
    for(let i=0;i<n;i++){
      const off=84+i*50;
      const norma=[vista.getFloat32(off,true),vista.getFloat32(off+4,true),vista.getFloat32(off+8,true)];
      for(let j=0;j<3;j++) exigir(Number.isFinite(norma[j]), 'Normal STL no válida.');
      for(let k=0;k<3;k++){
        const base=off+12+k*12,dest=(i*3+k)*6;
        for(let j=0;j<3;j++){
          const v=vista.getFloat32(base+j*4,true);
          exigir(Number.isFinite(v),'Vértice STL no válido.');
          vertices[dest+j]=v;
          min[j]=Math.min(min[j],v); max[j]=Math.max(max[j],v);
          vertices[dest+j+3]=norma[j];
        }
      }
    }
    const ancho=max[0]-min[0],alto=max[1]-min[1],grosor=max[2]-min[2];
    exigir(ancho>0&&alto>0&&grosor>0,'STL sin volumen 3D.');
    const gl=canvas.getContext('webgl',{alpha:false,antialias:true,depth:true,preserveDrawingBuffer:false});
    if(!gl)return abrirCanvas2D(canvas,vertices,n,min,max);
    const vShader=compilar(gl,gl.VERTEX_SHADER,`
      attribute vec3 a_pos; attribute vec3 a_normal;
      uniform vec3 u_center,u_right,u_up,u_front;
      uniform float u_scale,u_aspect,u_depth_scale;
      varying vec3 v_normal;
      void main(){
        vec3 p=a_pos-u_center;
        gl_Position=vec4(dot(p,u_right)*u_scale/u_aspect,
                         dot(p,u_up)*u_scale, -dot(p,u_front)*u_depth_scale, 1.0);
        v_normal=a_normal;
      }`);
    const fShader=compilar(gl,gl.FRAGMENT_SHADER,`
      precision mediump float;
      varying vec3 v_normal;
      void main(){
        vec3 n=normalize(v_normal);
        float diff=max(dot(n,normalize(vec3(-0.35,-0.48,0.81))),0.0);
        float fill=max(dot(n,normalize(vec3(0.62,0.38,0.50))),0.0);
        float light=0.34+0.52*diff+0.14*fill;
        vec3 color=vec3(0.37,0.67,0.98)*light;
        gl_FragColor=vec4(color,1.0);
      }`);
    const prog=gl.createProgram();gl.attachShader(prog,vShader);gl.attachShader(prog,fShader);gl.linkProgram(prog);
    if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw Error('No se pudo iniciar el visor 3D: '+gl.getProgramInfoLog(prog));
    const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,vertices,gl.STATIC_DRAW);
    gl.useProgram(prog);
    const locP=gl.getAttribLocation(prog,'a_pos'),locN=gl.getAttribLocation(prog,'a_normal');
    gl.enableVertexAttribArray(locP);gl.vertexAttribPointer(locP,3,gl.FLOAT,false,24,0);
    gl.enableVertexAttribArray(locN);gl.vertexAttribPointer(locN,3,gl.FLOAT,false,24,12);
    const uCenter=gl.getUniformLocation(prog,'u_center'),uRight=gl.getUniformLocation(prog,'u_right');
    const uUp=gl.getUniformLocation(prog,'u_up'),uFront=gl.getUniformLocation(prog,'u_front');
    const uScale=gl.getUniformLocation(prog,'u_scale'),uAspect=gl.getUniformLocation(prog,'u_aspect');
    const uDepthScale=gl.getUniformLocation(prog,'u_depth_scale');
    let az=-0.60, el=0.95, zoom=1, grab=null, eliminado=false;
    const centro=min.map((v,j)=>(v+max[j])/2),radio=Math.hypot(ancho,alto,grosor)/2;
    gl.uniform3fv(uCenter,centro);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);
    function pintar(){
      if(eliminado)return;
      const dpr=Math.min(2,window.devicePixelRatio||1);
      const w=Math.max(1,Math.round(canvas.clientWidth*dpr)),h=Math.max(1,Math.round(canvas.clientHeight*dpr));
      if(w!==canvas.width||h!==canvas.height){canvas.width=w;canvas.height=h;}
      gl.viewport(0,0,w,h);gl.clearColor(.045,.075,.12,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      const sa=Math.sin(az),ca=Math.cos(az),se=Math.sin(el),ce=Math.cos(el);
      gl.uniform3f(uRight,ca,-sa,0);
      gl.uniform3f(uUp,-se*sa,-se*ca,ce);
      gl.uniform3f(uFront,ce*sa,ce*ca,se);
      gl.uniform1f(uScale,0.84*zoom/radio);
      gl.uniform1f(uDepthScale,0.84/radio);
      gl.uniform1f(uAspect,w/h);
      gl.drawArrays(gl.TRIANGLES,0,n*3);
    }
    function pointerDown(e){if(e.button!==0 && e.pointerType==='mouse')return;grab={x:e.clientX,y:e.clientY,id:e.pointerId};canvas.setPointerCapture(e.pointerId);}
    function pointerMove(e){if(!grab||grab.id!==e.pointerId)return;
      az+=(e.clientX-grab.x)*.008;el=Math.max(-1.48,Math.min(1.48,el+(e.clientY-grab.y)*.008));
      grab={x:e.clientX,y:e.clientY,id:e.pointerId};pintar();
    }
    function pointerUp(e){if(grab&&grab.id===e.pointerId)grab=null;}
    function wheel(e){e.preventDefault();zoom=Math.max(.3,Math.min(6,zoom*Math.exp(-e.deltaY*.001)));pintar();}
    function reset(){az=-0.60;el=0.95;zoom=1;pintar();}
    canvas.addEventListener('pointerdown',pointerDown);
    canvas.addEventListener('pointermove',pointerMove);
    canvas.addEventListener('pointerup',pointerUp);
    canvas.addEventListener('pointercancel',pointerUp);
    canvas.addEventListener('lostpointercapture',pointerUp);
    canvas.addEventListener('wheel',wheel,{passive:false});
    canvas.addEventListener('dblclick',reset);
    window.addEventListener('resize',pintar);
    requestAnimationFrame(pintar);
    return {
      triangulos:n, medidas:[ancho,alto,grosor], reset,
      destruir(){if(eliminado)return;eliminado=true;
        canvas.removeEventListener('pointerdown',pointerDown);
        canvas.removeEventListener('pointermove',pointerMove);
        canvas.removeEventListener('pointerup',pointerUp);
        canvas.removeEventListener('pointercancel',pointerUp);
        canvas.removeEventListener('lostpointercapture',pointerUp);
        canvas.removeEventListener('wheel',wheel);
        canvas.removeEventListener('dblclick',reset);
        window.removeEventListener('resize',pintar);
        gl.deleteBuffer(buf);gl.deleteProgram(prog);gl.deleteShader(vShader);gl.deleteShader(fShader);
      }
    };
  }
  return {abrir};
})();
