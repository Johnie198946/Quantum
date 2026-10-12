import FloatingField from './FloatingField';
import { dayNumber } from './mapRoute';
import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion, useIsPresent } from 'motion/react';
import { useTravel } from '../TravelContext';
import { Sheet, Icon, Primary, spring } from './UI';
import RangePicker, { readDates, readTime, dateLabel } from './RangePicker';
import RoutePlaceSurface, { photoRevealOrigin } from './RoutePlaceSurface';
import ActivityDetail from './ActivityDetail';
import {normalizePlan} from './services/planning';
import { images } from '../data';
import { useHoldReorder } from './useHoldReorder';
import DayServiceFacts from './services/DayServiceFacts';
import InlinePassengers from './flight/InlinePassengers';

function ItineraryCard({ item, image, editing, index, setItem, openTime, preview=false }) {
  return <div className="itinerary-card glass">
    <img className="itinerary-thumb" src={item.image || (/城山|市区/.test(item.title)?images.sakurajima:image)} alt="" draggable={false}/>
    <div className="timeline-content">
      <motion.button className="itinerary-time" type="button" aria-label={'选择'+item.title+'时间段'} onClick={event=>openTime?.(event.detail===0)} whileTap={{scale:.88}} tabIndex={preview?-1:undefined}><time>{item.time}{item.endTime&&<><span> — </span>{item.endTime}</>}</time></motion.button>
      {editing ? <><label>安排<FloatingField aria-label={'安排'+(index+1)+'名称'} value={item.title} onChange={e=>setItem(item.id,'title',e.target.value)}/></label><label>具体说明<FloatingField as="textarea" aria-label={'安排'+(index+1)+'说明'} value={item.description} onChange={e=>setItem(item.id,'description',e.target.value)} rows={2}/></label></> : <><h3>{item.title}</h3><p>{item.description}</p></>}
    </div>
    <button type="button" className="itinerary-grip" data-reorder-handle aria-label={'拖动'+item.title+'排序'} tabIndex={preview?-1:0}><Icon name="grip" size={12}/></button>
  </div>;
}
export default function DayDetail({ day, onClose, full = false, routeOrigin }) {
  const { updateDay, profile, setProfile,updateDates,openServices } = useTravel();
  const plan=normalizePlan(profile.servicePlan);
  const [saveError,setSaveError]=useState('');
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => ({...structuredClone(day), items:day.items.map((item,i)=>({...structuredClone(item), id:item.id || 'day-'+day.id+'-item-'+i}))}));
  const [dateRange,setDateRange] = useState(()=>readDates(profile)), [picker,setPicker] = useState(null);
  const [activity,setActivity]=useState(null);
  const reduced = useReducedMotion(), present = useIsPresent();
  useEffect(() => {
    if(!present)return;
    // A rapid reopen during the exit animation must start a fresh draft.
    setDraft({...structuredClone(day),items:day.items.map((item,i)=>({...structuredClone(item),id:item.id||'day-'+day.id+'-item-'+i}))});
    setDateRange(readDates(profile)); setEditing(false); setPicker(null);setActivity(null);
  }, [present, day]);
  const setItem = (id, key, value) => setDraft(prev=>({...prev,items:prev.items.map(item=>item.id===id?{...item,[key]:value}:item)}));
  const reorder = useCallback(items=>setDraft(prev=>({
    ...prev,
    // Activities move between time slots; the schedule itself stays ordered.
    items:items.map((item,index)=>({...item,time:prev.items[index].time,endTime:prev.items[index].endTime}))
  })),[]);
  const drag = useHoldReorder(draft.items,reorder);
  const confirm = () => {
    if(profile.tripSession?.phase&&profile.tripSession.phase!=='before'&&JSON.stringify(dateRange)!==JSON.stringify(readDates(profile))){setSaveError('出发后的日期会保留，请只调整剩余安排。');return;}
    const error=updateDay(draft);if(error){setSaveError(error);return;}
    // Commit the date range with the day draft. Dismissing the day discards both.
    updateDates(dateRange);
    onClose();
  };
  const closePicker = useCallback(()=>setPicker(null),[]);
  const closeActivity = useCallback(()=>setActivity(null),[]);
  const openActivity=(event,item)=>setActivity({id:item.id,origin:photoRevealOrigin(event,event.currentTarget.closest('.screen-host'))});
  const pickedItem = draft.items.find(item=>item.id===picker?.id);
  const Surface=routeOrigin?RoutePlaceSurface:Sheet;
  const liftTarget = drag.lift && drag.refs.current.get(drag.lift.id)?.getBoundingClientRect();
  return <>
    <Surface day={day} origin={routeOrigin} label={'第'+dayNumber(day)+'天行程详情'} onClose={onClose} className={full?'day-detail full-sheet':'day-detail'}>
      <div className="detail-heading"><div><p className="eyebrow">DAY {dayNumber(day)} · {dateLabel(dateRange[0]+dayNumber(day)-1)}</p>{editing?<FloatingField aria-label="当日标题" className="title-input" value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/>:<h2>{draft.name}</h2>}</div><motion.button type="button" aria-label={editing?'完成编辑':'编辑'} aria-pressed={editing} className={'glass edit-toggle '+(editing?'selected':'')} onClick={()=>setEditing(!editing)} whileTap={{scale:.9}}><Icon name={editing?'check':'edit'} size={19}/></motion.button></div>
      {routeOrigin?<p className="route-brief-text">{day.items.map(item=>item.description).join('；')}。</p>:<img className="detail-hero" src={day.image} alt={day.place+'的目的地视觉参考'}/>}
      <p className="sr-only" id={'order-help-'+day.id}>拖动右侧把手排序，长按卡片标记待定，活动使用新位置的时间；轻点时间调整时段，轻点其他区域或按回车查看玩法；键盘可用 Alt 加上下方向键调整，把手支持上下方向键。</p>
      <ol className="day-timeline" aria-label="每日安排" data-dragging={!!drag.lift}>
        {draft.items.map((item,i)=><motion.li layout="position" transition={reduced?{duration:0}:spring} ref={el=>{if(el)drag.refs.current.set(item.id,el);else drag.refs.current.delete(item.id);}} className={'timeline-item item-'+i+(drag.lift?.id===item.id?' held-slot':'')} key={item.id} data-item-id={item.id} data-pending-key={'day-'+day.id+'-item-'+item.id} tabIndex={0} aria-label={item.title} aria-describedby={'order-help-'+day.id} onContextMenu={e=>e.preventDefault()} onPointerDown={e=>drag.start(e,item)} onTouchStart={e=>drag.start(e,item)} onKeyDown={e=>{drag.keyDown(e,item);if(e.key==='Enter'&&e.target===e.currentTarget&&!editing){e.preventDefault();openActivity(e,item);}}} onClick={e=>{if(!editing&&drag.allowTap()&&!e.target.closest('button,input,textarea,label'))openActivity(e,item);}}>
          <ItineraryCard item={item} image={day.image} editing={editing} index={i} setItem={setItem} openTime={keyboard=>{if(keyboard||drag.allowTap())setPicker({kind:'time',id:item.id});}}/>
        </motion.li>)}
      </ol>
      <span className="sr-only" role="status" aria-live="polite">{drag.announcement}</span>
      <DayServiceFacts day={draft} items={draft.items} profile={profile} plan={plan} onOpen={openServices}/>
      <div className="detail-meta"><motion.button type="button" className="date-entry" aria-label="选择旅行日期" onClick={()=>setPicker({kind:'date'})} whileTap={{scale:.94}}><Icon name="calendar" size={16}/>{dateLabel(dateRange[0])+' — '+dateLabel(dateRange[1])}</motion.button><span>{profile.pace}</span></div>
      <InlinePassengers scope="行程" value={parseInt(profile.count)||1} onChange={value=>setProfile(prev=>({...prev,count:value+'人'}))}/>
      <p role="status" className="lifecycle-error">{saveError}</p><Primary onClick={confirm}>确认行程</Primary>
    </Surface>
    {createPortal(<AnimatePresence>{drag.lift&&<motion.div aria-hidden="true" className="itinerary-lift" key={drag.lift.id} style={{top:drag.lift.top,left:drag.lift.left,width:drag.lift.width}} initial={{scale:1,y:0}} animate={{scale:reduced?1:1.035,y:drag.lift.y,rotate:reduced?0:Math.max(-2,Math.min(2,drag.lift.y/110))}} exit={{scale:1,rotate:0,y:liftTarget?liftTarget.top-drag.lift.top:drag.lift.y,opacity:0}} transition={{type:'spring',stiffness:650,damping:38}}><ItineraryCard item={draft.items.find(item=>item.id===drag.lift.id)||drag.lift.item} image={day.image} editing={false} preview/></motion.div>}</AnimatePresence>,document.body)}
    <AnimatePresence>{picker&&<RangePicker key={picker.kind} kind={picker.kind} initial={picker.kind==='time'?readTime(pickedItem):dateRange} title={pickedItem?.title} onClose={closePicker} onConfirm={value=>{if(picker.kind==='time')setDraft(prev=>({...prev,items:prev.items.map(item=>item.id===picker.id?{...item,...value}:item)}));else setDateRange(value);setPicker(null);}}/>}</AnimatePresence>
    <AnimatePresence>{activity&&<ActivityDetail key={activity.id} item={draft.items.find(item=>item.id===activity.id)} day={draft} origin={activity.origin} onClose={closeActivity}/>}</AnimatePresence>
  </>;
}
