# Product Capability Manual

QCP version: `1.0.0`
Catalog digest: `83abb82e5bd7eb2b202839f91f4b1c2fd876349d2d5a602bd9a90a08b9cb33d6`

| Capability | Domain | Effect | Confirmation | Receipt | Event | Renderer | Status |
|---|---|---|---|---|---|---|---|
| `artifact.consume_structured@1.0.0` | artifact | read | none | required | `artifact.consumed` | `artifact_consumption@1` | implemented |
| `artifact.download@1.0.0` | artifact | read | none | none | `artifact.download_ready` | `artifact@1` | implemented |
| `artifact.open@1.0.0` | artifact | read | none | none | `artifact.content` | `artifact@1` | implemented |
| `knowledge.navigation@1.0.0` | knowledge | client | none | none | `knowledge.navigation` | `knowledge_action@1` | implemented |
| `knowledge.note.archive@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.create@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.merge@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.read@1.0.0` | knowledge | read | none | none | `knowledge.note` | `answer@1` | implemented |
| `knowledge.note.restore@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.search@1.0.0` | knowledge | read | none | none | `knowledge.results` | `answer@1` | implemented |
| `knowledge.note.update@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `presentation.create_from_document@1.0.0` | presentation | write | required | required | `presentation.created` | `presentation_review@1` | implemented |
| `workflow.create@1.0.0` | workflow | write | required | required | `workflow.created` | `workflow@1` | implemented |
| `workflow.open@1.0.0` | workflow | read | none | none | `workflow.summary` | `workflow@1` | implemented |
| `workflow.start@1.0.0` | workflow | execute | required | required | `workflow.started` | `workflow@1` | implemented |
| `workflow.status@1.0.0` | workflow | read | none | none | `workflow.summary` | `workflow@1` | implemented |

## Consumption contracts

| Contract | Kind | Receipt | Status |
|---|---|---|---|
| `artifact.structured_consumption` | artifact | `durable_structured_consumption_receipt` | implemented |
| `knowledge.natural_qa` | knowledge | `durable_answer_and_source_events` | implemented |
| `workflow.knowledge_need_injection` | workflow | `workflow_event_receipt` | implemented |

PCM compiles every implemented, client-supported capability into a native Hermes tool at session assembly. Normal business execution does not depend on capability search or describe. QCP validates every invocation against the allowlisted contract; domain handlers remain the authorization truth.
