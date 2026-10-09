export function tableRows(content) {
  return content.replace(/^\n+|\n+$/g, "").split(/\r?\n/).filter((line) => !/^\s*\|?\s*:?-+/.test(line)).map((line) =>
    line.includes("\t") ? line.split("\t") : line.replace(/^\s*\||\|\s*$/g, "").split("|").map((cell) => cell.trim()));
}
export function plainContent(item) {
  return [item.text, ...item.blocks.map((block) => block.kind === "chart"
    ? [block.content, ...block.labels.map((label, i) => `${label}\t${block.values[i]}`)].join("\n") : block.content)].filter(Boolean).join("\n\n");
}
