import assert from "node:assert/strict";
import test from "node:test";

import { consumeQCPEvent } from "../src/features/quantum-workspace/qcpEventRegistry.js";

test("QWS consumes schedule events through the shared registry", () => {
  const snapshot = consumeQCPEvent({
    type: "schedule.snapshot",
    version: 1,
    payload: { schedule: { process_revision: 8 } },
  });
  assert.equal(snapshot.path, "answer");
  assert.match(snapshot.text, /revision 8/);

  const proposal = consumeQCPEvent({
    type: "schedule.change_proposed",
    version: 1,
    payload: { proposal: { id: "proposal-1" } },
  });
  assert.match(proposal.text, /proposal-1/);
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
