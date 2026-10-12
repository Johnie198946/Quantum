import {displayServicePrice,displayServiceDistance} from '../../production/service-provider';
import FloatingField from '../FloatingField';
import React,{useState,useEffect,useMemo,useRef,useId} from 'react';
import {motion,AnimatePresence,useReducedMotion,useIsPresent} from 'motion/react';
import {Icon} from '../UI';
import ModeDetails from './ModeDetails';
import RouteMap from './RouteMap';
import {availableRouteModes,routeOptions} from './route-model';
function RouteModePane({children,...props}){
 const present=useIsPresent();
 return <motion.div {...props} aria-hidden={present?undefined:true} inert={present?undefined:''} style={present?undefined:{position:'absolute',left:0,right:0,top:0}}>{children}</motion.div>;
}
export default function RouteDetails({mode,onMode,from,to,fromName,toName,time,date,water,onRoute,settings={},onSettings}){
 const [choice,setChoice]=useState(0),[direction,setDirection]=useState(1),reduced=useReducedMotion(),id=useId(),tabs=useRef([]);
 const generatedKey=JSON.stringify(settings.generatedRoutes??null);
 const args={mode,from,to,fromName,toName,time,date,water,settings};
 const modes=useMemo(()=>availableRouteModes(args),[from?.lat,from?.lon,to?.lat,to?.lon,fromName,toName,time,date,water,generatedKey]);
 const selectedMode=modes.some(([name])=>name===mode)?mode:modes[0]?.[0];
 const options=useMemo(()=>selectedMode?routeOptions({...args,mode:selectedMode}):[],[selectedMode,from?.lat,from?.lon,to?.lat,to?.lon,fromName,toName,time,date,water,generatedKey]);
 const route=options[choice]||options[0],publicMode=['公交车','地铁','火车','渡轮','接驳船'].includes(selectedMode),selectedIndex=modes.findIndex(([name])=>name===selectedMode);
 useEffect(()=>{if(selectedMode&&selectedMode!==mode){setChoice(0);onMode(selectedMode);}},[selectedMode,mode,onMode]);
 useEffect(()=>{onRoute(route||null);},[route,onRoute]);
 const changeMode=(value,index)=>{setDirection(index>=selectedIndex?1:-1);setChoice(0);onMode(value);};
 const keyMode=(event,index)=>{
  const next=event.key==='ArrowRight'?(index+1)%modes.length:event.key==='ArrowLeft'?(index+modes.length-1)%modes.length:event.key==='Home'?0:event.key==='End'?modes.length-1:null;
  if(next!==null){event.preventDefault();changeMode(modes[next][0],next);tabs.current[next]?.focus({preventScroll:true});}
 };
 const motionVariants={enter:d=>({x:reduced?0:d*30,opacity:reduced?1:0}),center:{x:0,opacity:1},exit:d=>({x:reduced?0:-d*30,opacity:reduced?1:0})};
 return <section className="route-detail-design transit-route-design">
  {modes.length>0?<>
   <div className="travel-mode-options mode-detail-tabs route-mode-segment" role="tablist" aria-label="交通方式" aria-orientation="horizontal">
    {modes.map(([name,icon],index)=><button key={name} ref={el=>tabs.current[index]=el} type="button" role="tab" id={id+'-tab-'+index} aria-label={name} aria-selected={selectedMode===name} aria-controls={id+'-panel'} tabIndex={selectedMode===name?0:-1} onClick={()=>changeMode(name,index)} onKeyDown={event=>keyMode(event,index)}>
     {selectedMode===name&&<motion.span className="route-mode-selected" aria-hidden="true" layoutId={id+'-selected-mode'} transition={reduced?{duration:0}:{type:'spring',stiffness:380,damping:31,mass:.8}}/>}
     <Icon name={icon} size={17}/><span>{name}</span>
    </button>)}
   </div>
   <div className="route-mode-viewport" id={id+'-panel'} role="tabpanel" aria-labelledby={id+'-tab-'+selectedIndex} tabIndex={0}><AnimatePresence initial={false} mode="sync" custom={direction}>
    <RouteModePane key={selectedMode} className="route-mode-content" custom={direction} variants={motionVariants} initial="enter" animate="center" exit="exit" transition={{duration:reduced?0:.24,ease:[.2,.7,.2,1]}}>
     <RouteMap from={from} to={to} fromName={fromName} toName={toName} mode={selectedMode} alternate={choice===1}/>
     {!route?<p role="status" className="route-unavailable">这段路线资料待补充。</p>:<>
      {options.length>1&&<div className="route-alternatives" role="group" aria-label="路线比较">{options.map((r,i)=><button type="button" key={r.id} aria-pressed={choice===i} aria-label={'选择'+r.label} onClick={()=>setChoice(i)}><small>{r.label}</small><strong>{r.duration}<span> 分钟</span></strong><span>{displayServiceDistance(r.distance)} · {displayServicePrice(r.price,r.priceCurrency)}</span></button>)}</div>}
      <ol className="route-segment-cards" aria-label="逐段路线">{route.stops.map((stop,i)=><li className="route-segment-card glass" key={route.id+'-'+i}>
       <time>{stop.time||'待确认'}</time><span className="route-segment-icon" aria-hidden="true"><Icon name={stop.icon} size={17}/></span><div><strong>{stop.name||'沿途衔接'}</strong>{stop.instruction&&<p>{stop.instruction}</p>}</div>
      </li>)}</ol>
      {publicMode&&<div className="route-public-facts"><span><Icon name="clock" size={13}/>{route.wait==null?'候车时间待核对':'候车约 '+route.wait+' 分钟'}</span><span><Icon name="ticket" size={13}/>单程 {displayServicePrice(route.price,route.priceCurrency)}</span><p>{selectedMode==='公交车'?'上车前确认方向、站牌与行李位置；下车前确认付款方式。':['火车','地铁'].includes(selectedMode)?'接驳段与铁路段分开确认票制、站台及乘车方向。':'确认出发港、天气与能否携车。'}</p></div>}
      {selectedMode==='出租车'&&<section className="route-mode-information"><div className="service-form-grid"><label>车型<select aria-label="出租车车型" value={settings.vehicle||'普通轿车'} onChange={e=>onSettings('vehicle',e.target.value)}><option>普通轿车</option><option>多人商务车</option><option>无障碍车辆</option></select></label><label>上车位置<FloatingField aria-label="出租车上车位置" value={settings.pickup||''} onChange={e=>onSettings('pickup',e.target.value)} placeholder="到达层／酒店门口"/></label></div><p>普通车通常最多4人；多人或大件行李可选商务车。无障碍车型需预约核验。</p><dl><div><dt>费用范围</dt><dd>{displayServicePrice(route.price,route.priceCurrency)} · 附加费用待核对</dd></div><div><dt>费用构成</dt><dd>起步价＋里程；等候、高速、夜间附加费另计</dd></div><div><dt>下车位置</dt><dd>{toName} · 入口待确认</dd></div></dl></section>}
      {selectedMode==='自驾'&&<section className="route-mode-information"><div className="service-form-grid"><label>路线偏好<select aria-label="自驾道路偏好" value={settings.road||'推荐道路'} onChange={e=>onSettings('road',e.target.value)}><option>推荐道路</option><option>避开收费道路</option><option>避开高速</option></select></label><label>停车要求<select aria-label="停车要求" value={settings.parking||'目的地停车场'} onChange={e=>onSettings('parking',e.target.value)}><option>目的地停车场</option><option>酒店免费停车</option><option>无障碍车位</option></select></label></div><dl><div><dt>油费估计</dt><dd>待核对车辆油耗、油价与实际路程</dd></div><div><dt>停车预算</dt><dd>收费及车位待核验</dd></div><div><dt>收费道路</dt><dd>{settings.road==='避开收费道路'?'偏好已记录，需实际导航确认绕行':'道路收费待查询'}</dd></div></dl><p>取还车、驾驶资格、营业时间、保险与异地还车费一起确认。</p></section>}
      <ModeDetails mode={selectedMode} settings={settings} onSettings={onSettings} route={route} from={from} to={to}/>
      <p className="route-demo-scope">行程资料 · 班次与报价待核验 · 地图连线为路线示意</p>
     </>}
    </RouteModePane>
   </AnimatePresence></div>
  </>:<p role="status" className="route-query-pending">{!from||!to?'地点确定后，显示可用的交通方式与逐段路线。':'这段交通资料待查询。'}</p>}
 </section>;
}
