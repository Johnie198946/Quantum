import {invoke} from '../../production/bridge.js';
import {entryBreakdown} from './budget-model.js';
// Optional iOS host contract. The offline browser prototype works without it.
// A host must restrict its handler to this app's trusted main-frame page.
const pending = new Map();
let serial = 0;
const bridge = () => globalThis.window?.webkit?.messageHandlers?.quantumBudget;
const unified = () => globalThis.window?.__quantumBudgetNative === true;
export const nativeBudgetAvailable = () => unified() || typeof bridge()?.postMessage === 'function';
const sendCancellation = id => {
  try { bridge()?.postMessage({ id, action: 'speechCancel', payload: {} }); } catch { /* Host is already disconnected. */ }
};

function request(action, payload = {}, timeout = 12000) {
  if (!nativeBudgetAvailable()) return Promise.reject(new Error('当前预览没有连接 iOS 原生能力，可使用文字或浏览器语音记账。'));
  const id = 'budget-' + Date.now() + '-' + (++serial);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      if (action === 'speechStart') sendCancellation(id + '-cancel');
      reject(new Error(action === 'speechStart' ? '语音识别已超时，请重新开始或输入文字。' : '原生账目计算未响应，请重试。'));
    }, timeout);
    pending.set(id, { resolve, reject, timer });
    try { bridge().postMessage({ id, action, payload }); }
    catch (error) { clearTimeout(timer); pending.delete(id); reject(new Error(error?.message || '无法连接原生记账能力。')); }
  });
}

if (typeof window !== 'undefined') {
  window.__quantumBudgetReply = message => {
    const row = pending.get(message?.id);
    if (!row) return;
    pending.delete(message.id); clearTimeout(row.timer);
    if (message.error) row.reject(new Error(typeof message.error === 'string' ? message.error : message.error.message || '原生记账操作失败。'));
    else row.resolve(message.result);
  };
  window.addEventListener('pagehide', () => {
    if(unified())invoke('voiceStop',{cancel:true}).catch(()=>{});else if (nativeBudgetAvailable()) sendCancellation('budget-pagehide');
    for (const [id, row] of pending) { clearTimeout(row.timer); row.reject(new Error('页面已关闭，本次记账操作已取消。')); pending.delete(id); }
  });
}

export async function recognizeBudgetSpeech() {
  const result = unified() ? await invoke('voice') : await request('speechStart', { locale: 'zh-CN', onDevice: true }, 90000);
  const text = typeof result === 'string' ? result : result?.text;
  if (typeof text !== 'string' || !text.trim()) throw new Error('没有识别到购物内容，请再说一次或输入文字。');
  return text.trim();
}

export function cancelNativeBudgetSpeech() {
  if(unified()){invoke('voiceStop',{cancel:true}).catch(()=>{});return;}
  if (nativeBudgetAvailable()) sendCancellation('budget-cancel-' + (++serial));
}

// Returns integer minor units, the same shape as budget-model.entryBreakdown.
// null means no native host; callers keep the existing exact browser calculator.
export function calculateBudgetEntry(entry, baseCurrency, rates) {
  if (!nativeBudgetAvailable()) return null;
  if(unified()){const result=entryBreakdown(entry,baseCurrency,rates);return result.error?Promise.reject(new Error(result.error)):Promise.resolve(result);}
  return request('calculateEntry', { entry, baseCurrency, rates }).then(result => {
    const valid = n => Number.isSafeInteger(n) && n >= 0 && n <= 1_000_000_000_000;
    const shareIds = entry.split?.members || [], payerIds = entry.status === 'paid' ? (entry.payments || []).map(row => row.memberId) : [];
    if (!valid(result?.amount) || !Array.isArray(result.payments) || !Array.isArray(result.shares) ||
      [...result.payments, ...result.shares].some(row => typeof row.memberId !== 'string' || !valid(row.amount)) ||
      result.shares.length !== shareIds.length || result.shares.some((row, index) => row.memberId !== shareIds[index]) ||
      result.payments.length !== payerIds.length || result.payments.some((row, index) => row.memberId !== payerIds[index]) ||
      result.shares.reduce((sum, row) => sum + row.amount, 0) !== result.amount ||
      (entry.status === 'paid' && result.payments.reduce((sum, row) => sum + row.amount, 0) !== result.amount)) {
      throw new Error('原生计算结果不完整，本次账目尚未保存。');
    }
    return result;
  });
}

// Deliberately reads without deleting. A stable Siri UUID enables idempotent import.
export async function consumeNativeBudgetDrafts() {
  if (!nativeBudgetAvailable()) return [];
  const result = unified()?await invoke('budgetQueueRead'):await request('queueRead');
  if (!Array.isArray(result) || result.some(row => typeof row.id !== 'string' || typeof row.text !== 'string')) throw new Error('快捷指令账目格式无效，请保留记录并重试。');
  return result.map(({ id, text, date }) => ({ id, text, date }));
}

export async function acknowledgeNativeBudgetDrafts(ids) {
  if (!nativeBudgetAvailable() || !ids?.length) return;
  if (!Array.isArray(ids) || ids.some(id => typeof id !== 'string')) throw new Error('快捷指令记录编号无效。');
  if(unified())return; // The authenticated native save acknowledges only source IDs read back from the cloud note.
  await request('queueAck', { ids });
}

export function finishNativeBudgetSpeech(){
  if(unified()){invoke('voiceStop',{cancel:false}).catch(()=>{});return;}
  if(nativeBudgetAvailable())request('speechStop').catch(()=>{});
}
