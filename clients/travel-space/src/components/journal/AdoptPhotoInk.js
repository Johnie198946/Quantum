import {useEffect,useRef,useState} from 'react';
import {photoAmbientColor} from '../photo-ambient';

// Sample the visible lower crop where the title sits, rather than the whole photo.
export default function useAdoptPhotoInk(source){
 const image=useRef(null),[ink,setInk]=useState('light');
 useEffect(()=>{
  const element=image.current;if(!element)return;
  const sample=()=>{if(!element.naturalWidth||!element.clientHeight)return;
   photoAmbientColor(element);
   try{const canvas=document.createElement('canvas');canvas.width=48;canvas.height=24;const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)return;
    const aspect=element.clientWidth/element.clientHeight,cropWidth=Math.min(element.naturalWidth,element.naturalHeight*aspect),cropHeight=Math.min(element.naturalHeight,element.naturalWidth/aspect);
    const sx=(element.naturalWidth-cropWidth)/2,sy=(element.naturalHeight-cropHeight)/2+cropHeight*.55;
    context.drawImage(element,sx,sy,cropWidth*.72,cropHeight*.45,0,0,48,24);
    const pixels=context.getImageData(0,0,48,24).data;let luminance=0;
    for(let i=0;i<pixels.length;i+=4)luminance+=.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2];
    setInk(luminance/(pixels.length/4)>158?'dark':'light');
   }catch{setInk('light');}
  };
  element.addEventListener('load',sample);const observer=new ResizeObserver(sample);observer.observe(element);sample();
  return()=>{element.removeEventListener('load',sample);observer.disconnect();};
 },[source]);
 return {image,ink};
}
