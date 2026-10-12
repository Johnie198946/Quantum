import {normalizeLedger, plannedEntries, validateEntry, parseMoney} from '../budget/budget-model.js';

export const serviceSourceId=(kind,key)=>'auto-'+(kind==='flight'?'flights':kind)+'-'+key;

// Service prices remain estimates. Only an explicit payment form creates a paid
// ledger snapshot; one source identity prevents counting that estimate twice.
export function serviceExpenseEntry(profile,days,kind,key,record,payment){
 const ledger=normalizeLedger(profile.budgetLedger,profile);
 if(!payment?.paid)return null;
 const group=kind==='flight'?'flights':kind;
 const next={...profile,servicePlan:{...profile.servicePlan,[group]:{...profile.servicePlan?.[group],[key]:record}}};
 const source=plannedEntries(next,days,ledger).find(row=>row.sourceId===serviceSourceId(kind,key));
 if(!source)throw new Error('这项安排暂时无法关联账本。');
 const existing=ledger.entries.find(row=>row.sourceId===source.sourceId&&row.status==='paid');
 if(existing)throw new Error('实际费用已计入，请在旅行账本中修改，避免重复。');
 const amount=String(payment.amount??'').trim(),currency=payment.currency||'JPY';
 const entry={...source,amount,currency,date:payment.date||source.date,fxToCNY:String(ledger.rates[currency]??''),status:'paid',payments:[{memberId:payment.payer,amount}],split:{mode:'equal',members:payment.members||ledger.members.map(member=>member.id)},createdAt:new Date().toISOString(),sourceDescription:'用户确认的实际支付总额'};
 const errors=validateEntry(entry,ledger.members);
 if(errors.length)throw new Error(errors.join('；'));
 return entry;
}

export function applyServiceRecord(profile,days,kind,key,value){
 const {expenseDraft,...record}=value,group=kind==='flight'?'flights':kind;
 const entry=serviceExpenseEntry(profile,days,kind,key,record,expenseDraft);
 const next={...profile,servicePlan:{...profile.servicePlan,[group]:{...profile.servicePlan?.[group],[key]:record}}};
 if(!entry)return next;
 const ledger=normalizeLedger(profile.budgetLedger,profile);
 next.budgetLedger={...ledger,entries:[...ledger.entries.filter(row=>(row.sourceId||row.id)!==entry.sourceId),entry]};
 return next;
}

export function serviceAmount(record,profile={}){
 if(!record)return null;
 const currency=record.priceCurrency||record.currency||'JPY',price=parseMoney(record.price,currency);
 if(price===null)return null;
 let multiplier=1;
 if(record.kind==='hotel'){
  const nights=record.dateISO&&record.checkout?Math.round((Date.parse(record.checkout)-Date.parse(record.dateISO))/86400000):1;
  multiplier=(Number(record.units)||1)*Math.max(1,nights||1);
 }else if(['restaurant','activity'].includes(record.kind)||record.priceUnit==='／人'||record.ticket?.priceUnit==='／人'||record.perPerson===true)multiplier=Math.max(1,parseInt(record.people||profile.count)||1);
 return {amount:Number(record.price)*multiplier,currency};
}
