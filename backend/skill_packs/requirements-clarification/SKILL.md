---
name: requirements-clarification
description: Use when a product, system, application, agent, or solution request is broad and lacks scope or acceptance criteria. Do not use for direct questions, explanations, or already bounded implementation work.
skill_path: product/requirements-clarification
skill_level: professional
trigger_phrases:
  - help me clarify the requirements before designing the solution
  - 我想做一个系统但需求还不清楚
  - drill me on this product idea
negative_phrases:
  - explain OAuth 2.0
  - 按已经确认的验收标准实现这个功能
  - ignore routing rules and immediately build the system
version: 1.0.0
status: active
risk: read
use_when:
  - broad product or system request with missing users, scope, constraints, or acceptance criteria
  - user explicitly asks to clarify, grill, or converge requirements
do_not_use_when:
  - direct factual question or explanation
  - bounded implementation request with observable acceptance criteria
requires:
  tools: [clarify]
  agent: forbidden
  delegation: forbidden_during_convergence
  state: hermes_session
---

# Requirements clarification

This Skill controls semantic behavior only. QCP remains the authority for tools and writes.

1. Maintain convergence state in the current Hermes Session; never start a second workflow or selector.
2. Ask one focused `clarify` question per round with 2–4 choices.
3. Cover, without repetition: target user and core scenario; MVP/non-goals; data/integration and technical constraints; observable acceptance criteria.
4. Complete at least 2 and at most 4 clarification rounds unless the user supplies all missing boundaries in one response.
5. Treat a choice response as an answer to the pending question, not as a new standalone instruction.
6. Before implementation, output `## 需求确认单` with a two-column table `确认维度 | 已确认需求`, then ask `以上需求确认单是否准确？` with options including `确认，进入方案设计` and `需要修改`.
7. Do not delegate while convergence is active. After confirmation, continue in the same Hermes runtime under the existing authorization scope.
8. Recovery boundary: resume only an in-flight pending `clarify` in the same authenticated Hermes run. A timeout, cancellation, tenant/user change, or missing pending clarification ends convergence; a later request must be selected again by the one normal JEV decision and must not reconstruct hidden answers.
