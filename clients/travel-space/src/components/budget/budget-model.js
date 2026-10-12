// Local ledger arithmetic. Rates are explicitly supplied CNY per source unit;
// Cross-currency rates require explicit user input.
export const CURRENCIES = Object.freeze({CNY:2,USD:2,EUR:2,JPY:0,THB:2});
export const DEFAULT_RATES = Object.freeze({CNY:'1',USD:'',EUR:'',JPY:'',THB:''});
export const CATEGORIES = ['flight','transport','hotel','restaurant','activity','shopping','other'];
const MAX_MINOR=1_000_000_000_000;
const hasCurrency=code=>Object.hasOwn(CURRENCIES,code);
const scale=code=>10n**BigInt(CURRENCIES[code]);
const isMinor=value=>Number.isSafeInteger(value)&&value>=0&&value<=MAX_MINOR;
const safe=value=>value>=0n&&value<=BigInt(MAX_MINOR)?Number(value):null;
const roundRatio=(numerator,denominator)=>(numerator+denominator/2n)/denominator;
const dateValid=value=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return false;const date=new Date(value+'T12:00:00Z');return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value;};
const unique=values=>[...new Set(values)];
const count=value=>Math.min(20,Math.max(1,parseInt(value,10)||1));

function decimalRatio(value){
 const text=String(value??'').trim();
 if(text.length>30||!/^\d+(?:\.\d{1,12})?$/.test(text))return null;
 const [whole,fraction='']=text.split('.'),numerator=BigInt(whole+fraction),denominator=10n**BigInt(fraction.length);
 return numerator>0n&&numerator<=denominator*1_000_000n?{numerator,denominator}:null;
}
export function parseMoney(value,currency='CNY'){
 if(!hasCurrency(currency)||value===null||value===undefined)return null;
 const text=String(value).trim();
 // Accept grouping only when it is a well-formed thousands grouping.
 if(!/^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(text))return null;
 const [whole,fraction='']=text.replaceAll(',','').split('.'),digits=CURRENCIES[currency];
 if(fraction.length>digits)return null;
 return safe(BigInt(whole)*scale(currency)+BigInt((fraction+'0'.repeat(digits)).slice(0,digits)||'0'));
}
export function amountString(minor,currency='CNY'){
 if(!hasCurrency(currency)||!isMinor(minor))return '';
 const digits=CURRENCIES[currency],integer=BigInt(minor),unit=scale(currency);
 return digits?String(integer/unit)+'.'+String(integer%unit).padStart(digits,'0'):String(integer);
}
export function formatMoney(minor,currency='CNY'){
 if(!hasCurrency(currency)||!Number.isSafeInteger(minor)||Math.abs(minor)>MAX_MINOR)return '—';
 return new Intl.NumberFormat('zh-CN',{style:'currency',currency,minimumFractionDigits:CURRENCIES[currency],maximumFractionDigits:CURRENCIES[currency]}).format(minor/(10**CURRENCIES[currency]));
}
export function convertMinor(minor,from,to,rates=DEFAULT_RATES){
 if(!isMinor(minor)||!hasCurrency(from)||!hasCurrency(to))return null;
 const a=decimalRatio(rates?.[from]),b=decimalRatio(rates?.[to]);
 if(!a||!b)return null;
 if(from===to)return minor;
 return safe(roundRatio(BigInt(minor)*a.numerator*b.denominator*scale(to),scale(from)*a.denominator*b.numerator));
}

