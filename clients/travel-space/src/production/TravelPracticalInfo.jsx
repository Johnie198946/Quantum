import React from 'react';
import {Disclosure} from '../components/UI';

const categories={stay:'住宿',flights:'机票',transport:'当地交通',food:'餐饮',meals:'餐饮',activities:'游玩',insurance:'保险',contingency:'预备金',total:'合计'};
export default function TravelPracticalInfo({profile}){
  const guidance=(profile.practicalGuidance||[]).filter(r=>r&&typeof r.details==='string'),budget=(profile.budgetBreakdown||[]).filter(r=>r&&typeof r.value==='string'),sources=new Map((profile.evidence||[]).map(s=>[s.id,s]));
  const references=row=>(Array.isArray(row.source_ids)?row.source_ids:[]).map(id=>sources.get(id)).filter(s=>s&&/^https?:\/\//.test(s.url)).map(s=><a key={s.id} href={s.url} target="_blank" rel="noreferrer">{s.title}</a>);
  return <div className="travel-practical-info">
    {!!profile.guideJournal&&<Disclosure title="完整攻略与摄影参考"><p style={{whiteSpace:'pre-wrap'}}>{profile.guideJournal}</p></Disclosure>}
    {!!profile.notebookSupplement&&<Disclosure title="旅行手记的补充参考"><p style={{whiteSpace:'pre-wrap'}}>{profile.notebookSupplement}</p></Disclosure>}
    {!!guidance.length&&<Disclosure title="交通、季节与行前核对">{guidance.map((row,i)=><section key={i}><h3>{row.title||categories[row.category]||'出发前核对'}</h3><p>{row.details}</p>{row.next_step&&<p className="travel-next-step">下一步 · {row.next_step}</p>}<div className="travel-reference-links">{references(row)}</div></section>)}</Disclosure>}
    {!!profile.alternativeDays?.length&&<Disclosure title="未采用的备选日">{profile.alternativeDays.map(day=><section key={day.id}><h3>{day.title}</h3><p>{day.journal}</p><small>备选参考 · 未计入当前行程</small></section>)}</Disclosure>}
    {!!budget.length&&<Disclosure title="出发前的预算估算"><p>估算与实际花费分别保留，价格以出行日期和实际订单为准。</p>{budget.map((row,i)=><section key={i}><h3>{categories[row.category]||row.title||'费用估算'}</h3><p>{row.value}</p>{row.note&&<p>{row.note}</p>}<div className="travel-reference-links">{references(row)}</div></section>)}</Disclosure>}
  </div>;
}
