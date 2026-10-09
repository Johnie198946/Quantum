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
