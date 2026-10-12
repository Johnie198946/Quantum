export const travelDocument={schema_version:2,destination:'测试旅行',date_range:null,companions:2,budget:null,style:'轻松',journal:'原来的手记',open_questions:['核对当天开放时间'],
  sources:[{id:'source-1',title:'测试来源',url:'https://example.org/place',checked_at:'2026-10-12'}],
  stops:[{id:'place-1',name:'第一处风景',address:'实际地址待核对',latitude:31.59,longitude:130.56,source_ids:['source-1']},
    {id:'place-2',name:'第二处风景',address:'实际地址待核对',latitude:null,longitude:null,source_ids:[]}],
  photo_references:[],actions:[
    {id:'action-1',day_id:'day-1',title:'第一处风景',kind:'experience',place_id:'place-1',start:null,end:null,timezone:'Asia/Tokyo',status:'planned',actual_start:null,actual_end:null,locked:false,details:'慢慢走，看一段风景。',booking_reference:'',from_place_id:null,to_place_id:null,source_ids:['source-1']},
    {id:'action-2',day_id:'day-2',title:'第二处风景',kind:'experience',place_id:'place-2',start:null,end:null,timezone:'Asia/Tokyo',status:'planned',actual_start:null,actual_end:null,locked:false,details:'留一点空白给旅程。',booking_reference:'',from_place_id:null,to_place_id:null,source_ids:[]} ]};

export function installFixture(){
  const doc=structuredClone(travelDocument),calls=[];let revision=1,noteMode=false;
  const workflow={id:'workflow-test',title:'旅行测试任务',status:'completed',sourceClientSessionId:'session-test'};
  const execution={id:'execution-test',workflowId:workflow.id,status:'completed',progress:100};
  let artifact={id:'artifact-test-1',contentHash:'a'.repeat(64),metadata:{renderType:'travel_plan_v2',travelRevision:1}};
  window.fixture={calls,doc,workflow,execution};
  window.webkit={messageHandlers:{quantum:{postMessage:async body=>{
    calls.push(body);
    if(window.fixture.failOperation===body.operation){window.fixture.failOperation=null;throw Error('模拟保存失败，请重试');}
    switch(body.operation){
      case 'bootstrap':if(window.fixture.openNote){noteMode=true;artifact={...artifact,id:'note-test'};return {workflows:[],draft:null,note:{workflow,artifact,content:JSON.stringify(doc),noteMode:true,noteId:'note-test'}};}return {workflows:[workflow],draft:null};
      case 'snapshot':return {workflow,execution,artifact,noteMode,noteId:noteMode?'note-test':null,artifacts:[artifact],content:JSON.stringify(doc),clarification:{session:{phase:'completed',roundNumber:1},messages:[],events:[]}};
      case 'draft':return {saved:true};
      case 'saveNotebook':noteMode=true;doc.client_state={...doc.client_state,saved:true};artifact={...artifact,id:'note-test'};return {noteId:'note-test',contentHash:artifact.contentHash,content:JSON.stringify(doc)};
      case 'saveState':
        if(body.hash!==artifact.contentHash)throw new Error('行程已有新版本，请查看变化后重试');
        doc.client_state=structuredClone(body.state);artifact={...artifact,id:noteMode?'note-test':'artifact-test-'+(++revision),contentHash:String(revision%10).repeat(64),metadata:{...artifact.metadata,travelRevision:revision}};
        return {id:artifact.id,contentHash:artifact.contentHash};
      case 'revise':
        if(body.hash!==artifact.contentHash)throw new Error('行程已有新版本，请查看变化后重试');
        Object.assign(doc,JSON.parse(body.content));artifact={...artifact,id:noteMode?'note-test':'artifact-test-'+(++revision),contentHash:String(revision%10).repeat(64)};return {id:artifact.id,contentHash:artifact.contentHash};
      case 'progress':
        if(body.hash!==artifact.contentHash)throw new Error('版本已变化');
        const action=doc.actions.find(a=>a.id===body.actionId);action.status=body.progress;
        if(body.progress==='in_progress')action.actual_start=new Date().toISOString();else action.actual_end=new Date().toISOString();
        artifact={...artifact,id:noteMode?'note-test':'artifact-test-'+(++revision),contentHash:String(revision%10).repeat(64)};return {id:artifact.id,contentHash:artifact.contentHash};
      case 'ask':return {answer:body.question.includes('results')?JSON.stringify({results:window.fixture.results||[]}):'结合当前记录，保留一点不赶路的时间。',hasActions:false};
      case 'versions':return [artifact];
      case 'version':return {content:JSON.stringify(doc)};
      case 'export':return {opened:true};
      case 'printNotebook':
        if(body.hash!==artifact.contentHash||body.artifactId!==artifact.id)throw Error('导出版本未绑定');
        return {opened:true};
      case 'voice':throw new Error('测试权限未开启');
      case 'openTasks':return {opened:true};
      case 'map':throw new Error('测试不读取联网地图');
      case 'tab':return {selected:body.tag};
      default:throw new Error('Unsupported fixture operation: '+body.operation);
    }
  }}}};
}
