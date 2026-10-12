import React from 'react';
import {createPortal} from 'react-dom';
import {Sheet} from './UI';
export function flightOrigin(element){
 const phone=element?.closest('.phone')||document.querySelector('.phone'),bounds=phone?.getBoundingClientRect(),rect=element?.getBoundingClientRect();
 return rect&&bounds?{x:rect.left+rect.width/2-bounds.left,y:rect.top+rect.height/2-bounds.top,width:rect.width,height:rect.height}:{x:(phone?.clientWidth||390)/2,y:160,width:200,height:54};
}
export default function FlyingPanel({origin,children,...props}){
 return createPortal(<Sheet {...props} flyFrom={origin||flightOrigin()}>{children}</Sheet>,document.querySelector('.phone')||document.body);
}
