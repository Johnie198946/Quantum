const genericEvents = [
  "agent.changed", "agent.snapshot", "artifact.generated",
  "bookshelf.opened", "bookshelf.results", "bookshelf.subscription_changed",
  "capability.proposed",
  "client.action.requested", "document.created",
  "hermes.session.deleted", "hermes.session.listed", "hermes.session.opened", "hermes.session.resumed",
  "knowledge.action", "knowledge.note", "knowledge.results",
  "memory.changed", "memory.snapshot",
  "notification.changed", "notification.preferences_changed", "notification.snapshot",
  "presentation.created", "profile.changed", "profile.snapshot", "project.created", "project.snapshot",
  "skill.changed", "skill.snapshot", "task.execution_queued", "task.snapshot",
  "workflow.approved", "workflow.cancelled", "workflow.created", "workflow.revised", "workflow.started", "workflow.summary",
];

const semanticRendererByEvent = new Map([
  ["capability.proposed", "confirmation"],
  ["learning.exercise", "learning_exercise"],
  ["bookshelf.opened", "bookshelf"],
  ["bookshelf.results", "bookshelf"],
  ["bookshelf.subscription_changed", "bookshelf"],
  ["client.action.requested", "client_action"],
  ["document.created", "workflow"],
  ["hermes.session.deleted", "hermes_session_detail"],
  ["hermes.session.listed", "hermes_session_list"],
  ["hermes.session.opened", "hermes_session_detail"],
  ["hermes.session.resumed", "hermes_session_detail"],
  ["knowledge.action", "knowledge_action"],
  ["presentation.created", "presentation_review"],
  ["task.execution_queued", "task_execution_card"],
  ["workflow.approved", "workflow"],
  ["workflow.cancelled", "workflow"],
  ["workflow.created", "workflow"],
  ["workflow.revised", "workflow"],
  ["workflow.started", "workflow"],
  ["workflow.summary", "workflow"],
]);

const rendererRoutes = new Map([
  ["confirmation", { path: "confirmation", minimumVersion: 1, fallback: "answer" }],
  ["answer", { path: "answer", minimumVersion: 1, fallback: "answer" }],
  ["knowledge_action", { path: "knowledge_action", minimumVersion: 1, fallback: "answer" }],
  ["workflow", { path: "workflow", minimumVersion: 1, fallback: "answer" }],
  ["presentation_review", { path: "presentation_review", minimumVersion: 1, fallback: "artifact" }],
  ["artifact", { path: "artifact", minimumVersion: 1, fallback: "answer" }],
  ["learning_exercise", { path: "learning_exercise", minimumVersion: 1, fallback: "answer" }],
  ["bookshelf", { path: "bookshelf", minimumVersion: 1, fallback: "answer" }],
  ["hermes_session_list", { path: "hermes_session_list", minimumVersion: 1, fallback: "answer" }],
  ["hermes_session_detail", { path: "hermes_session_detail", minimumVersion: 1, fallback: "answer" }],
  ["client_action", { path: "client_action", minimumVersion: 1, fallback: "answer" }],
  ["artifact_card", { path: "artifact_card", minimumVersion: 1, fallback: "answer" }],
  ["data_analysis_card", { path: "data_analysis_card", minimumVersion: 1, fallback: "answer" }],
  ["image_card", { path: "image_card", minimumVersion: 1, fallback: "answer" }],
  ["task_execution_card", { path: "task_execution_card", minimumVersion: 1, fallback: "answer" }],
]);

const routes = new Map([
  ["learning.resume", { path: "answer", minimumVersion: 1, fallback: "answer", render: (payload) => payload?.resume ? `继续学习 · ${payload.resume.section_title}` : "还没有阅读记录，请先选择一本书。" }],
  ["learning.exercise", { path: "learning_exercise", minimumVersion: 1, fallback: "answer", render: (payload) => [payload?.status === "graded" ? "练习已批改" : "练习已同步", payload?.book_title, payload?.section_title, payload?.hint].filter(Boolean).join(" · ") }],
  ["project.change_proposed", { path: "answer", minimumVersion: 1, fallback: "answer", render: (payload) => `项目变更提案 · ${payload?.proposal?.id || "待回读"}` }],
  ["task.change_proposed", { path: "answer", minimumVersion: 1, fallback: "answer", render: (payload) => `任务变更提案 · ${payload?.proposal?.id || "待回读"}` }],
  ["schedule.snapshot", { path: "answer", minimumVersion: 1, fallback: "answer", render: (payload) => `项目排期已回读 · revision ${payload?.schedule?.process_revision ?? "-"}` }],
  ["schedule.change_proposed", { path: "answer", minimumVersion: 1, fallback: "answer", render: (payload) => `排期变更提案 · ${payload?.proposal?.id || "待回读"}` }],
  ...genericEvents.map((type) => [type, {
    path: semanticRendererByEvent.get(type) || "answer",
    minimumVersion: 1,
    fallback: "answer",
    render: () => `能力事件已回读 · ${type}`,
  }]),
]);

function rendererIsAllowed(type, renderer) {
  if (!renderer) return false;
  if (!rendererRoutes.has(renderer)) return false;
  const artifactRenderers = new Set(["artifact_card", "data_analysis_card", "image_card"]);
  if (type === "artifact.generated") return artifactRenderers.has(renderer);
  return routes.get(type)?.path === renderer;
}

export function consumeQCPEvent(event) {
  const eventRoute = routes.get(event?.type);
  if (!eventRoute) return null;
  if (!Number.isInteger(event?.version) || event.version !== eventRoute.minimumVersion) {
    return { path: eventRoute.fallback, text: "当前客户端版本不支持该能力事件；已保留服务端状态。", payload: event?.payload };
  }
  if (!rendererIsAllowed(event?.type, event?.renderer)) return null;
  const route = event?.renderer ? rendererRoutes.get(event.renderer) : eventRoute;
  if (!route) return null;
  const version = event?.renderer ? event.renderer_version : event.version;
  if (!Number.isInteger(version) || version !== route.minimumVersion) {
    return { path: route.fallback, text: "当前客户端版本不支持该能力事件；已保留服务端状态。", payload: event.payload };
  }
  return {
    path: route.path || "answer",
    renderer: event.renderer || route.path || "answer",
    text: eventRoute.render?.(event.payload) || route.render?.(event.payload) || `能力事件已回读 · ${event.type}`,
    payload: event.payload,
  };
}
