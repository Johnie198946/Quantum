// Foreign rates require user confirmation; retain original source currency.
export const unitsPerCNY=Object.freeze({CNY:1,USD:null,EUR:null,JPY:null,THB:null});
const aliases={人民币:'CNY',美元:'USD',欧元:'EUR',日元:'JPY',泰铢:'THB'};
export const currencyCode=value=>Object.hasOwn(unitsPerCNY,value)?value:aliases[value]||'CNY';
export function formatPrice(amount,currency='CNY',base='CNY',locale='zh-CN'){
 const source=/^[A-Z]{3}$/.test(base)?base:currencyCode(base);
 if(amount==null||!Number.isFinite(Number(amount)))return '费用待核对';
 return new Intl.NumberFormat(locale,{style:'currency',currency:source}).format(Number(amount))+(currencyCode(currency)!==source?' · 汇率待确认':'');
}
export function recommendedFlight(flights,date,time){
 const target=Number(time.slice(0,2))*60+Number(time.slice(3)),sameDay=flights.filter(f=>f.date===date);
 const score=f=>(f.priceCurrency===sameDay[0]?.priceCurrency?f.price:0)+f.duration*.8+f.stops*120+Math.abs(Number(f.time.slice(0,2))*60+Number(f.time.slice(3))-target)*.4;
 return sameDay.reduce((best,f)=>!best||score(f)<score(best)?f:best,null);
}
