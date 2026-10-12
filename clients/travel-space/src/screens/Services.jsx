import React,{useState} from 'react';
import {useTravel} from '../TravelContext';
import {TopBar,Icon} from '../components/UI';
import TripServices from '../components/services/TripServices';
import {runtime} from '../production/runtime';
export default function Services(){const {setStage,servicesFocus,startMaking,requestGenerate}=useTravel(),[working,setWorking]=useState(false);
 const start=async()=>{if(working)return;setWorking(true);try{await startMaking();}catch(error){runtime.publish({error:error.message});}finally{setWorking(false);}};
 return <section className="paper-screen services-screen"><TopBar title="交通与预订" onBack={()=>setStage(servicesFocus.origin||'route')}>{servicesFocus.beforeGeneration&&<button className="icon-btn topbar-confirm-icon" aria-label="开始制作行程" disabled={working} onClick={()=>requestGenerate(start)}><Icon name="check" size={18}/></button>}</TopBar><div className="paper-scroll"><TripServices/></div></section>;}
