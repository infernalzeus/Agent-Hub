/* Demo-only GPU version of the approved metallic facet material. */
(function(root){'use strict';
root.AgentHubCrystalSurface={create:function(canvas){
 var gl=canvas.getContext('webgl',{alpha:true,antialias:true,depth:true,preserveDrawingBuffer:true,premultipliedAlpha:false});if(!gl)return null;
 var derivatives=gl.getExtension('OES_standard_derivatives');
 function shader(type,text){var s=gl.createShader(type);gl.shaderSource(s,text);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;}
 var vs=shader(gl.VERTEX_SHADER,'attribute vec3 p;attribute vec3 normal;attribute vec3 centre;attribute vec3 bary;attribute vec3 rim;attribute float grad;uniform mat3 rotation;varying vec3 n;varying vec3 o;varying vec3 b;varying vec3 edge;varying float gradient;varying float height;void main(){gl_Position=vec4(p,1.0);n=rotation*normal;o=centre;b=bary;edge=rim;gradient=grad;height=(rotation*centre).y;}');
 var fs=shader(gl.FRAGMENT_SHADER,(derivatives?'#extension GL_OES_standard_derivatives : enable\n':'')+`precision highp float;
 varying vec3 n;varying vec3 o;varying vec3 b;varying vec3 edge;varying float gradient;varying float height;
 uniform float clock;uniform float pulseAge;uniform vec2 viewport;uniform float ratio;
 void main(){
 vec3 r=normalize(n);float rx=r.x,ry=r.y,rz=r.z;
 float spec1=pow(abs(rx*.2-ry*.35+rz*.91),38.0),spec2=pow(abs(rx*.75+ry*.2+rz*.6),28.0);
 float reflection=.5+.5*sin(rx*5.4+ry*3.7+rz*4.8);
 float strip=pow(max(0.0,cos(rx*7.5+ry*3.1-rz*2.4)),18.0);
 float polish=min(1.0,strip*.7+spec1*.5+spec2*.35);
 float sparkle=pow(max(0.0,cos(o.x*83.0+o.y*71.0+o.z*97.0+rx*12.0+ry*9.0+rz*11.0)),28.0);
 polish=min(1.0,polish+sparkle*.3);
 float energy=(.58+abs(rz)*.16+reflection*.08)*(.82+.18*sin(o.x*95.0+o.y*73.0+o.z*109.0));
 float emerald=.5+.5*sin(o.x*10.0+o.y*6.0+o.z*9.0);
 vec3 colour=floor(vec3(3.0+polish*70.0,(80.0+150.0*emerald)*energy+polish*230.0,(205.0-70.0*emerald)*energy+polish*230.0)+.5);
 float wave=pow(max(0.0,cos(o.x*9.0+o.y*7.0+o.z*11.0-clock*1.8)),14.0);
 float catchLight=.35+.65*pow(.5+.5*sin(o.x*97.0+o.y*83.0+o.z*71.0),3.0);
 float radial=length(gl_FragCoord.xy-viewport*.5)/viewport.x;
 float band=radial-pulseAge*.48;
 float pulse=pulseAge>=0.0&&pulseAge<1.0?exp(-band*band/.0025)*sin(3.14159265*pulseAge):0.0;
 // Independent bottom-to-top glisten, with the globe pulse added separately.
 float risingCentre=.65-mod(clock*.22,1.3);
 float risingBand=height-risingCentre;
 float rising=exp(-risingBand*risingBand/.006)*.6;
 float gleam=(wave+rising)*catchLight+pulse*(1.3+.7*catchLight),tint=.5+.5*sin(o.x*13.0+o.y*8.0+clock*.45);
 colour+=gleam*vec3(18.0,90.0+95.0*tint,185.0-50.0*tint);
 vec3 a=min(vec3(255.0),colour*vec3(1.0,.7,.8));
 vec3 c=min(vec3(255.0),colour+vec3(polish*10.0,0.0,0.0));
 vec3 d=min(vec3(255.0),colour*vec3(.7,.5,.6));
 float t=clamp(gradient,0.0,1.0);vec3 rgb=t<.5?mix(a,c,t*2.0):mix(c,d,(t-.5)*2.0);
 `+(derivatives?`vec3 distance=b/max(fwidth(b),vec3(.00001));float nearest=min(min(edge.x>.5?distance.x:1000.0,edge.y>.5?distance.y:1000.0),edge.z>.5?distance.z:1000.0);float halo=exp(-nearest*nearest/8.0)*.25;float line=1.0-smoothstep(.25*ratio,1.1*ratio,nearest);rgb=mix(rgb,vec3(65.0,235.0,255.0),min(.85,line*.8+halo));`:``)+`
 gl_FragColor=vec4(rgb/255.0,1.0);}`);
 var program=gl.createProgram();gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(program));gl.deleteShader(vs);gl.deleteShader(fs);
 var fixed=gl.createBuffer(),moving=gl.createBuffer(),positions,vertices=0,indices=[],attributes=['normal','centre','bary','rim'],locations=attributes.map(function(a){return gl.getAttribLocation(program,a);});
 function prepare(coords,faces,counts){var data=[];
 for(var f=0;f<faces.length;f++)for(var t=0;t<faces[f].length;t+=3){var ids=[faces[f][t],faces[f][t+1],faces[f][t+2]],a=ids[0]*3,b=ids[1]*3,c=ids[2]*3;
 var ux=coords[b]-coords[a],uy=coords[b+1]-coords[a+1],uz=coords[b+2]-coords[a+2],vx=coords[c]-coords[a],vy=coords[c+1]-coords[a+1],vz=coords[c+2]-coords[a+2];
 var nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx,length=Math.hypot(nx,ny,nz)||1,centre=[(coords[a]+coords[b]+coords[c])/3,(coords[a+1]+coords[b+1]+coords[c+1])/3,(coords[a+2]+coords[b+2]+coords[c+2])/3];
 function rim(u,v){return counts[Math.min(u,v)*4096+Math.max(u,v)]===1?1:0;}var edges=[rim(ids[1],ids[2]),rim(ids[2],ids[0]),rim(ids[0],ids[1])];
 for(var k=0;k<3;k++){indices.push(ids[k]);data.push(nx/length,ny/length,nz/length,centre[0],centre[1],centre[2],k===0?1:0,k===1?1:0,k===2?1:0,edges[0],edges[1],edges[2]);}}
 vertices=indices.length;positions=new Float32Array(vertices*4);gl.bindBuffer(gl.ARRAY_BUFFER,fixed);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);}
 return {draw:function(screen,coords,faces,counts,size,matrix,time,age){if(!positions)prepare(coords,faces,counts);
 for(var t=0;t<vertices;t+=3){var ia=indices[t]*3,ib=indices[t+1]*3,ic=indices[t+2]*3,dx=screen[ic]-screen[ia],dy=screen[ic+1]-screen[ia+1],den=dx*dx+dy*dy||1;
 var grad=[0,((screen[ib]-screen[ia])*dx+(screen[ib+1]-screen[ia+1])*dy)/den,1];
 for(var k=0;k<3;k++){var i=indices[t+k]*3,j=(t+k)*4;positions[j]=screen[i]/size*2-1;positions[j+1]=1-screen[i+1]/size*2;positions[j+2]=-screen[i+2];positions[j+3]=grad[k];}}
 gl.viewport(0,0,canvas.width,canvas.height);gl.useProgram(program);gl.bindBuffer(gl.ARRAY_BUFFER,fixed);for(var i=0;i<4;i++){gl.enableVertexAttribArray(locations[i]);gl.vertexAttribPointer(locations[i],3,gl.FLOAT,false,48,i*12);}
 gl.bindBuffer(gl.ARRAY_BUFFER,moving);gl.bufferData(gl.ARRAY_BUFFER,positions,gl.DYNAMIC_DRAW);var p=gl.getAttribLocation(program,'p'),grad=gl.getAttribLocation(program,'grad');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,3,gl.FLOAT,false,16,0);gl.enableVertexAttribArray(grad);gl.vertexAttribPointer(grad,1,gl.FLOAT,false,16,12);
 gl.uniformMatrix3fv(gl.getUniformLocation(program,'rotation'),false,new Float32Array([matrix[0],matrix[3],matrix[6],matrix[1],matrix[4],matrix[7],matrix[2],matrix[5],matrix[8]]));gl.uniform1f(gl.getUniformLocation(program,'clock'),time);gl.uniform1f(gl.getUniformLocation(program,'pulseAge'),age);gl.uniform2f(gl.getUniformLocation(program,'viewport'),canvas.width,canvas.height);gl.uniform1f(gl.getUniformLocation(program,'ratio'),canvas.width/size);
 gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.enable(gl.CULL_FACE);gl.frontFace(gl.CCW);gl.cullFace(gl.BACK);gl.disable(gl.BLEND);gl.drawArrays(gl.TRIANGLES,0,vertices);
 },destroy:function(){gl.deleteBuffer(fixed);gl.deleteBuffer(moving);gl.deleteProgram(program);var lose=gl.getExtension('WEBGL_lose_context');if(lose)lose.loseContext();}};
}};
})(window);
