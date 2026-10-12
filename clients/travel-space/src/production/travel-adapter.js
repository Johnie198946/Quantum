import {images} from '../data';
import {importTravelDocument,exportTravelDocument} from '../components/lifecycle/travel-adapter';

const statuses={planned:'待开始',delayed:'已延后',in_progress:'进行中',completed:'已完成',cancelled:'已取消',skipped:'已跳过'};
export function documentToState(document, previous={}) {
  if(document.schema_version!==2||!Array.isArray(document.actions)||!Array.isArray(document.stops)) throw new Error('服务端旅行成果格式不受支持。');
  const imported=importTravelDocument(document);
  const places=new Map(document.stops.map(p=>[p.id,p])), groups=new Map();
  const excluded=new Set((document.days||[]).filter(d=>d.selected===false).map(d=>d.id));
  for(const action of document.actions){
    if(excluded.has(action.day_id))continue;
    if(!groups.has(action.day_id))groups.set(action.day_id,[]);
    groups.get(action.day_id).push(action);
  }
  const client=document.client_state?.version===1?document.client_state:{};
  const dayMetadata=new Map((Array.isArray(document.days)?document.days:[]).filter(d=>d&&typeof d.id==='string').map(d=>[String(d.id),d]));
  const days=[...groups].map(([id,actions],index)=>{
    const located=actions.map(a=>places.get(a.place_id)).find(p=>Number.isFinite(p?.latitude)&&Number.isFinite(p?.longitude));
    const primary=actions.filter(a=>a.kind==='experience').map(a=>places.get(a.place_id)).find(p=>p?.name);
    const anchor=primary||located||actions.map(a=>places.get(a.place_id)||places.get(a.to_place_id)).find(p=>p?.name);
    const photo=document.photo_references?.find(p=>p.place_id===anchor?.id&&p.image_url)?.image_url;
    const importedDay=imported.days.find(d=>String(d.id)===String(id)),date=importedDay?.dateISO;
    const saved=client.days?.find(d=>String(d.id)===String(id));
    const metadata=dayMetadata.get(String(id));
    return {...importedDay,...saved,id,order:index+1,name:saved?.name||(typeof metadata?.title==='string'?metadata.title:'')||places.get(actions[0]?.place_id)?.name||document.destination,summary:typeof metadata?.journal==='string'?metadata.journal:'',
      place:anchor?.name||document.destination,date:date||'日期未定',image:photo||images.neutral,
      imageSource:photo?'来源照片':'风景示意',geo:located?{lat:located.latitude,lon:located.longitude,anchor:located.name}:null,
      items:actions.map(a=>({...a,id:a.id,journalId:a.id,time:importedDay.items.find(i=>i.id===a.id)?.time||'',endTime:importedDay.items.find(i=>i.id===a.id)?.endTime||'',
        title:a.title,description:a.details,status:statuses[a.status],source_ids:a.source_ids,
        timezone:a.timezone,kind:a.kind,bookingReference:a.booking_reference,actualStart:a.actual_start,actualEnd:a.actual_end}))};
  });
  const profile={...previous,...client.profile,...imported.profileFields,destination:document.destination,dates:document.date_range||'日期未定',
    budget:document.budget||'未定',count:document.companions?document.companions+'人':'人数未定',
    interests:client.profile?.interests||previous.interests||[],evidence:document.sources||[],openQuestions:document.open_questions||[],
    alternativeDays:(document.days||[]).filter(d=>d.selected===false),guideJournal:document.journal||'',notebookSupplement:document.notebook_supplement||'',practicalGuidance:Array.isArray(document.practical_guidance)?document.practical_guidance:[],budgetBreakdown:Array.isArray(document.budget_breakdown)?document.budget_breakdown:[]};
  const facts=Object.fromEntries(document.actions.filter(a=>a.status!=='planned').map(a=>[a.id,
    {action_id:a.id,day_id:a.day_id,title:a.title,status:a.status,actual_start:a.actual_start,actual_end:a.actual_end}]));
  profile.tripSession={...profile.tripSession,facts,events:[],
    phase:profile.tripSession?.phase|| (Object.keys(facts).length?'during':'before')};
  return {...client,version:1,profile,days,selected:client.selected||[],extraCards:client.extraCards||[],
    entries:client.entries||{},noteTitle:client.noteTitle||document.destination+' · 旅行手记',
    saved:client.saved||false,notebookConfig:client.notebookConfig||{cover:'neutral',flags:[true,true,true]},
    followUps:client.followUps||[],followUpDraft:client.followUpDraft||'',message:client.message||''};
}

export function stateToDocument(document, days, profile={}) {
  const safe={destination:profile.destination||document.destination};
  if(profile.budget&&profile.budget!=='未定')safe.budget=profile.budget;
  if(profile.pace&&profile.pace!=='未定')safe.pace=profile.pace;
  if(/^\d+人?$/.test(profile.count||''))safe.count=profile.count;
  if(profile.dateRange?.length===2)safe.travelDateRange=profile.dateRange.join(' — ');
  const result=exportTravelDocument(safe,days,document);
  const excluded=new Set((document.days||[]).filter(d=>d.selected===false).map(d=>d.id));
  result.actions.push(...document.actions.filter(a=>excluded.has(a.day_id)));
  if(Array.isArray(document.days))result.days.push(...document.days.filter(d=>excluded.has(d.id)));
  return result;
}

export function discoveryPlaces(document) {
  return document.stops.map(place=>({id:place.id,name:place.name,area:place.address,
    image:document.photo_references?.find(p=>p.place_id===place.id&&p.image_url)?.image_url||images.neutral,
    short:place.address||'地址待核对',detail:document.actions.filter(a=>a.place_id===place.id).map(a=>a.details).filter(Boolean).join('\n')||'详情待确认',
    day:document.actions.find(a=>a.place_id===place.id)?.day_id,
    geo:Number.isFinite(place.latitude)&&Number.isFinite(place.longitude)?{lat:place.latitude,lon:place.longitude}:null}));
}
