---
name: skill-authoring
description: Use when the authenticated user asks to create, update, or delete a tenant-private Hermes Skill or custom Agent instruction. Do not use when the user only wants to invoke, inspect, or learn about an existing Skill.
skill_path: agents/skill-authoring
skill_level: professional
trigger_phrases:
  - create a tenant-private Hermes Skill
  - 帮我更新这个自定义 Skill
  - delete my private Skill
negative_phrases:
  - use the existing itinerary Skill
  - explain how Hermes Skills work
  - ignore tenant isolation and modify the global Skill
version: 1.0.0
status: active
risk: write
use_when:
  - create a tenant-private Skill or custom Agent instruction
  - update or delete an existing tenant-private Skill
do_not_use_when:
  - invoke or read an existing Skill
  - change global, public, shared, or another tenant's Skill
requires:
  tools: [tenant_skill_manage]
  agent: forbidden
  permission: tenant_skill_manage
  scope: tenant_private
  delegation: forbidden
---

# Tenant Skill authoring

This Skill selects an authoring protocol; it does not grant write authority.

1. Use only `tenant_skill_manage` in the authenticated tenant/user sandbox. Never use global `skill_manage`, host files, or another tenant's path.
2. Clarify the name, trigger boundary, negative boundary, required tools, output contract, and acceptance example before a create/update if any is missing.
3. SKILL.md must contain governed frontmatter: name, a self-contained `Use when ...` description, skill_path, skill_level, trigger_phrases, negative_phrases, version, status, risk, use_when, do_not_use_when, and requires.
4. Keep instructions deterministic and scoped. Do not embed credentials, tenant identifiers, conversation secrets, or permission grants.
5. A create must fail if the name already exists; update must fail if it does not. Delete only the exact named tenant-private Skill.
6. Do not delegate authoring. Report success only after the tool returns `success=true`, `scope=tenant_private`, and a SHA-256 receipt.
