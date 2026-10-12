import React,{useState,useEffect} from 'react';
import FloatingField from '../FloatingField';
import AlignedSelect from '../AlignedSelect';
import {Icon} from '../UI';
import {normalizeLedger} from '../budget/budget-model';
import {serviceSourceId} from './service-expenses';

export default function ServiceExpenseForm({profile,kind,recordKey,estimate,currency='CNY',date='',onChange}){
 const ledger=normalizeLedger(profile.budgetLedger,profile),sourceId=serviceSourceId(kind,recordKey);
 const existing=ledger.entries.find(row=>row.sourceId===sourceId&&row.status==='paid');
 const [payment,setPayment]=useState({paid:false,amount:'',currency,date:'',payer:ledger.members[0]?.id,members:ledger.members.map(member=>member.id)});
 useEffect(()=>{if(existing){setPayment(previous=>({...previous,paid:false}));onChange(null);}},[existing?.id]);
 const update=patch=>{const next={...payment,...patch};setPayment(next);onChange(next);};
 return <section className="service-payment" aria-label="计入旅行账本"><header><Icon name="wallet" size={15}/><h3>收进旅行账本</h3><small>{estimate==null?'费用待核对':'预计 '+currency+' '+Number(estimate).toLocaleString()}</small></header>{existing?<p className="service-paid-status"><Icon name="check" size={13}/>实际费用已计入：{existing.currency} {existing.amount}<small>在旅行账本中修改这笔花费。</small></p>:<><label className="service-paid-check"><input type="checkbox" checked={payment.paid} onChange={event=>update({paid:event.target.checked})}/><span>我已支付，记录实际总额</span></label>{payment.paid&&<div className="service-payment-details"><div className="service-form-grid"><FloatingField aria-label="实际支付总额" inputMode="decimal" value={payment.amount} onChange={event=>update({amount:event.target.value})}/><AlignedSelect label="实际费用币种" value={payment.currency} options={['JPY','CNY','USD','EUR','THB'].map(code=>[code,code])} onChange={currency=>update({currency})}/></div><FloatingField type="date" aria-label="支付日期" value={payment.date||date} onChange={event=>update({date:event.target.value})}/><AlignedSelect label="付款人" value={payment.payer} options={ledger.members.map(member=>[member.id,member.name])} onChange={payer=>update({payer})}/><fieldset><legend>平摊给谁</legend>{ledger.members.map(member=><label key={member.id}><input type="checkbox" checked={payment.members.includes(member.id)} onChange={event=>update({members:event.target.checked?[...payment.members,member.id]:payment.members.filter(id=>id!==member.id)})}/>{member.name}</label>)}</fieldset></div>}</>}</section>;
}
