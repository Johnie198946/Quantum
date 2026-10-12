import assert from 'node:assert/strict';
const calls=[];
globalThis.window={__quantumBudgetNative:true,addEventListener(){},webkit:{messageHandlers:{quantum:{postMessage:async body=>{calls.push(body);if(body.operation==='voice')return {text:'我买了一个包，花了12000日元'};if(body.operation==='budgetQueueRead')return [{id:'real-shortcut-uuid',text:'我买了一个包，花了12000日元',date:'2026-10-13'}];return {stopped:true};}}}}};
const budget=await import('../src/components/budget/native-budget.js');
assert(budget.nativeBudgetAvailable());assert.equal(await budget.recognizeBudgetSpeech(),'我买了一个包，花了12000日元');
budget.finishNativeBudgetSpeech();budget.cancelNativeBudgetSpeech();
assert(calls.some(c=>c.operation==='voiceStop'&&c.cancel===false));assert(calls.some(c=>c.operation==='voiceStop'&&c.cancel===true));
const result=await budget.calculateBudgetEntry({amount:'12000',currency:'JPY',fxToCNY:'0.05',status:'paid',payments:[{memberId:'me',amount:'12000'}],split:{mode:'equal',members:['me']}},'CNY',{CNY:'1',JPY:'0.05'});
assert.equal(result.amount,60000);assert.equal(result.shares[0].amount,result.amount);
await assert.rejects(budget.calculateBudgetEntry({amount:'12000',currency:'JPY',status:'paid',split:{mode:'equal',members:['me']}},'CNY',{}));
assert.equal((await budget.consumeNativeBudgetDrafts())[0].id,'real-shortcut-uuid');
const before=calls.length;await budget.acknowledgeNativeBudgetDrafts(['real-shortcut-uuid']);assert.equal(calls.length,before); // Only a native cloud note readback may acknowledge.
console.log(JSON.stringify({checks:7,errors:0}));
