import { dayNumber } from './mapRoute';
import React, { useState, useRef, useEffect, useCallback } from 'react';
import {useReducedMotion} from 'motion/react';
import VoiceText from './journal/VoiceText';
import { Icon, Primary, Sheet } from './UI';
import RoutePlaceSurface from './RoutePlaceSurface';

const timeLabel=item=>item.time+(item.endTime?' — '+item.endTime:'');
const sourceCopy='目的地参考图片为AI示意。真实照片与来源沿用现有手记能力。';
const emptyRecord='还没有记录，留给真正出发时的你。';
const titles={plan:'今日安排说明',record:'自己的旅行记录',source:'照片来源与拍摄建议'};

export default function DiaryPhotoCards({day,flags,record,onOpen}) {
  const cards=[
    flags[0]&&{kind:'plan',preview:day.items.map(item=>timeLabel(item)+' '+item.title).join(' → ')},
    {kind:'record',preview:record||emptyRecord},
    flags[1]&&{kind:'source',preview:sourceCopy}
  ].filter(Boolean);
  return <div className="diary-photo-cards">
    {cards.map(({kind,preview})=><button type="button" key={kind} className={'diary-photo-card'+(!flags[1]?' diary-card-without-photo':'')} aria-label={titles[kind]} onClick={event=>onOpen(event,kind)}>
      {flags[1]&&<img src={day.image} alt="" draggable="false"/>}
      <span className="diary-photo-card-panel"><span className="diary-photo-card-grip" aria-hidden="true"/>
        <span className="diary-photo-card-heading"><strong>{titles[kind]}</strong><Icon name="expand" size={14}/></span>
        <span className="diary-photo-card-preview">{preview}</span>
      </span>
    </button>)}
  </div>;
}

export function DiaryPhotoPanel({day,record,panel,onClose,onSave,showPhoto=true}) {
  const [editing,setEditing]=useState(!!panel.editing),[draft,setDraft]=useState(''),[media,setMedia]=useState([]),[recording,setRecording]=useState(false);
  const timer=useRef(null),reduced=useReducedMotion();useEffect(()=>()=>clearTimeout(timer.current),[]);
  const confirm=()=>{const result=onSave(draft,media);if(result)return result;timer.current=setTimeout(onClose,reduced?80:500);return '';};
  const title=titles[panel.kind];
  const Surface=showPhoto?RoutePlaceSurface:Sheet;
  const edit=()=>{setDraft(record||'');setEditing(true);};
  return <Surface day={day} origin={panel.origin} photoMeta={'DAY '+String(dayNumber(day)).padStart(2,'0')+' / '+day.date}
    label={title+'详情'} className={showPhoto?'diary-photo-sheet':'diary-photo-sheet diary-text-sheet'} onClose={onClose}>
    <div className="detail-heading"><div><p className="eyebrow">{day.place} · {day.date}</p><h2>{title}</h2></div></div>
    {panel.kind==='plan'&&<ol className="diary-plan-list">{day.items.map((item,index)=><li key={item.id??index}>
      <time>{timeLabel(item)}</time><div><h3>{item.title}</h3><p>{item.description}</p></div>
    </li>)}</ol>}
    {panel.kind==='record'&&<div className="diary-record-content">{editing?<>
      <VoiceText onListeningChange={setRecording} label="自己的旅行记录" value={draft} onChange={setDraft} rows={5} rich onMedia={item=>setMedia(prev=>[...prev.filter(x=>item.kind!=='audio'||x.kind!=='audio'),item])} onSubmit={confirm}/>
      {media.length>0&&<div className="record-media-drafts">{media.map((m,i)=><div key={i}>{m.kind==='image'?<img src={m.src} alt={m.name}/>:<span><Icon name="mic" size={14}/>录音 · {Math.round(m.seconds)}秒</span>}<button aria-label={'移除记录附件'+(i+1)} onClick={()=>setMedia(prev=>prev.filter((_,j)=>j!==i))}><Icon name="close" size={12}/></button></div>)}</div>}
    </>:<><p className="diary-record-text">{record||emptyRecord}</p><Primary onClick={edit}>{record?'编辑记录':'记下这一刻'}</Primary></>}</div>}
    {panel.kind==='source'&&<div className="diary-source-content"><p>{sourceCopy}</p><p className="diary-photo-source-note">{day.place} · 目的地视觉参考</p></div>}
  </Surface>;
}
