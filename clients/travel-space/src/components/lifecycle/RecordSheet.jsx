import React,{useState} from 'react';
import {useTravel} from '../../TravelContext';
import {Sheet} from '../UI';
import VoiceText from '../journal/VoiceText';
import {safeImage,safeAudio} from '../journal/journal-media';
export default function RecordSheet({day,action,onClose}){
 const {profile,setProfile,entries,setEntries}=useTravel(),[text,setText]=useState(''),[media,setMedia]=useState([]);
 const save=()=>{if(!text.trim()&&!media.length)return '写一句话，或留下图片、录音。';if((profile.journalRecords?.[day.id]||[]).length>=50)return '这一天已有50条记录，请先整理或导出。';if(JSON.stringify(profile.journalRecords||{}).length+JSON.stringify(profile.journalChats||{}).length+JSON.stringify(media).length>1800000)return '附件空间已满，请移除部分附件后再保存。';const record={id:crypto.randomUUID(),dayId:day.id,actionId:action?.journalId||action?.id||null,text:text.trim(),at:Date.now(),media};setProfile(prev=>({...prev,journalRecords:{...prev.journalRecords,[day.id]:[...(prev.journalRecords?.[day.id]?.length?prev.journalRecords[day.id]:entries[day.id]?[{id:'legacy-'+day.id,text:entries[day.id],at:Date.now(),media:[]}]:[]),record]}}));setEntries(prev=>({...prev,[day.id]:[prev[day.id],text.trim()].filter(Boolean).join('\n\n')}));onClose();return '';};
 return <Sheet label="随手记下这一刻" onClose={onClose} className="lifecycle-record-sheet"><p className="eyebrow">A LITTLE MOMENT</p><h2>现在，想留下什么？</h2><p>{day.date} · {action?.title||day.place}</p><VoiceText rich value={text} onChange={setText} label="这一刻的记录" placeholder="看到、听到、尝到的，都可以说一句。" onMedia={m=>setMedia(prev=>prev.length<8?[...prev,m]:prev)} onSubmit={save}/><div className="lifecycle-media-drafts">{media.map((m,i)=><div key={i}>{m.kind==='image'&&safeImage(m.src)?<img src={m.src} alt={m.name||'记录图片'}/>:safeAudio(m.src)?<audio controls src={m.src}/>:null}<button onClick={()=>setMedia(prev=>prev.filter((_,j)=>j!==i))} aria-label={'移除记录附件'+(i+1)}>移除</button></div>)}</div><p className="lifecycle-hint">记录收进当天手记，原话与附件会保留。购物花费可在旅行账本里说一句记下。</p></Sheet>;
}
