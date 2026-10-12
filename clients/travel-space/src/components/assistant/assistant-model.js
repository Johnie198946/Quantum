// Local proposal schemas. Effects are applied only after explicit confirmation.
export const answerKinds=[['schedule','时间','clock','把当天第一项改到10:00'],['party','人数','person','调整同行人数'],['route','路线','pin','看看从A点到B点的地图'],['weather','天气','sun','补充当天的天气'],['flight','机票','plane','安排航班订票'],['hotel','住宿','bed','安排酒店预订'],['image','照片','image','看看目的地图片'],['rich','笔记','edit','整理成富文本笔记'],['code','代码','code','展示行程代码块'],['flow','流程','layers','展示确认与回填的流程图']];
export const daySignature=day=>JSON.stringify({id:day.id,date:day.date,items:day.items.map(i=>({id:i.journalId||i.id,title:i.title,time:i.time,endTime:i.endTime,description:i.description,status:i.status}))});
const clean=value=>String(value||'').trim().slice(0,2000);
export function inferAnswerKind(question){
 if(/代码|json|code/i.test(question))return 'code';
 if(/流程|工作流|flow/i.test(question))return 'flow';
 if(/天气|气温|晴|下雨/.test(question))return 'weather';
 if(/航班|机票|飞机|订票/.test(question))return 'flight';
 if(/酒店|住宿|订房/.test(question))return 'hotel';
 if(/人数|几人|[一二三四五六七八九十\d]+个人|同行/.test(question))return 'party';
 if(/照片|图片|风景/.test(question))return 'image';
 if(/地图|路线|导航|A点|B点/i.test(question))return 'route';
 if(/\d{1,2}[:：]\d{2}|几点|时间|提前|推迟|调整|换成/.test(question))return 'schedule';
 return 'rich';
}
export function createAnswer({question,quote='',day,days,profile,id=globalThis.crypto.randomUUID()}){
 const kind=inferAnswerKind(question),item=day.items.find(i=>question.includes(i.title)||quote.includes(i.title))||day.items[0],time=question.match(/\d{1,2}[:：]\d{2}/)?.[0]?.replace('：',':').padStart(5,'0');
 const n=question.match(/(\d{1,2})\s*(?:个?人|位)/)?.[1]||({'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6}[question.match(/([一二两三四五六])个?人/)?.[1]]);
 const note=kind==='rich'?'**'+day.place+' · '+day.date+'**\n'+day.items.map(i=>'- '+i.time+' · '+i.title).join('\n')+'\n\n> 关注：'+clean(question)+(quote?'\n'+clean(quote):''):'DAY '+(day.order||day.id)+' · '+day.date+' · '+day.place+'\n'+day.items.map(i=>i.time+' '+i.title).join('\n');
 return {id,kind,dayId:day.id,signature:daySignature(day),question:clean(question),quote:clean(quote),status:'proposal',values:{time:time||item?.time||'',itemIndex:Math.max(0,day.items.indexOf(item)),count:Number(n)||parseInt(profile.count)||1,roomCount:'',automatic:false,note,temperature:profile.assistantWeather?.[day.id]?.temperature??'',condition:profile.assistantWeather?.[day.id]?.condition||'',fromId:day.id,toId:days.find(d=>d.id!==day.id)?.id||day.id,photoId:day.id}};
}
export function validateAnswer(card,values,day){
 if(!day)return '这一天已不存在，请重新提问。';
 if(card.signature!==daySignature(day))return '这一天已更新，请重新生成提议后确认。';
 if(card.status==='applied')return '这张卡片已经回填。';
 if(card.kind==='schedule'&&(!Number.isInteger(Number(values.itemIndex))||Number(values.itemIndex)<0||Number(values.itemIndex)>=day.items.length))return '请先选择当天已有的一项安排。';
 if(card.kind==='weather'&&!['晴','多云','雨','雪'].includes(values.condition))return '请确认天气状况。';
 if(card.kind==='schedule'&&!/^([01]\d|2[0-3]):[0-5]\d$/.test(values.time))return '请填写有效的24小时制时间。';
 if(['party','flight','hotel'].includes(card.kind)&&(!Number.isInteger(Number(values.count))||Number(values.count)<1||Number(values.count)>20))return '同行人数应为1至20人。';
 if(card.kind==='hotel'&&(!Number.isInteger(Number(values.roomCount))||Number(values.roomCount)<1||Number(values.roomCount)>20))return '房间数应为1至20间。';
 if(card.kind==='weather'&&(values.temperature===''||!Number.isFinite(Number(values.temperature))||Number(values.temperature)<-60||Number(values.temperature)>60))return '请补充-60至60°C之间的气温。';
 if(['rich','code','flow','route','image'].includes(card.kind)&&!clean(values.note))return '先写下要收进手记的内容。';
 return '';
}
