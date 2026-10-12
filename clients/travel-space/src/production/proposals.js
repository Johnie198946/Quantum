import {runtime} from './runtime';
import {invoke} from './bridge';
export async function requestProposal(question,quote,schema){
 const generation=runtime.generation;
 const response=await invoke('ask',{question:question+'\n只给出建议，不执行操作。仅返回 JSON，字段：'+schema+'。保留原安排标识和已发生的记录，不编造地点、订单或实际进度。',quote:JSON.stringify(quote)});
 if(runtime.generation!==generation)throw new Error('行程已切换，请重新提出建议。');
 if(response.hasActions)throw new Error('这条请求产生了待确认操作，请在首页对话中检查。');
 let value;try{value=JSON.parse(response.answer.replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,''));}catch{throw new Error('回复尚未形成可确认的修改对照，请补充要求后重试。');}
 if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('建议格式无效。');
 return value;
}
