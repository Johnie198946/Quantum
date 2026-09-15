# Product Capability Manual

QCP version: `1.0.0`
Catalog digest: `db5bccbf93298e61ccfa38c4a468ffec60929d116c36e8723d9fe26d8d3541ae`

| Capability | Domain | Effect | Confirmation | Receipt | Event | Renderer | Status |
|---|---|---|---|---|---|---|---|
| `artifact.consume_structured@1.0.0` | artifact | read | none | required | `artifact.consumed` | `artifact_consumption@1` | implemented |
| `artifact.download@1.0.0` | artifact | read | none | none | `artifact.download_ready` | `artifact@1` | implemented |
| `artifact.open@1.0.0` | artifact | read | none | none | `artifact.content` | `artifact@1` | implemented |
| `document.word.create_from_text@1.0.0` | document | write | required | required | `document.created` | `workflow@1` | implemented |
| `knowledge.navigation@1.0.0` | knowledge | client | none | none | `knowledge.navigation` | `knowledge_action@1` | implemented |
| `knowledge.note.archive@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.create@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.merge@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.read@1.0.0` | knowledge | read | none | none | `knowledge.note` | `answer@1` | implemented |
| `knowledge.note.restore@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `knowledge.note.search@1.0.0` | knowledge | read | none | none | `knowledge.results` | `answer@1` | implemented |
| `knowledge.note.update@1.0.0` | knowledge | write | required | required | `knowledge.action` | `knowledge_action@1` | implemented |
| `paper.academic.create_from_text@1.0.0` | paper | write | required | required | `document.created` | `workflow@1` | implemented |
| `presentation.create_from_document@1.0.0` | presentation | write | required | required | `presentation.created` | `presentation_review@1` | implemented |
| `presentation.create_from_text@1.0.0` | presentation | write | required | required | `presentation.created` | `presentation_review@1` | implemented |
| `report.research.create_from_text@1.0.0` | report | write | required | required | `document.created` | `workflow@1` | implemented |
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

## iOS document-class E2E coverage

| iOS user function | Capability | Event | Renderer | Handler | Consumer | Policy | Automated evidence | Production receipt | Status |
|---|---|---|---|---|---|---|---|---|---|
| Generate, revise, and download a multi-page Word document | `document.word.create_from_text` | `document.created@1` | `workflow@1` | `backend/capability_handlers.py:_word_create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner + artifact-owner | `tests/e2e/test_word_workflow.py`, `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | unverified | partial |
| Generate and revise a research report with traceable evidence | `report.research.create_from_text` | `document.created@1` | `workflow@1` | `backend/capability_handlers.py:_research_report_create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner + artifact-owner | `tests/e2e/test_research_report_workflow.py`, `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | unverified | partial |
| Generate an academic paper with verified citation correspondence | `paper.academic.create_from_text` | `document.created@1` | `workflow@1` | `backend/capability_handlers.py:_academic_paper_create_from_text` | `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift:dispatchCapabilityEvent` | workflow-owner + artifact-owner | `tests/e2e/test_academic_paper_workflow.py`, `tests/test_product_capabilities.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift` | unverified | partial |

PCM compiles every implemented, client-supported capability into a native Hermes tool at session assembly. Normal business execution does not depend on capability search or describe. QCP validates every invocation against the allowlisted contract; domain handlers remain the authorization truth.