// Deterministic largest-remainder allocation. Input order wins equal remainders.
function allocate(total,weights){
 if(!isMinor(total)||!weights.length||weights.some(n=>!isMinor(n)))return null;
 const sum=weights.reduce((n,v)=>n+BigInt(v),0n);
 if(sum===0n)return total===0?weights.map(()=>0):null;
 const values=weights.map((weight,index)=>{const product=BigInt(total)*BigInt(weight);return {index,amount:Number(product/sum),remainder:product%sum};});
 let remainder=total-values.reduce((n,row)=>n+row.amount,0);
 for(const row of [...values].sort((a,b)=>a.remainder===b.remainder?a.index-b.index:a.remainder>b.remainder?-1:1))if(remainder-->0)row.amount++;
 return values.map(row=>row.amount);
}
function originalShares(entry,amount){
 const ids=Array.isArray(entry.split?.members)?entry.split.members:[];
 if(entry.split?.mode==='amount')return ids.map(memberId=>({memberId,amount:parseMoney(entry.split.amounts?.[memberId],entry.currency)}));
 const portions=allocate(amount,ids.map(()=>1));
 return ids.map((memberId,index)=>({memberId,amount:portions?.[index]??null}));
}
export function validateEntry(entry,members=[]){
 const errors=[],ids=new Set(members.map(member=>member.id));
 if(!entry||typeof entry!=='object')return ['账目格式无效'];
 if(typeof entry.id!=='string'||!entry.id.trim())errors.push('账目需要编号');
 if(typeof entry.title!=='string'||!entry.title.trim()||entry.title.length>160)errors.push('请填写不超过160字的账目名称');
 if(!CATEGORIES.includes(entry.category))errors.push('请选择账目类别');
 if(!dateValid(entry.date))errors.push('请选择有效日期');
 if(!hasCurrency(entry.currency))errors.push('请选择支持的币种');
 const amount=parseMoney(entry.amount,entry.currency);
 if(amount===null)errors.push('金额无效，不能为负数、超限或超过币种小数位');
 if(!decimalRatio(entry.fxToCNY))errors.push('请填写有效的原币兑人民币汇率');
 if(!['paid','planned'].includes(entry.status))errors.push('请选择预计或已支付');
 const split=entry.split,splitIds=split?.members;
 if(entry.splitIntent?.unresolved)errors.push(entry.splitIntent.message||'请确认这笔花费的分摊成员');
 if(!['equal','amount'].includes(split?.mode)||!Array.isArray(splitIds)||!splitIds.length||unique(splitIds).length!==splitIds.length||splitIds.some(id=>!ids.has(id)))errors.push('请选择有效且不重复的分账成员');
 else if(amount!==null){
  const shares=originalShares(entry,amount);
  if(shares.some(row=>row.amount===null)||shares.reduce((sum,row)=>sum+(row.amount||0),0)!==amount)errors.push('每人分账金额之和必须等于总额');
 }
 const payments=Array.isArray(entry.payments)?entry.payments:[];
 if(entry.status==='paid'){
  if(!payments.length||payments.some(row=>!ids.has(row.memberId))||unique(payments.map(row=>row.memberId)).length!==payments.length)errors.push('请选择有效且不重复的支付成员');
  const amounts=payments.map(row=>parseMoney(row.amount,entry.currency));
  if(amounts.some(value=>value===null)||amount!==null&&amounts.reduce((sum,value)=>sum+(value||0),0)!==amount)errors.push('所有支付金额之和必须等于总额');
 }else if(payments.length)errors.push('预计账目应在确认支付后填写付款人');
 return errors;
}
export function entryBreakdown(entry,baseCurrency='CNY',rates=DEFAULT_RATES){
 // Validation here is independently bounded; summarizeLedger additionally checks membership.
 const original=parseMoney(entry?.amount,entry?.currency),fx=decimalRatio(entry?.fxToCNY);
 if(original===null||!fx||!hasCurrency(baseCurrency))return {amount:0,payments:[],shares:[],error:'金额、币种或历史汇率无效'};
 const conversionRates={...rates,[entry.currency]:entry.fxToCNY},amount=convertMinor(original,entry.currency,baseCurrency,conversionRates);
 if(amount===null)return {amount:0,payments:[],shares:[],error:'结算汇率无效或金额超限'};
 const originals=originalShares(entry,original),payments=entry.status==='paid'&&Array.isArray(entry.payments)?entry.payments:[];
 if(!originals.length||originals.some(row=>row.amount===null)||originals.reduce((sum,row)=>sum+row.amount,0)!==original)return {amount:0,payments:[],shares:[],error:'分账金额不等于总额'};
 const payerWeights=payments.map(row=>parseMoney(row.amount,entry.currency));
 if(payerWeights.some(value=>value===null)||entry.status==='paid'&&payerWeights.reduce((sum,value)=>sum+value,0)!==original)return {amount:0,payments:[],shares:[],error:'付款金额不等于总额'};
 const shareAmounts=allocate(amount,entry.split.mode==='equal'?originals.map(()=>1):originals.map(row=>row.amount)),paymentAmounts=payments.length?allocate(amount,payerWeights):[];
 if(!shareAmounts||!paymentAmounts)return {amount:0,payments:[],shares:[],error:'分账金额无效'};
 return {amount,payments:payments.map((row,index)=>({memberId:row.memberId,amount:paymentAmounts[index]})),shares:originals.map((row,index)=>({memberId:row.memberId,amount:shareAmounts[index]}))};
}

