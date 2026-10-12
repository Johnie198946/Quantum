import Versions from '../production/Versions';
import TravelPracticalInfo from '../production/TravelPracticalInfo';
import {invoke} from '../production/bridge';
import FloatingField from '../components/FloatingField';
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { AnimatePresence } from 'motion/react';
import { useTravel } from '../TravelContext';
import { images } from '../data';
import { TopBar, Primary, Icon, Disclosure, Sheet } from '../components/UI';
import RoutePlaceSurface, { photoRevealOrigin } from '../components/RoutePlaceSurface';
import DiaryPhotoCards, { DiaryPhotoPanel } from '../components/DiaryPhotoCards';
import PreparationChecklist from '../components/PreparationChecklist';
import ReaderAnnotations,{ReaderText} from '../components/journal/ReaderAnnotations';
import TripServices from '../components/services/TripServices';
import JournalDay from '../components/journal/JournalDay';
import JournalEditor from '../components/journal/JournalEditor';
import JournalAssistant from '../components/journal/JournalAssistant';
import JournalEssentials from '../components/journal/JournalEssentials';
import {journalServices} from '../components/journal/journal-model';
import DailyTrail from '../components/DailyTrail';
import SavedPlanSheet from '../components/lifecycle/SavedPlanSheet';
import {JourneyLink} from './JourneyHome';
import BudgetPanel,{BudgetLink} from '../components/budget/BudgetPanel';
import GeographicMap from '../components/GeographicMap';
import { dayNumber, downloadKML } from '../components/mapRoute';
import LiquidNav from '../components/LiquidNav';
import NoteSaveSheet from '../components/journal/NoteSaveSheet';
const guideNav=[['总览','总览','grid'],['沿途','沿途','pin'],['预订','预订','ticket'],['待办','待办','list'],['预算','预算','wallet']];
const preparationTopics = [
  {title:'证件与入境条件',subtitle:'出发前，确认随身资料',image:images.sakurajima},
  {title:'当地交通与开放时间',subtitle:'让沿途的衔接更从容',image:images.senganen},
  {title:'温泉与住宿信息',subtitle:'留一些时间，好好休息',image:images.ibusuki},
  {title:'天气与火山周边公告',subtitle:'看看天气，再决定出发',image:images.kirishima}
];
export function Guide() {
  const {setTodosOpen,requestGenerate,setStage,days,profile,setProfile,saved,openNotebook,entries,notebookConfig}=useTravel();
  const [tab,setTab]=useState(()=>new URLSearchParams(window.location.search).get('view')==='budget'?'预算':'总览'),[opened,setOpened]=useState(null),[modal,setModal]=useState(null),[feedback,setFeedback]=useState('');
  const screen=useRef(null),scroll=useRef(null);
  const close=useCallback(()=>setModal(null),[]);
  useEffect(()=>{if(saved&&modal==='save')setModal(null);},[saved,modal]);
  useEffect(()=>{
    const confirm=()=>{if(document.querySelector('.phone')?.dataset.stage!=='guide'||modal)return;saved?openNotebook('guide'):requestGenerate(()=>setModal('save'));};
    window.addEventListener('quantum-guide-confirm',confirm);
    return()=>window.removeEventListener('quantum-guide-confirm',confirm);
  },[modal,saved,openNotebook,requestGenerate]);
  const changeTab=value=>{setTab(value);scroll.current?.scrollTo({top:0});};
  const exportJSON=()=>invoke('export',{content:JSON.stringify({profile,days:days.map(({image,...day})=>day),entries,notebookConfig},null,2),filename:'travel-journal.json'}).catch(e=>alert(e.message));
  function openTopic(event,index){
    const bounds=screen.current.getBoundingClientRect(),target=event.currentTarget.getBoundingClientRect();
    setModal({kind:'todo',index,origin:{x:(event.detail?event.clientX:target.x+target.width/2)-bounds.x-16,y:(event.detail?event.clientY:target.y+target.height/2)-bounds.y-16,radius:Math.hypot(bounds.width,bounds.height)}});
  }
  const topic=modal?.kind==='todo'?preparationTopics[modal.index]:null;
  return <section ref={screen} className="paper-screen guide-screen guide-calm">
    <TopBar title={profile.destination+'旅行攻略'} onBack={()=>setStage('adopt')}><button className="icon-btn topbar-confirm-icon" aria-label={saved?'查看旅行手记':'保存为旅行手记'} onClick={()=>saved?openNotebook('guide'):requestGenerate(()=>setModal('save'))}><Icon name="check" size={18}/></button><button className="icon-btn" aria-label="行程更多操作" onClick={()=>setModal('more')}><Icon name="more"/></button></TopBar>
    <LiquidNav items={guideNav} value={tab} onChange={changeTab} label="攻略页面" labelPrefix="" className="guide-reader-navigation"/>
    <div className="paper-scroll" ref={scroll}>
      {tab==='总览'&&<div className="guide-overview">
        <figure className="guide-cover-photo"><img src={days[0]?.image||images.neutral} alt="旅行封面"/><figcaption>{profile.destination} · 山与海之间</figcaption></figure>
        <header className="guide-reading-title"><p className="eyebrow">TRAVEL NOTES / {days.length} DAYS</p><h1>把日子，交给山与海。</h1><p>{profile.dates}</p></header>
        <p className="guide-meta">{profile.count} · {profile.pace} · 预算{profile.budget}</p>
        <BudgetLink onOpen={event=>setModal({kind:'budget',origin:photoRevealOrigin(event,screen.current)})}/><h2>这一程，慢慢走</h2><div className="guide-journey-map"><GeographicMap days={days}/><div className="guide-map-actions"><button onClick={()=>setStage('route')}><Icon name="expand" size={12}/>展开路线</button></div></div>
        <div className="paper-route">{days.map((day,index)=><button className="glass guide-route-row" key={day.id} onClick={()=>{setOpened(day.id);changeTab('沿途');}}><img src={day.image} alt=""/><span><small>DAY {String(dayNumber(day)).padStart(2,'0')} · {day.date}</small><strong>{day.place}</strong><span>{day.name}</span></span><Icon name="chevron" size={16}/></button>)}</div>
        <button className="text-btn teal" onClick={()=>changeTab('沿途')}>查看完整行程 →</button>
        <TravelPracticalInfo profile={profile}/><Disclosure title="资料来源与出发前待确认"><div>{profile.evidence?.map(source=><p key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a><small>{source.checked_at}</small></p>)}{profile.openQuestions?.map((question,i)=><p key={i}>{question}</p>)}</div></Disclosure>
      </div>}
      {tab==='沿途'&&<DailyTrail days={days} opened={opened} onToggle={setOpened}/>}
      {tab==='预订'&&<div className="guide-services"><TripServices/></div>}
      {tab==='预算'&&<BudgetPanel/>}
      {tab==='待办'&&<div className="guide-todo"><button type="button" className="guide-linked-todos glass" onClick={()=>setTodosOpen(true)}>查看旅行待办<Icon name="chevron" size={15}/></button><header className="guide-reading-title"><p className="eyebrow">BEFORE YOU GO</p><h1>出发前，再看一眼。</h1><p>把这些小事，慢慢确认好。</p></header>{preparationTopics.map((item,index)=><button className="glass preparation-card" key={item.title} onClick={event=>openTopic(event,index)} aria-label={item.title}><img src={item.image} alt=""/><span><strong>{item.title}</strong><small>{item.subtitle}</small></span><Icon name="chevron" size={16}/></button>)}</div>}
    </div>
    <AnimatePresence>
      {modal?.kind==='budget'&&<Sheet label="旅行账本" onClose={close} revealFrom={modal.origin} className="budget-unfold"><BudgetPanel/></Sheet>}
      {topic&&<RoutePlaceSurface key={topic.title} day={{id:modal.index+1,place:'出发前',date:'待确认',image:topic.image}} origin={modal.origin} photoMeta="出发前 / 待确认" label={topic.title+'详情'} onClose={close}><div className="detail-heading"><div><p className="eyebrow">出发前 · 待确认</p><h2>{topic.title}</h2></div></div><p className="route-brief-text">{topic.subtitle}。</p><PreparationChecklist index={modal.index}/></RoutePlaceSurface>}
      {modal==='save'&&<NoteSaveSheet onClose={close}/>}
      {modal==='more'&&<Sheet label="行程操作" onClose={close}><h2>行程操作</h2><button className="menu-row" onClick={()=>setModal('versions')}>旧版本<Icon name="chevron"/></button><button className="menu-row" onClick={()=>setModal('adjust')}>有变化？告诉我怎么调整<Icon name="chevron"/></button><button className="menu-row" onClick={exportJSON}>导出 JSON<Icon name="chevron"/></button><button className="menu-row" onClick={()=>setStage('workflow')}>回到工作流<Icon name="home"/></button></Sheet>}
      {modal==='versions'&&<Sheet label="旧版本" onClose={close}><Versions/><button className="menu-row" onClick={close}>返回当前行程<Icon name="chevron"/></button></Sheet>}
      {modal==='adjust'&&<Sheet label="调整旅行计划" onClose={close}><h2>想怎样调整？</h2><label>修改意见<FloatingField as="textarea" aria-label="整趟调整意见" rows={4} value={feedback} onChange={e=>setFeedback(e.target.value)}/></label><Primary onClick={()=>{const text=feedback.trim();if(text)setProfile(prev=>({...prev,additional:[prev.additional,text].filter(Boolean).join('；'),requirements:prev.requirements?{...prev.requirements,notes:[...prev.requirements.notes,text]}:undefined}));setStage('route');}}>返回行程调整</Primary></Sheet>}
    </AnimatePresence>
  </section>;
}

