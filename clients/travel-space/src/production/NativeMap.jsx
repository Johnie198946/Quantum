import React,{useEffect,useState} from 'react';
import {invoke} from './bridge';
export default function NativeMap({bounds,className=''}){
 const [image,setImage]=useState(''),key=JSON.stringify(bounds);
 useEffect(()=>{let active=true;setImage('');if(bounds)invoke('map',{bounds,width:1000,height:620}).then(value=>{if(active)setImage(value.image);}).catch(()=>{});return()=>{active=false;};},[key]);
 return image?<img className={className} src={image} alt="当前行程的地图"/>:<div role="img" className={'production-map-pending '+className} aria-label="地图暂未加载"/>;
}