export function defaultLedger(profile={}){
 return {version:1,baseCurrency:'CNY',target:'',members:Array.from({length:count(profile.count)},(_,index)=>({id:index?'p'+(index+1):'me',name:index?'同行者'+(index+1):'我'})),entries:[],settlements:[],dismissedPlans:[],rates:{...DEFAULT_RATES}};
}
export function normalizeLedger(value,profile={}){
 const fallback=defaultLedger(profile),source=value&&typeof value==='object'?value:{};
 const members=Array.isArray(source.members)?source.members.filter(member=>member&&typeof member.id==='string'&&member.id&&typeof member.name==='string'&&member.name.trim()).map(member=>({id:member.id,name:member.name.trim().slice(0,40)})):[];
 const seen=new Set(),validMembers=members.filter(member=>!seen.has(member.id)&&seen.add(member.id));
 return {...fallback,...source,version:1,members:validMembers.length?validMembers:fallback.members,entries:Array.isArray(source.entries)?source.entries.filter(entry=>entry&&typeof entry==='object'):[],settlements:Array.isArray(source.settlements)?source.settlements.filter(entry=>entry&&typeof entry==='object'):[],dismissedPlans:Array.isArray(source.dismissedPlans)?source.dismissedPlans.filter(row=>row&&typeof row.sourceId==='string'&&typeof row.planFingerprint==='string'):[],rates:{...DEFAULT_RATES,...(source.rates&&typeof source.rates==='object'?source.rates:{})}};
}
function dateFor(record,days,profile){
 if(dateValid(record.dateISO))return record.dateISO;
 if(dateValid(record.date))return record.date;
 const start=profile.dateRange?.[0]||profile.requirements?.date,index=days.findIndex(day=>String(day.id)===String(record.dayId));
 if(!dateValid(start)||index<0)return '';
 const date=new Date(start+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+index);return date.toISOString().slice(0,10);
}
function timesMinor(minor,multiplier){return isMinor(minor)&&Number.isInteger(multiplier)&&multiplier>=0?safe(BigInt(minor)*BigInt(multiplier)):null;}
export function plannedEntries(profile={},days=[],ledger=defaultLedger(profile)){
 const plan=profile.servicePlan||{},rows=[],members=ledger.members.map(member=>member.id);
 for(const group of ['flights','transport','hotel','restaurant','activity']){
  for(const [key,record] of Object.entries(plan[group]||{})){
   if(!record||typeof record!=='object')continue;
   const category=group==='flights'?'flight':group,currency=record.priceCurrency||record.currency||(category==='flight'?'CNY':'JPY');
   const price=parseMoney(record.price,currency);let multiplier=1,sourceDescription='行程估算';
   if(category==='flight'){multiplier=count(record.pax||profile.count);sourceDescription=multiplier+' 人 × 每人票价';}
   if(category==='hotel'){
    const checkIn=record.dateISO||record.date,checkout=record.checkout;
    const nights=dateValid(checkIn)&&dateValid(checkout)?Math.round((Date.parse(checkout)-Date.parse(checkIn))/86400000):1;
    const units=Number(record.units??1);multiplier=nights>0&&units>0?units*nights:NaN;sourceDescription=units+' 间 × '+nights+' 晚 × 每间每晚';
   }
   if(category==='restaurant'||category==='activity'){multiplier=count(record.people||profile.count);sourceDescription=multiplier+' 人 × 每人费用';}
   if(category==='transport'){
    const perPerson=record.priceUnit==='／人'||record.ticket?.priceUnit==='／人'||record.perPerson===true||!record.priceUnit&&record.priceCurrency==='CNY'&&record.people;
    multiplier=perPerson?count(record.people||profile.count):1;sourceDescription=perPerson?multiplier+' 人 × 每人票价':'每车／整段费用';
   }
   const amount=timesMinor(price,multiplier),sourceId='auto-'+group+'-'+key;
   // Invalid source amounts remain visible as invalid rows, never silently count as zero.
   rows.push({id:sourceId,sourceId,title:record.name||({flight:'往返航班',transport:'交通',hotel:'住宿',restaurant:'餐食',activity:'体验'}[category]),category,date:dateFor(record,days,profile),amount:amount===null?'':amountString(amount,currency),currency,fxToCNY:String(ledger.rates?.[currency]??''),status:'planned',payments:[],split:{mode:'equal',members},createdAt:'',sourceDescription,source:'servicePlan'});
  }
 }
 return rows;
}
export const planFingerprint=entry=>JSON.stringify([entry.sourceId,entry.title,entry.amount,entry.currency,entry.date,entry.sourceDescription]);
export function ledgerEntries(profile={},days=[],ledger=normalizeLedger(profile.budgetLedger,profile)){
 const automatic=plannedEntries(profile,days,ledger),current=new Set(automatic.map(entry=>entry.sourceId)),stored=[];
 const seen=new Set();
 // Last saved revision wins; a paid source snapshot survives service edits/deletion.
 for(const entry of [...ledger.entries].reverse()){
  const identity=entry.sourceId||entry.id;
  if(seen.has(identity))continue;seen.add(identity);
  if(entry.sourceId?.startsWith('auto-')&&entry.status==='planned'&&!current.has(entry.sourceId))continue;
  stored.unshift({...entry});
 }
 const overrides=new Set(stored.map(entry=>entry.sourceId).filter(Boolean));
 return [...automatic.filter(entry=>!overrides.has(entry.sourceId)&&!ledger.dismissedPlans?.some(row=>row.sourceId===entry.sourceId&&row.planFingerprint===planFingerprint(entry))),...stored].sort((a,b)=>(a.date||'').localeCompare(b.date||'')||(a.createdAt||'').localeCompare(b.createdAt||''));
}
export function summarizeLedger(entries=[],ledger=defaultLedger()){
 const base=ledger.baseCurrency,summary={paid:0,planned:0,committed:0,byCategory:CATEGORIES.map(category=>({category,paid:0,planned:0})),members:ledger.members.map(member=>({...member,paid:0,share:0,balance:0})),transfers:[],errors:[]},members=new Map(summary.members.map(member=>[member.id,member]));
 for(const entry of entries){
  const errors=validateEntry(entry,ledger.members),breakdown=errors.length?null:entryBreakdown(entry,base,ledger.rates);
  if(errors.length||breakdown?.error){summary.errors.push({id:entry.id,title:entry.title,message:errors.join('；')||breakdown.error});continue;}
  const category=summary.byCategory.find(row=>row.category===entry.category),status=entry.status;
  if(summary.paid+summary.planned+breakdown.amount>MAX_MINOR){summary.errors.push({id:entry.id,title:entry.title,message:'合计金额超限'});continue;}
  summary[status]+=breakdown.amount;category[status]+=breakdown.amount;
  if(status==='paid'){
   for(const row of breakdown.payments)members.get(row.memberId).paid+=row.amount;
   for(const row of breakdown.shares)members.get(row.memberId).share+=row.amount;
  }
 }
 for(const member of summary.members)member.balance=member.paid-member.share;
 for(const settlement of ledger.settlements||[]){
  const from=members.get(settlement.from),to=members.get(settlement.to),minor=parseMoney(settlement.amount,settlement.currency),rates={...ledger.rates,[settlement.currency]:settlement.fxToCNY};
  const amount=minor===null?null:convertMinor(minor,settlement.currency,base,rates);
  if(!from||!to||from===to||amount===null||!dateValid(settlement.date)){summary.errors.push({id:settlement.id,title:'还款',message:'还款成员、金额、日期或汇率无效'});continue;}
  from.balance+=amount;to.balance-=amount;
 }
 summary.committed=summary.paid+summary.planned;
 const debtors=summary.members.filter(member=>member.balance<0).map(member=>({id:member.id,amount:-member.balance})),creditors=summary.members.filter(member=>member.balance>0).map(member=>({id:member.id,amount:member.balance}));
 // A deterministic valid settlement schedule; it does not claim a globally minimal number of transfers.
 for(const debtor of debtors)for(const creditor of creditors){const amount=Math.min(debtor.amount,creditor.amount);if(!amount)continue;summary.transfers.push({from:debtor.id,to:creditor.id,amount});debtor.amount-=amount;creditor.amount-=amount;}
 return summary;
}

