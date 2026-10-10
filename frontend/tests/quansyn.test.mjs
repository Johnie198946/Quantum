import test from "node:test";
import assert from "node:assert/strict";
import { tableRows, plainContent } from "../src/features/quansyn/content.js";
test("QuanSyn preserves TSV cells and Markdown table headers", () => {
  assert.deepEqual(tableRows("名称\t值\nA\t2"), [["名称", "值"], ["A", "2"]]);
  assert.deepEqual(tableRows("| 名称 | 值 |\n| :--- | ---: |\n| A | 2 |"), [["名称", "值"], ["A", "2"]]);
  assert.deepEqual(tableRows("<script>\t"), [["<script>", ""]]);
});
test("QuanSyn copies actual chart numbers alongside text and code", () => {
  assert.equal(plainContent({text:"结果", blocks:[{kind:"chart",content:"实测",labels:["A"],values:[2]},{kind:"code",content:"print(2)"}]}), "结果\n\n实测\nA\t2\n\nprint(2)");
});


// Exercise the shipped handler with a controlled clock; no fixtures enter the UI.
import { readFileSync } from "node:fs";
import vm from "node:vm";
const design = readFileSync(new URL("../src/features/quansyn/QuanSynDesign.jsx", import.meta.url), "utf8");
const handler = design.slice(design.indexOf("  async function connectQuantum()"), design.indexOf("  const [account", design.indexOf("  async function connectQuantum()")));
async function runConnect({ success = true, elapsed = 0, cancel = false, busy = false } = {}) {
  let now = 0;
  const phases = [], waits = [];
  let focused = false;
  const run = { current: 0 };
  const context = vm.createContext({
    connectPhase: "idle", busy, count: 0, account: "19900000000", connectRun: run,
    Date: { now: () => now },
    setConnectPhase: value => phases.push(value),
    platformApi: { startQuantumLogin: async () => { now += elapsed; if (cancel) run.current += 1; if (!success) throw new Error("failed"); return {state: "test-browser-secret"}; } },
    setWebLogin: () => {},
    action: async fn => { try { await fn(); return true; } catch { return false; } },
    setTimeout: (callback, delay) => { waits.push(delay); now += delay; callback(); },
    document: { getElementById: () => ({ focus: () => { focused = true; } }) },
  });
  await vm.runInContext(handler + "connectQuantum()", context);
  return { phases, waits, focused };
}
test("Quantum login shows success only after the request and the minimum loading duration", async () => {
  assert.deepEqual(await runConnect(), { phases: ["loading", "success", "restoring", "idle"], waits: [1200, 1000, 300], focused: false });
  assert.deepEqual((await runConnect({ elapsed: 2000 })).waits, [0, 1000, 300]);
});
test("Quantum login never shows a success check for errors or after unmount", async () => {
  const failed = await runConnect({ success: false });
  assert.deepEqual(failed.phases, ["loading", "error", "restoring", "idle"]);
  assert.equal(failed.focused, false);
  assert.deepEqual((await runConnect({ cancel: true })).phases, ["loading"]);
  assert.deepEqual((await runConnect({ busy: true })).phases, []);
});


const pasteHandler = design.slice(design.indexOf("  function pasteImages(event)"), design.indexOf("  const docs = items.flatMap", design.indexOf("  function pasteImages(event)")));
test("Clipboard images enter the real attachment path; ordinary text keeps native paste", () => {
  const image = { name: "image.png", type: "image/png" };
  const uploads = [], drafts = [];
  let prevented = false;
  const context = vm.createContext({busy:false, agreementContent:null, draft:"前后", setDraft:value=>drafts.push(value), attachFile:files=>uploads.push(files)});
  vm.runInContext(pasteHandler, context);
  const event = {preventDefault:()=>{prevented=true;},currentTarget:{selectionStart:1,selectionEnd:1},clipboardData:{items:[{kind:"file",type:"image/png",getAsFile:()=>image}],getData:()=>"说明"}};
  context.pasteImages(event);
  assert.equal(prevented,true);
  assert.equal(uploads[0][0],image);
  assert.deepEqual(drafts,["前说明后"]);
  prevented=false;
  event.clipboardData.items=[{kind:"string",type:"text/plain"}];
  context.pasteImages(event);
  assert.equal(prevented,false);
  assert.equal(uploads.length,1);
  context.busy=true;
  event.clipboardData.items=[{kind:"file",type:"image/png",getAsFile:()=>image}];
  context.pasteImages(event);
  assert.equal(uploads.length,1);
});

const pollingEffect = design.slice(design.indexOf('  useEffect(() => {\n    if (!webLogin)'), design.indexOf('  useEffect(() => () => { connectRun.current', design.indexOf('  useEffect(() => {\n    if (!webLogin)')));
async function runLoginPolling(statuses) {
  const sessions = [], errors = [], scheduled = [];
  let cleanup, cleared = false;
  const context = vm.createContext({
    webLogin: {state: 'browser-secret'}, AbortController,
    useEffect: callback => { cleanup = callback(); },
    platformApi: { quantumLoginStatus: async state => {
      assert.equal(state, 'browser-secret'); return statuses.shift();
    } },
    loginWithOAuthTicket: async value => { assert.equal(value.appApproval, true); sessions.push(value.ticket); },
    report: value => errors.push(value), setWebLogin: () => {cleared = true;},
    setTimeout: callback => {scheduled.push(callback); return scheduled.length;}, clearTimeout: () => {},
  });
  vm.runInContext(pollingEffect, context);
  await new Promise(resolve => setImmediate(resolve));
  while (scheduled.length) {scheduled.shift()(); await new Promise(resolve => setImmediate(resolve));}
  cleanup();
  return {sessions, errors, cleared};
}
test('Quantum web waits for real approval before ticket exchange; cancellation never logs in', async () => {
  assert.deepEqual(await runLoginPolling([{status:'pending'}, {status:'approved', ticket:'one-time-ticket'}]),
    {sessions:['one-time-ticket'], errors:[], cleared:false});
  const cancelled = await runLoginPolling([{status:'cancelled'}]);
  assert.deepEqual(cancelled.sessions, []);
  assert.equal(cancelled.errors.length, 1);
  assert.equal(cancelled.cleared, true);
});
