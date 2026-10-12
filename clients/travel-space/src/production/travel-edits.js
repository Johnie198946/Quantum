const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const copy=value=>structuredClone(value);
// Apply only the user's differences to the latest server document. Any competing
// change to the same field needs review; notebook prose and actual facts stay current.
export function mergeTravelEdits(base,edited,current){
 const result=copy(current);
 const merge=(before,after,latest,keys)=>{for(const key of keys){if(same(before[key],after[key]))continue;if(!same(latest[key],before[key])&&!same(latest[key],after[key]))throw new Error('这段安排已有新的变化，请重新核对后保存。');if(after[key]===undefined)delete latest[key];else latest[key]=copy(after[key]);}};
 merge(base,edited,result,['destination','date_range','budget','companions','style','days']);
 const old=new Map(base.actions.map(a=>[a.id,a])),newer=new Map(current.actions.map(a=>[a.id,copy(a)])),user=new Map(edited.actions.map(a=>[a.id,a]));
 const keys=['day_id','title','kind','place_id','start','end','timezone','details','from_place_id','to_place_id','source_ids'];
 for(const [id,before] of old){const after=user.get(id),latest=newer.get(id);if(!after){if(latest&&!same(latest,before))throw new Error('准备移除的安排已有新记录，请重新核对。');newer.delete(id);continue;}if(!latest){if(!same(after,before))throw new Error('准备修改的安排已经移除，请重新核对。');continue;}merge(before,after,latest,keys);}
 for(const [id,after] of user)if(!old.has(id)){if(newer.has(id)&&!same(newer.get(id),after))throw new Error('新增安排编号冲突，请重新核对。');newer.set(id,copy(after));}
 const baseOrder=base.actions.map(a=>a.id),userOrder=edited.actions.map(a=>a.id),currentOrder=current.actions.filter(a=>old.has(a.id)).map(a=>a.id);
 if(!same(baseOrder,userOrder)&&!same(baseOrder,currentOrder)&&!same(userOrder,currentOrder))throw new Error('每天的顺序已有新变化，请重新核对。');
 const order=same(baseOrder,userOrder)?current.actions.map(a=>a.id):userOrder;
 result.actions=[...order.filter(id=>newer.has(id)).map(id=>newer.get(id)),...([...newer].filter(([id])=>!order.includes(id)).map(([,a])=>a))];
 return result;
}