export function Notebook() {
  const {setStage,days,noteTitle,setNoteTitle,profile,setProfile,entries,setEntries,notebookConfig,notebookOrigin,notebookRequest}=useTravel();
  const [tab,setTab]=useState(()=>new URLSearchParams(window.location.search).get('view')==='journal'?'旅行日记':'封面'),[dayIndex,setDayIndex]=useState(0),[photoPanel,setPhotoPanel]=useState(null),[workbench,setWorkbench]=useState(null);
  const consumedRequest=useRef(null);
  useEffect(()=>{if(!notebookRequest||consumedRequest.current===notebookRequest.token)return;consumedRequest.current=notebookRequest.token;if(notebookRequest.view==='diary')setTab('旅行日记');const i=days.findIndex(day=>String(day.id)===String(notebookRequest.dayId));if(i>=0)setDayIndex(i);},[notebookRequest,days]);
  const closeWorkbench=useCallback(()=>setWorkbench(null),[]);
  const cover=images[notebookConfig.cover]||days[0]?.image||images.neutral;
  const flags=notebookConfig.flags;
  const d=days[dayIndex]||{id:'cover',items:[]};
  const screen=useRef(null),panelSerial=useRef(0);
  const close=useCallback(()=>setPhotoPanel(null),[]);
  const openPanel=(event,kind,editing=false)=>setPhotoPanel({kind,editing,token:++panelSerial.current,origin:photoRevealOrigin(event,screen.current)});
  const openEditor=event=>openPanel(event,'record',true);
  const saveEntry=(value,media=[])=>{if(!value.trim()&&!media.length)return '写下一点文字，或加入图片、录音。';if(JSON.stringify(profile.journalRecords||{}).length+JSON.stringify(profile.journalChats||{}).length+JSON.stringify(media).length>1800000)return '附件空间已满，请移除草稿中的图片或录音后再保存。';const entry={id:crypto.randomUUID(),text:value.trim(),media,at:Date.now()};setProfile(prev=>({...prev,journalRecords:{...prev.journalRecords,[d.id]:[...(prev.journalRecords?.[d.id]?.length?prev.journalRecords[d.id]:entries[d.id]?[{id:'legacy-'+d.id,text:entries[d.id],media:[],at:Date.now()}]:[]),entry]}}));setEntries(prev=>({...prev,[d.id]:[prev[d.id],value.trim()].filter(Boolean).join('\n\n')}));return '';};
  const copy=async()=>{const text=noteTitle+'\n'+days.map(day=>'DAY '+dayNumber(day)+' '+day.date+' '+day.name+'\n'+journalServices(day,days,profile).map(s=>s.label+'：'+(s.rows.length?s.rows.map(r=>r.name+'（'+r.state+'）').join('、'):s.text+'（建议）')).join('\n')).join('\n\n');try{await navigator.clipboard.writeText(text);}catch{const textarea=document.createElement('textarea');textarea.value=text;document.body.append(textarea);textarea.select();document.execCommand('copy');textarea.remove();}};
  return <section ref={screen} className={'paper-screen notebook-screen notebook-'+tab}><TopBar title={tab==='封面'?'':noteTitle} onBack={()=>setStage(notebookOrigin)}><button className="icon-btn" aria-label="查看手记批注" onClick={()=>setWorkbench({kind:'annotations'})}><Icon name="book" size={15}/></button><button className="icon-btn journal-whole-edit" aria-label="整体编辑旅行手记" onClick={()=>setWorkbench({kind:'edit'})}><Icon name="edit" size={15}/></button></TopBar>{tab==='封面'?<div className="notebook-cover"><header className="journal-cover-heading"><div className="journal-masthead" aria-hidden="true"><span>TRAVEL JOURNAL</span><span>山海作伴</span></div></header><nav className="journal-section-index" aria-label="手记章节">{['封面','旅行日记','实用附录','预算'].map((section,i)=><button key={section} onClick={()=>setTab(section)}><small>{String(i+1).padStart(2,'0')}</small>{section}</button>)}</nav><div className="journal-cover-composition"><figure className="journal-cover-photo glass"><img src={cover} className="notebook-cover-image" alt="旅行手记视觉封面"/><figcaption>在山与海的怀抱中</figcaption></figure><div className={'journal-cover-title '+(profile.destination.length>6?'journal-title-long':'')}><h1>{profile.destination}</h1></div><p className="journal-cover-aside">山与海之间</p></div><div className="cover-copy"><h2><ReaderText dayId={d.id} id="cover-title" text={noteTitle}/></h2><p><ReaderText dayId={d.id} id="cover-subtitle" text={profile.journal?.subtitle||'山与海之间，遇见更慢的日子'}/></p><p>{profile.dates}<br/>{profile.count} · {profile.interests.join('、')}</p><div className="cover-route"><small>游览顺序</small><p>{days.map(day=>day.place).join(' → ')}</p></div>{!!days.length&&<JourneyLink/>}<button className="lifecycle-snapshot-link" onClick={()=>setWorkbench({kind:'saved-plan'})}>对照保存时的安排<Icon name="layers" size={13}/></button><BudgetLink onOpen={()=>setTab('预算')}/><p className="private-line"><Icon name="lock" size={16}/>仅自己可见</p><Primary className="teal-primary" onClick={()=>setTab('旅行日记')}>翻开旅行手记</Primary></div></div>:<><nav className="reader-tabs" aria-label="手记页面">{['封面','旅行日记','实用附录','预算'].map(x=><button key={x} className={tab===x?'active':''} onClick={()=>setTab(x)}>{x}</button>)}</nav><div className="paper-scroll">
    {tab==='旅行日记'&&!days.length&&<p className="guide-meta">还没有每天的安排。已有旅行文字保留在实用附录中。</p>}{tab==='旅行日记'&&!!days.length&&<div className="diary"><div className="day-picker" role="group" aria-label="旅行日记日期">{days.map((day,i)=><button aria-pressed={dayIndex===i} className={dayIndex===i?'active':''} key={day.id} onClick={()=>setDayIndex(i)}>DAY {dayNumber(day)}</button>)}</div><JournalDay day={d} record={entries[d.id]} flags={flags} onRecord={openEditor} onEdit={()=>setWorkbench({kind:'edit'})} onAssistant={mode=>setWorkbench({kind:'assistant',mode})} onSource={event=>openPanel(event,'source')} onSelectDay={id=>{const index=days.findIndex(day=>day.id===id);if(index>=0)setDayIndex(index);}}/></div>}
    {tab==='实用附录'&&<JournalEssentials included={flags[2]} onCopy={copy}/>}
    {tab==='预算'&&<BudgetPanel/>}
  </div>{tab!=='预算'&&<div className="paper-fixed"><Primary className="teal-primary" onClick={tab==='旅行日记'?openEditor:()=>setTab('旅行日记')}>{tab==='旅行日记'?'记下这一刻':'继续写旅行日记'}</Primary>{tab==='旅行日记'&&<button className="journal-ai-dock" aria-label="阅读与批注" onClick={()=>setWorkbench({kind:'assistant',mode:'notes'})}><Icon name="book" size={16}/><span>批注</span></button>}</div>}</>}<ReaderAnnotations root={screen} day={d} showList={workbench?.kind==='annotations'} onClose={closeWorkbench} onJump={(id,block)=>{setTab(block.startsWith('cover-')?'封面':'旅行日记');const i=days.findIndex(day=>day.id===id);if(i>=0)setDayIndex(i);}}/><AnimatePresence>{workbench?.kind==='saved-plan'&&<SavedPlanSheet key="saved-plan" onClose={closeWorkbench}/>} {workbench?.kind==='edit'&&<JournalEditor key="journal-editor" initialDayId={d.id} onClose={closeWorkbench}/>} {workbench?.kind==='assistant'&&<JournalAssistant key={d.id+'-assistant'} day={d} initialMode={workbench.mode} onClose={closeWorkbench}/>} {photoPanel&&<DiaryPhotoPanel key={d.id+'-'+photoPanel.kind+'-'+photoPanel.token} day={d} record={entries[d.id]} showPhoto={flags[1]} panel={photoPanel} onClose={close} onSave={saveEntry}/>}</AnimatePresence></section>;
}
