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
    connectPhase: "idle", busy, count: 0, connectRun: run,
    Date: { now: () => now },
    setConnectPhase: value => phases.push(value),
    sendCode: async () => { now += elapsed; if (cancel) run.current += 1; return success; },
    setTimeout: (callback, delay) => { waits.push(delay); now += delay; callback(); },
    document: { getElementById: () => ({ focus: () => { focused = true; } }) },
  });
  await vm.runInContext(handler + "connectQuantum()", context);
  return { phases, waits, focused };
}
test("Quantum login shows success only after the request and the minimum loading duration", async () => {
  assert.deepEqual(await runConnect(), { phases: ["loading", "success", "restoring", "idle"], waits: [1200, 1000, 300], focused: true });
  assert.deepEqual((await runConnect({ elapsed: 2000 })).waits, [0, 1000, 300]);
});
test("Quantum login never shows a success check for errors or after unmount", async () => {
  const failed = await runConnect({ success: false });
  assert.deepEqual(failed.phases, ["loading", "error", "restoring", "idle"]);
  assert.equal(failed.focused, false);
  assert.deepEqual((await runConnect({ cancel: true })).phases, ["loading"]);
  assert.deepEqual((await runConnect({ busy: true })).phases, []);
});
