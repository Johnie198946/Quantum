import React, { useEffect, useRef, useState } from 'react';

const vertex = `attribute vec2 position; varying vec2 uv; void main(){uv=position;gl_Position=vec4(position,0.,1.);}`;
const fragment = `
precision highp float;
varying vec2 uv;
uniform float clock, fill, agitation;
uniform vec2 tilt;
float surface(vec3 p){
  float wave=(sin(p.x*4.3+clock*2.1)*.045+sin(p.z*5.1-clock*1.8)*.032+sin(p.x*7.+p.z*3.+clock*2.9)*.015)*agitation;
  return -1.+2.*fill+(p.x*tilt.x+p.z*(.18+tilt.y)+wave)*sin(fill*3.14159);
}
void main(){
  vec3 ro=vec3(0.,0.,3.);
  vec3 rd=normalize(vec3(uv*1.09,-3.));
  float b=dot(ro,rd), disc=b*b-8.;
  if(disc<0.){gl_FragColor=vec4(0.);return;}
  float front=-b-sqrt(disc),back=-b+sqrt(disc);
  vec3 hit=ro+rd*front,n=normalize(hit);
  float length=0.,first=back;
  for(int i=0;i<56;i++){
    float t=mix(front,back,(float(i)+.5)/56.);
    vec3 p=ro+rd*t;
    if(p.y<surface(p)&&fill>.001){length+=(back-front)/56.;first=min(first,t);}
  }
  vec3 color=vec3(.90,.93,.91);
  float alpha=.17;
  if(length>0.){
    vec3 point=ro+rd*first;
    float density=1.-exp(-length*1.6);
    color=mix(vec3(.70,.83,.84),vec3(.28,.47,.54),density*.82);
    color+=.045*sin(point.x*11.+point.z*6.+clock*1.2)*sin(point.y*8.-clock*.9);
    if(first>front+.04&&fill<.995){
      float dx=(surface(point+vec3(.012,0.,0.))-surface(point-vec3(.012,0.,0.)))/.024;
      float dz=(surface(point+vec3(0.,0.,.012))-surface(point-vec3(0.,0.,.012)))/.024;
      vec3 normal=normalize(vec3(-dx,1.,-dz));
      float spec=pow(max(0.,dot(reflect(normalize(vec3(.6,-1.,-.5)),normal),-rd)),22.);
      color=mix(color,vec3(.77,.87,.86),.62)+vec3(.25)*spec;
      alpha=.95;
    }else{alpha=.88;}
  }
  float edge=pow(1.-max(0.,dot(n,-rd)),2.4);
  float highlight=pow(max(0.,dot(n,normalize(vec3(-.55,.7,1.)))),35.);
  float rim=pow(max(0.,dot(n,normalize(vec3(.8,-.5,.3)))),19.);
  color=mix(color,vec3(.80,.87,.85),edge*.32)+vec3(.19)*highlight+vec3(.08)*rim;
  alpha=max(alpha,edge*.48+highlight*.32);
  float mask=smoothstep(0.,.025,disc);
  gl_FragColor=vec4(color,alpha*mask);
}`;

export default function SloshingLiquid({ progress, draining, interaction }) {
  const canvas=useRef(null),values=useRef({progress,draining});
  values.current={progress,draining};
  const [renderer,setRenderer]=useState('fallback');
  useEffect(()=>{
    const node=canvas.current;
    const gl=node.getContext('webgl',{alpha:true,antialias:true,premultipliedAlpha:false,preserveDrawingBuffer:true});
    if(!gl)return;
    const shaders=[];
    function compile(type,source){const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);shaders.push(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;}
    let program;
    try{program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,vertex));gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));}
    catch(error){node.dataset.fallbackReason=error.message;shaders.forEach(s=>gl.deleteShader(s));if(program)gl.deleteProgram(program);return;}
    const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);gl.useProgram(program);
    const attribute=gl.getAttribLocation(program,'position');gl.enableVertexAttribArray(attribute);gl.vertexAttribPointer(attribute,2,gl.FLOAT,false,0,0);
    const uniforms=Object.fromEntries(['clock','fill','tilt','agitation'].map(name=>[name,gl.getUniformLocation(program,name)]));
    const media=matchMedia('(prefers-reduced-motion: reduce)');
    let raf,prior=performance.now(),time=0,x=0,z=0,vx=0,vz=0;
    const resize=()=>{const size=Math.min(512,Math.round(node.clientWidth*Math.min(devicePixelRatio,2)));node.width=node.height=Math.max(1,size);gl.viewport(0,0,node.width,node.height);};
    const observer=new ResizeObserver(resize);observer.observe(node);resize();setRenderer('webgl');
    function frame(now){
      const dt=Math.min(.04,(now-prior)/1000);prior=now;
      if(!media.matches)time+=dt;
      const target=interaction.current;
      const tx=media.matches?0:target.x*.25+Math.sin(time*1.6)*.07;
      const tz=media.matches?0:target.y*.13+Math.cos(time*1.3)*.04;
      vx+=(tx-x)*dt*32;vz+=(tz-z)*dt*32;vx*=Math.exp(-dt*3.2);vz*=Math.exp(-dt*3.2);x+=vx*dt;z+=vz*dt;
      if(media.matches){x=z=vx=vz=0;}
      gl.uniform1f(uniforms.clock,time);gl.uniform1f(uniforms.fill,values.current.progress/100);gl.uniform2f(uniforms.tilt,x,z);gl.uniform1f(uniforms.agitation,media.matches?0:(values.current.draining?1.8:1));gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
      node.dataset.slosh=x.toFixed(4)+','+z.toFixed(4);raf=requestAnimationFrame(frame);
    }
    raf=requestAnimationFrame(frame);
    const lost=event=>{event.preventDefault();cancelAnimationFrame(raf);setRenderer('fallback');};
    node.addEventListener('webglcontextlost',lost);
    return()=>{cancelAnimationFrame(raf);observer.disconnect();node.removeEventListener('webglcontextlost',lost);gl.deleteBuffer(buffer);gl.deleteProgram(program);shaders.forEach(s=>gl.deleteShader(s));};
  },[interaction]);
  return <div className={'slosh-renderer renderer-'+renderer} data-renderer={renderer} aria-hidden="true"><canvas ref={canvas}/><div className="slosh-fallback liquid-fill" style={{height:progress+'%'}}><div className="liquid-wave wave-one"/><div className="liquid-wave wave-two"/><div className="slosh-fallback-surface"/></div></div>;
}
