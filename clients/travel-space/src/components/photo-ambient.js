const cache=new Map();
const fallback=[201,209,199];

// Sample the crop actually visible in the magazine, then find its dominant tone.
export function photoAmbientColor(image){
 const aspect=image.clientWidth/image.clientHeight||1,key=image.currentSrc+'@'+aspect.toFixed(2);
 if(cache.has(key))return cache.get(key);
 try{
  const canvas=document.createElement('canvas');canvas.width=48;canvas.height=48;
  const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return fallback;
  const width=image.naturalWidth,height=image.naturalHeight;if(!width||!height)return fallback;
  const cropWidth=Math.min(width,height*aspect),cropHeight=Math.min(height,width/aspect);
  context.drawImage(image,(width-cropWidth)/2,(height-cropHeight)/2,cropWidth,cropHeight,0,0,48,48);
  const pixels=context.getImageData(0,0,48,48).data,bins=new Map();
  for(let i=0;i<pixels.length;i+=4){
   const r=pixels[i],g=pixels[i+1],b=pixels[i+2],light=.2126*r+.7152*g+.0722*b;
   if(pixels[i+3]<128||light<24||light>238)continue;
   const binKey=(r>>5)*64+(g>>5)*8+(b>>5),weight=.65+(Math.max(r,g,b)-Math.min(r,g,b))/255;
   const bin=bins.get(binKey)||{weight:0,r:0,g:0,b:0};bin.weight+=weight;bin.r+=r*weight;bin.g+=g*weight;bin.b+=b*weight;bins.set(binKey,bin);
  }
  const dominant=[...bins.values()].sort((a,b)=>b.weight-a.weight)[0];if(!dominant)return fallback;
  const raw=[dominant.r,dominant.g,dominant.b].map(v=>v/dominant.weight),grey=.2126*raw[0]+.7152*raw[1]+.0722*raw[2];
  // A pastel version of the photo tone keeps the established muted glass palette.
  const muted=raw.map(v=>(grey+(v-grey)*.65)*.62+255*.38),light=.2126*muted[0]+.7152*muted[1]+.0722*muted[2];
  const lift=light<190?(190-light)/(255-light):0;
  const color=muted.map(v=>Math.round(v+(255-v)*lift));
  cache.set(key,color);return color;
 }catch{return fallback;}
}

export function blendPhotoColors(colors,photos,progress){
 const position=Math.max(0,Math.min(photos.length-1,progress)),index=Math.floor(position),fraction=position-index;
 const a=colors[photos[index].id]||fallback,b=colors[photos[Math.min(index+1,photos.length-1)].id]||a;
 return a.map((v,i)=>+(v+(b[i]-v)*fraction).toFixed(2));
}