const currencyAliases={人民币:'CNY',元人民币:'CNY',美元:'USD',美金:'USD',欧元:'EUR',日元:'JPY',日圆:'JPY',円:'JPY',泰铢:'THB',块:'CNY',元:'CNY',USD:'USD',CNY:'CNY',EUR:'EUR',JPY:'JPY',THB:'THB'};
const chineseDigits={零:0,〇:0,一:1,二:2,两:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9};
function spokenNumber(text){
 if(/^\d[\d,]*(?:\.\d+)?$/.test(text))return text.replaceAll(',','');
 const [integer,fraction]=text.split('点');
 if(fraction&&![...fraction].every(char=>Object.hasOwn(chineseDigits,char)))return null;
 // “一百二” can mean 102 or 120; require the speaker to clarify the missing unit.
 const trailing=integer.match(/([百千万亿])([一二两三四五六七八九])$/);
 if(trailing)return null;
 let total=0,section=0,current=0;
 if(!/[十百千万亿]/.test(integer))current=Number([...integer].map(char=>chineseDigits[char]??'x').join(''));
 else for(const char of integer){
  if(Object.hasOwn(chineseDigits,char)){current=chineseDigits[char];continue;}
  const unit={十:10,百:100,千:1000,万:10000,亿:100000000}[char];if(!unit)return null;
  if(unit<10000){section+=(current||1)*unit;current=0;}else {section+=current;total+=(section||1)*unit;section=0;current=0;}
 }
 if(!Number.isFinite(current))return null;
 return String(total+section+current)+(fraction?'.'+[...fraction].map(char=>chineseDigits[char]).join(''):'');
}
function shoppingCategory(title){return /打车|出租|地铁|公交|车票|交通|滴滴/.test(title)?'transport':/咖啡|早餐|午餐|晚餐|吃饭|餐厅|面包|奶茶|饮料|蛋糕/.test(title)?'restaurant':'shopping';}
function cleanTitle(text){return text.replace(/^[\s，,。；;、]+|[\s，,。；;、]+$/g,'').replace(/^(?:(?:今天|昨天|刚才|我们|我|[\d零〇一二两三四五六七八九十百千万]+\s*(?:个\s*)?(?:人|位)|一起|共同|又|还有|还|然后|和|另外|买了|买|购买了|购买|花了|花费|支付了|支付|付了|付|消费了|消费|了|一共|总共|共|是|用了|用|花)[\s，,]*)+/,'').replace(/(?:，|,)?(?:花了|花费|支付了|支付|付了|付|一共|总共|共|花|是|用了|用)\s*$/,'').trim()||'购物消费';}
function speechSplit(text,members,me){
 const all=members.map(member=>member.id),aliases=new Map(members.map(member=>[member.name,member.id]));
 if(me)aliases.set('我',me.id);
 const counts=unique([...text.matchAll(/([\d零〇一二两三四五六七八九十百千万]+)\s*(?:个\s*)?(?:人|位)(?!民币)/g)].map(match=>Number(spokenNumber(match[1]))).filter(value=>Number.isInteger(value)&&value>0));
 const count=counts.length===1?counts[0]:null;
 const intent=(reason,message,memberIds=[])=>({split:[],splitIntent:{count,memberIds,unresolved:true,reason,message}});
 if(counts.length>1)return intent('conflicting-count','原句出现不同的分摊人数，请确认具体成员与人数。');
 // Match explicit coordinated subjects, rather than every name in a sentence:
 // “小王付款，我和小李平分” must not make 小王 a beneficiary.
 const groups=[...text.matchAll(/([\u4e00-\u9fffA-Za-z0-9]{1,20}?(?:\s*(?:和|跟|与|及|、|，|,|还有|加上)\s*[\u4e00-\u9fffA-Za-z0-9]{1,20}?)+)\s*(?=平分|均分|AA|分摊|一起|共同|购买|买|花|承担)/gi)].map(match=>{
  const names=match[1].split(/\s*(?:和|跟|与|及|、|，|,|还有|加上)\s*/).map(name=>name.replace(/^(?:(?:今天|昨天|刚才|由|给|让|只有|仅|是|叫))+/,'').trim()).filter(name=>!/(?:付款|付了|支付|垫付|买单)$/.test(name)&&!/^(?:大家|我们|全体|所有人)$/.test(name)&&!/^(?:我们)?[\d零〇一二两三四五六七八九十百千万]+(?:个)?(?:人|位)$/.test(name));
  return {names,ids:unique(names.map(name=>aliases.get(name)).filter(Boolean)),unknown:names.some(name=>!aliases.has(name)),explicitSplit:/^\s*(?:平分|均分|AA|分摊|承担)/i.test(text.slice(match.index+match[0].length))};
 }).filter(group=>group.names.length>=2&&!group.names.some(name=>!aliases.has(name)&&/(?:买|花|\d+(?:\.\d+)?(?:人民币|美元|美金|欧元|日元|泰铢|USD|CNY|EUR|JPY|THB|元|块))/i.test(name)));
 const meaningful=groups.filter(group=>group.ids.length),unknown=groups.some(group=>group.unknown&&(group.ids.length||group.explicitSplit));
 if(unknown)return intent('unknown-members','原句提到的部分分摊成员不在同行名单中，请补充或确认成员。',unique(meaningful.flatMap(group=>group.ids)));
 const namedSets=unique(meaningful.map(group=>JSON.stringify([...group.ids].sort()))),named=meaningful[0]?.ids;
 if(namedSets.length>1)return intent('conflicting-count','原句出现不同的分摊成员，请确认这笔花费属于谁。',unique(meaningful.flatMap(group=>group.ids)));
 if(named?.length){
  if(count!==null&&count!==named.length)return intent('named-count-mismatch','原句说 '+count+' 人分摊，但明确姓名只有 '+named.length+' 人，请确认成员。',named);
  return {split:named};
 }
 if(count!==null){
  if(count===all.length)return {split:all};
  return intent('count-mismatch','原句说 '+count+' 人分摊，同行名单有 '+all.length+' 人，请选择具体的 '+count+' 位成员。');
 }
 return {split:/AA|平分|均分|分摊|大家一起|大家分/i.test(text)?all:[me?.id].filter(Boolean)};
}
function paymentContext(text,members){
 const me=members.find(member=>member.id==='me')||members[0],{split,splitIntent}=speechSplit(text,members,me);
 const payers=members.filter(member=>new RegExp(member.name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?:付了|支付|付款|付的|买单|垫付)').test(text));
 const payer=payers.length===1?payers[0]:me;
 const namedClauses=[...text.matchAll(/(?:^|[，,。；;\s])([^\s，,。；;]{1,6})(?:付了|支付了|支付|付款|垫付)/g)];
 const unknown=namedClauses.some(match=>!/买|购物|消费|花/.test(match[1])&&!members.some(member=>match[1]===member.name));
 return {payer,split,splitIntent,ambiguous:payers.length>1,unknown};
}
const escaped=value=>value.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
function amountPayer(prefix,members){return members.find(member=>new RegExp(escaped(member.name)+'(?:付了|支付了|支付|付款|付的|买单|垫付|付)\\s*$').test(prefix));}
export function parseShopping(text,{currency='CNY',members=[{id:'me',name:'我'}],date=new Date().toISOString().slice(0,10)}={}){
 const raw=String(text||'').trim(),missing=[],entries=[];
 if(!raw)return {entries,missing:['说出买了什么和花了多少钱'],message:'例如：今天买了一个包，花了12000日元。'};
 const number='(?:\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+(?:\\.\\d+)?|[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九]+)?)';
 const names='人民币|元人民币|美元|美金|欧元|日元|日圆|泰铢|USD|CNY|EUR|JPY|THB|円|元|块';
 const pattern=new RegExp('('+number+')\\s*('+names+')','gi'),found=[...raw.matchAll(pattern)];
 const context=paymentContext(raw,members),dateValue=dateValid(date)?(/昨天/.test(raw)?new Date(Date.parse(date+'T12:00:00Z')-86400000).toISOString().slice(0,10):date):'';
 if(!dateValue)missing.push('确认消费日期');
 const draft=(title,amount,code,index)=>({id:'voice-'+Date.now()+'-'+index,title:cleanTitle(title),category:shoppingCategory(title),date:dateValue,amount,currency:code,fxToCNY:String(DEFAULT_RATES[code]??''),status:'paid',payments:amount&&context.payer&&!context.ambiguous&&!context.unknown?[{memberId:context.payer.id,amount}]:[],split:{mode:'equal',members:context.split},...(context.splitIntent?{splitIntent:context.splitIntent}:{}),createdAt:new Date().toISOString(),voiceText:raw});
 if(found.length){
  let start=0;const explicitPayments=[];
  for(const [index,match] of found.entries()){
   const code=currencyAliases[match[2].toUpperCase()]||currencyAliases[match[2]],amount=spokenNumber(match[1]);
   const title=raw.slice(start,match.index),preceding=raw[match.index-1],valid=amount!==null&&parseMoney(amount,code)!==null&&!/[\d.\-−]/.test(preceding||'')&&!/\d[eE][+-]?$/.test(raw.slice(0,match.index));
   const payer=amountPayer(title,members);
   if(payer&&entries.length){explicitPayments.push({memberId:payer.id,amount:valid?amount:'',currency:code});}
   else if(entries.length&&/(?:一共|总共|合计)\s*(?:花了|花费|是)?\s*$/.test(title)){missing.push('同时出现明细与合计，请确认合计不重复记账');}
   else entries.push(draft(title,valid?amount:'',code,index));
   start=match.index+match[0].length;
   if(!valid)missing.push('确认“'+match[0]+'”的有效金额');
  }
  if(explicitPayments.length&&entries.length===1){
   const only=entries[0],total=parseMoney(only.amount,only.currency);
   const paymentTotal=explicitPayments.reduce((sum,row)=>sum+(parseMoney(row.amount,row.currency)??NaN),0);
   if(explicitPayments.every(row=>row.currency===only.currency)&&unique(explicitPayments.map(row=>row.memberId)).length===explicitPayments.length&&paymentTotal===total){only.payments=explicitPayments.map(({memberId,amount})=>({memberId,amount}));context.ambiguous=false;}
   else missing.push('核对每人支付金额与总额是否相等');
  }else if(explicitPayments.length)missing.push('请为各笔账目确认付款人和金额');
 }else{
  const expense=new RegExp('(?:花了|花费|支付了|支付|付了|付|消费了|消费|用了)\\s*('+number+')(?![个件只人天])','g'),matches=[...raw.matchAll(expense)];
  let start=0;
  for(const [index,match] of matches.entries()){
   const amount=spokenNumber(match[1]),valid=amount!==null&&parseMoney(amount,currency)!==null&&!/[\d.eE]/.test(raw[match.index+match[0].length]||'');
   entries.push(draft(raw.slice(start,match.index),valid?amount:'',currency,index));start=match.index+match[0].length;
   if(!valid)missing.push('确认消费金额');
  }
  if(!entries.length){entries.push(draft(raw,'',currency,0));missing.push('补充花费金额与币种');}
 }
 if(!hasCurrency(currency)&&!found.length)missing.push('选择支持的币种');
 if(context.ambiguous)missing.push('多人支付，请填写每人付款金额');
 if(context.unknown)missing.push('付款人不在同行成员中，请选择或添加付款人');
 if(context.splitIntent)missing.push(context.splitIntent.message);
 if(!members.length)missing.push('添加支付与分账成员');
 if(found.length>1&&/(?:一共|总共|合计)/.test(raw.slice(found.at(-1).index-6,found.at(-1).index)))missing.push('同时出现明细与合计，请确认合计不重复记账');
 return {entries,missing:unique(missing),message:missing.length?'先核对标出的信息，再确认记账。':'已整理为待确认账目，核对金额、付款人和分账成员后保存。'};
}
