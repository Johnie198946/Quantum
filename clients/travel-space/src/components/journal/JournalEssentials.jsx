import React,{useState} from 'react';
import {useTravel} from '../../TravelContext';
import {Icon} from '../UI';
import {journalServices} from './journal-model';
import TravelPracticalInfo from '../../production/TravelPracticalInfo';

export default function JournalEssentials({included,onCopy}){
 const {days,profile,openServices,setStage,exportNotebook}=useTravel();
 const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState('');
 const print=async()=>{if(exporting)return;setExporting(true);setExportError('');try{await exportNotebook();}catch(e){setExportError(e.message);}finally{setExporting(false);}};
 return <div className="appendix journal-essentials"><p className="journal-kicker">TRAVEL ESSENTIALS / 03</p><h1>住食行，<br/>随手可查。</h1><p>把沿途的小事，收在一起。<br/>预订、位置与每日记录，都有自己的出处。</p>{included?<><div className="journal-essential-list">{days.map((day,index)=><details key={day.id} open={index===0}><summary><span>DAY {index+1}<small>{day.date}</small></span><strong>{day.place}</strong><Icon name="down" size={12}/></summary><div>{journalServices(day,days,profile).map(s=><section key={s.kind}><header><h2>{s.label}</h2><button aria-label={'查看第'+(index+1)+'天'+s.label+'规划'} onClick={()=>openServices(s.kind,day.id)}><Icon name="expand" size={12}/></button></header>{s.rows.length?s.rows.map(r=><p key={r.kind+r.key}><strong>{r.time||'入住'} · {r.name}</strong><small>{r.state}</small></p>):<p>{s.text}<small>行程建议 · 预订未选定</small></p>}{s.missingMeals.map(meal=><p className="journal-meal-missing" key={meal}>{meal}<small>尚未选择餐厅</small></p>)}</section>)}</div></details>)}</div><p className="journal-essential-note">清单保留用户录入的状态，外部订单需向渠道核对。修改手记不会自动取消或改订。</p><TravelPracticalInfo profile={profile}/><div className="appendix-tools"><button className="text-btn teal" onClick={()=>setStage('route')}>旅行小世界</button><button className="text-btn teal" disabled={exporting} onClick={print}>导出文字 PDF</button>{exportError&&<p role="alert">{exportError}</p>}<button className="text-btn teal" onClick={onCopy}>复制分享摘要</button></div></>:<p>生成手记时未包含实用附录。可在整体编辑中重新开启。</p>}</div>;
}
