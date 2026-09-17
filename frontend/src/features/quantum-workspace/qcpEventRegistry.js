const routes = new Map([
  ["schedule.snapshot", { minimumVersion: 1, fallback: "answer", render: (payload) => `项目排期已回读 · revision ${payload?.schedule?.process_revision ?? "-"}` }],
  ["schedule.change_proposed", { minimumVersion: 1, fallback: "answer", render: (payload) => `排期变更提案 · ${payload?.proposal?.id || "待回读"}` }],
]);

export function consumeQCPEvent(event) {
  const route = routes.get(event?.type);
  if (!route) return null;
  if (!Number.isInteger(event.version) || event.version < route.minimumVersion) {
    return { path: route.fallback, text: "当前客户端版本不支持该排期事件；已保留服务端状态。", payload: event.payload };
  }
  return { path: "answer", text: route.render(event.payload), payload: event.payload };
}
