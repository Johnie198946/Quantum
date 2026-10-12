import {runtime} from './runtime';
export async function confirmExistingBooking(actionId,reference,client=runtime){
 const generation=client.generation,document=client.document,action=document?.actions?.find(row=>row.id===actionId);
 if(!action||action.locked||!['planned','delayed'].includes(action.status)||action.booking_reference)
  throw new Error('这项安排已更新或已有订单，请重新核对。');
 if(!reference.trim()||reference.length>240)throw new Error('请填写不超过240字的订单确认凭据。');
 const proposed={...document,actions:document.actions.map(row=>row.id===actionId?{...row,booking_reference:reference.trim()}:row)};
 await client.enqueue('revise',{content:JSON.stringify(proposed),reason:'用户明确关联已有预订凭据',confirmedBookings:{[actionId]:reference.trim()}});
 client.document=proposed;client.artifactHash=null;await client.refresh();
 if(generation!==client.generation)throw new Error('行程已切换，请到原任务查看订单关联结果。');
}
