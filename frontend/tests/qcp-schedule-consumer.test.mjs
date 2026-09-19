import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { consumeQCPEvent } from "../src/features/quantum-workspace/qcpEventRegistry.js";

const capabilityMatrix = JSON.parse(readFileSync(
  new URL("../../ops/acceptance/ios-capability-matrix.json", import.meta.url), "utf8",
));

test("QWS consumes schedule events through the shared registry", () => {
  const snapshot = consumeQCPEvent({
    type: "schedule.snapshot",
    version: 1,
    renderer: "answer", renderer_version: 1,
    payload: { schedule: { process_revision: 8 } },
  });
  assert.equal(snapshot.path, "answer");
  assert.match(snapshot.text, /revision 8/);

  const proposal = consumeQCPEvent({
    type: "schedule.change_proposed",
    version: 1,
    renderer: "answer", renderer_version: 1,
    payload: { proposal: { id: "proposal-1" } },
  });
  assert.match(proposal.text, /proposal-1/);
});

test("QWS consumes project and task mutation events through the shared registry", () => {
  const project = consumeQCPEvent({
    type: "project.change_proposed",
    version: 1,
    renderer: "answer", renderer_version: 1,
    payload: { proposal: { id: "project-proposal-1" } },
  });
  assert.equal(project.path, "answer");
  assert.match(project.text, /project-proposal-1/);

  const task = consumeQCPEvent({
    type: "task.change_proposed",
    version: 1,
    renderer: "answer", renderer_version: 1,
    payload: { proposal: { id: "task-proposal-1" } },
  });
  assert.equal(task.path, "answer");
  assert.match(task.text, /task-proposal-1/);

  const fallback = consumeQCPEvent({
    type: "project.change_proposed",
    version: 0,
    payload: { proposal: { id: "preserved" } },
  });
  assert.equal(fallback.path, "answer");
  assert.equal(fallback.payload.proposal.id, "preserved");
  assert.match(fallback.text, /保留服务端状态/);
});

test("QWS accepts only contracted capability confirmation envelopes", () => {
  const proposal = consumeQCPEvent({
    type: "capability.proposed",
    version: 1,
    renderer: "confirmation",
    renderer_version: 1,
    payload: { proposal_id: "proposal-1", confirmation_token: "opaque-token" },
  });
  assert.equal(proposal.path, "confirmation");
  assert.equal(proposal.payload.confirmation_token, "opaque-token");
  assert.equal(consumeQCPEvent({
    type: "capability.proposed", version: 1, payload: { proposal_id: "proposal-1" },
  }), null);
});

test("QWS schedule registry preserves unknown-version state with safe fallback", () => {
  const event = consumeQCPEvent({
    type: "schedule.snapshot",
    version: 0,
    payload: { schedule: { process_revision: 9 } },
  });
  assert.equal(event.path, "answer");
  assert.equal(event.payload.schedule.process_revision, 9);
  assert.match(event.text, /保留服务端状态/);
  assert.equal(consumeQCPEvent({ type: "unknown.event", version: 99 }), null);
});

test("QWS preserves every scoped generic capability event", () => {
  for (const [type, path] of [
    ["agent.changed", "answer"], ["artifact.generated", "artifact_card"], ["bookshelf.results", "bookshelf"],
    ["client.action.requested", "client_action"], ["document.created", "workflow"],
    ["hermes.session.listed", "hermes_session_list"], ["knowledge.action", "knowledge_action"],
    ["memory.snapshot", "answer"], ["notification.snapshot", "answer"],
    ["presentation.created", "presentation_review"], ["profile.snapshot", "answer"],
    ["project.snapshot", "answer"], ["skill.snapshot", "answer"],
    ["task.execution_queued", "task_execution_card"], ["workflow.cancelled", "workflow"],
    ["workflow.summary", "workflow"],
  ]) {
    const event = consumeQCPEvent({
      type, version: 1, renderer: path, renderer_version: 1,
      payload: { retained: true },
    });
    assert.equal(event.path, path);
    assert.equal(event.payload.retained, true);
    assert.match(event.text, new RegExp(type.replaceAll(".", "\\.")));
  }
});

test("QWS resolves shared events by contract renderer metadata", () => {
  for (const [renderer, path] of [
    ["artifact_card", "artifact_card"],
    ["data_analysis_card", "data_analysis_card"],
    ["image_card", "image_card"],
    ["task_execution_card", "task_execution_card"],
  ]) {
    const event = consumeQCPEvent({
      type: renderer === "task_execution_card" ? "task.execution_queued" : "artifact.generated",
      version: 1,
      renderer,
      renderer_version: 1,
      payload: { retained: true },
    });
    assert.equal(event.path, path);
    assert.equal(event.renderer, renderer);
    assert.equal(event.payload.retained, true);
  }
  assert.equal(consumeQCPEvent({
    type: "artifact.generated", version: 1,
    renderer: "wrong_renderer", renderer_version: 1, payload: {},
  }), null);
  assert.equal(consumeQCPEvent({
    type: "artifact.generated", version: 1,
    renderer: "task_execution_card", renderer_version: 1, payload: {},
  }), null);
  assert.equal(consumeQCPEvent({
    type: "task.execution_queued", version: 1,
    renderer: "image_card", renderer_version: 1, payload: {},
  }), null);
  const futureClientAction = consumeQCPEvent({
    type: "client.action.requested", version: 2,
    renderer: "client_action", renderer_version: 1, payload: { action_id: "a-1" },
  });
  assert.equal(futureClientAction.path, "answer");
  assert.match(futureClientAction.text, /不支持/);
});

test("every scoped matrix event resolves to its contracted QWS renderer", () => {
  for (const row of capabilityMatrix.capabilities) {
    const [renderer, rendererVersionText] = row.renderer.split("@");
    const result = consumeQCPEvent({
      type: row.event,
      version: 1,
      renderer,
      renderer_version: Number(rendererVersionText),
      payload: { capability: row.capability },
    });
    assert.ok(result, row.capability);
    assert.equal(result.path, renderer, row.capability);
  }
});
