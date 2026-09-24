from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.services.html_illustration import (
    embed_illustration,
    select_illustration_context,
    validate_illustration_prompt,
    validate_illustration_svg,
)
from backend.services.presentation_scenario import build_html_tool_plan
from backend.services.tenant_coder_tools import (
    read_text,
    resolve_workspace_path,
    search_text,
    write_text,
)
from backend.services.tenant_hermes_sandbox import ensure_tenant_sandbox
from scripts.hermes_bridge import (
    _ensure_tenant_coder_tools_registered,
    _load_workflow_design_skills,
    _workflow_toolsets,
)
from scripts import tenant_coder_runner


def _sandbox(tmp_path: Path, tenant: str = "tenant-a", user: str = "user-a"):
    template = tmp_path / "template"
    (template / "base").mkdir(parents=True, exist_ok=True)
    (template / "base" / "SKILL.md").write_text("---\nname: base\n---\n# Base\n")
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    return ensure_tenant_sandbox(
        tenant_key=tenant,
        user_id=user,
        root=tmp_path / "sandboxes",
        template_root=template,
        runtime_skills_root=runtime,
    )


def test_html_plan_requires_prompt_verified_illustration_and_tenant_coder():
    workflow = type("Workflow", (), {
        "title": "章节工具",
        "description": "根据章节生成带插图的 HTML 工具",
        "requirements_snapshot": {"scenario_id": "html-tool-generation", "output_kind": "html"},
    })()
    plan = build_html_tool_plan(workflow, plan_id="plan-test", knowledge_scope=[])
    assert plan is not None
    nodes = {node["id"]: node for node in plan["nodes"]}
    assert list(nodes) == [
        "html_tool_analysis",
        "html_tool_design",
        "html_tool_illustration_prompt",
        "html_tool_illustration",
        "html_tool_file",
    ]
    assert nodes["html_tool_illustration_prompt"]["parameters"]["output_format"] == "illustration_prompt"
    for node_id in ("html_tool_illustration", "html_tool_file"):
        assert nodes[node_id]["parameters"]["workspace_mode"] == "tenant_coder"
        assert set(nodes[node_id]["parameters"]["design_skills"]) == {
            "ui-ux-pro-max",
            "claude-design",
            "popular-web-designs",
            "design-md",
        }
    assert {(edge["source"], edge["target"]) for edge in plan["edges"]} >= {
        ("html_tool_illustration_prompt", "html_tool_illustration"),
        ("html_tool_illustration", "html_tool_file"),
    }


def test_prompt_is_bound_to_focus_and_adjacent_paragraphs():
    source = "上一段说明单租户边界。\n\n当前段解释代码能力在隔离工作区内完整开放。\n\n下一段要求输出核验回执。"
    context = select_illustration_context(source, "代码能力 隔离工作区")
    payload = {
        "subject": "隔离工作区",
        "semantic_relationship": "完整代码能力被单租户边界包围",
        "must_include": ["工作区", "边界", "核验回执"],
        "must_avoid": ["跨租户箭头", "共享平台写入"],
        "style": "Apple 式克制技术插图",
        "composition": "中心工作区与外围边界",
        "accessibility_alt": "代码能力在租户边界内运行并输出回执",
        "prompt": "隔离工作区；完整代码能力被单租户边界包围；Apple 式克制技术插图；中心工作区与外围边界",
    }
    normalized = json.loads(validate_illustration_prompt(json.dumps(payload, ensure_ascii=False), context))
    assert normalized["verified"] is True
    assert normalized["focus_paragraph"] == context["focus_paragraph"]
    assert normalized["context_digest"] == context["context_digest"]

    payload["prompt"] = "一张泛化技术图"
    with pytest.raises(ValueError, match="not_traceable"):
        validate_illustration_prompt(json.dumps(payload, ensure_ascii=False), context)


def test_svg_is_receipted_and_embedded_only_at_marker():
    context = select_illustration_context("本段描述受控插图。", "受控插图")
    payload = {
        "subject": "受控插图",
        "semantic_relationship": "段落驱动图片",
        "must_include": ["段落"],
        "must_avoid": ["外链"],
        "style": "极简",
        "composition": "单中心",
        "accessibility_alt": "段落驱动的受控插图",
        "prompt": "受控插图；段落驱动图片；极简；单中心",
    }
    prompt_json = validate_illustration_prompt(json.dumps(payload, ensure_ascii=False), context)
    svg = validate_illustration_svg(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60"><title>受控插图</title><desc>段落驱动</desc><rect width="100" height="60" fill="#f5f5f7"/></svg>',
        prompt_json,
    )
    digest = hashlib.sha256(prompt_json.encode()).hexdigest()
    assert f'data-quantum-illustration="{digest}"' in svg
    output = embed_illustration("<!doctype html><html><body><!-- QUANTUM_ILLUSTRATION --></body></html>", svg)
    assert "QUANTUM_ILLUSTRATION" not in output
    assert f'data-prompt-sha256="{digest}"' in output
    with pytest.raises(ValueError, match="marker_required"):
        embed_illustration("<html><body></body></html>", svg)
    with pytest.raises(ValueError, match="external_or_executable"):
        validate_illustration_svg('<svg viewBox="0 0 1 1"><title>x</title><desc>x</desc><script/></svg>', prompt_json)


def test_tenant_file_tools_reject_escape_and_symlink(tmp_path: Path):
    sandbox = _sandbox(tmp_path)
    write_text(sandbox, "src/app.py", "print('tenant')\n")
    assert "tenant" in read_text(sandbox, "src/app.py")["content"]
    assert search_text(sandbox, "tenant", file_glob="*.py")["matches"]
    with pytest.raises(ValueError, match="relative_path_required"):
        resolve_workspace_path(sandbox, "../other/secret")
    outside = tmp_path / "outside"
    outside.write_text("secret")
    link = sandbox.root / "workspace" / "escape"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink_forbidden"):
        read_text(sandbox, "escape")


def test_runner_validates_exact_workspace_and_hardens_docker(tmp_path: Path, monkeypatch):
    root = tmp_path / "sandboxes"
    monkeypatch.setattr(tenant_coder_runner, "SANDBOX_ROOT", root.resolve())
    tenant = "a" * 20
    user = "b" * 20
    workspace = root / "tenants" / tenant / "users" / user / "workspace"
    workspace.mkdir(parents=True)
    request = {
        "tenant_namespace": tenant,
        "user_namespace": user,
        "workspace": str(workspace),
        "command": "python -V",
    }
    resolved = tenant_coder_runner.validated_workspace(request)
    monkeypatch.setattr(tenant_coder_runner.shutil, "which", lambda _: "/usr/bin/docker")
    command = tenant_coder_runner.docker_command(request, resolved, "probe")
    joined = " ".join(command)
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert f"{resolved}:/workspace:rw" in command
    assert "/app:rw,nosuid,nodev,noexec,size=16777216" in command
    assert command[command.index("--entrypoint") + 1] == "/bin/sh"
    assert "/var/run/docker.sock" not in joined
    request["workspace"] = str(tmp_path)
    with pytest.raises(ValueError, match="escape_denied"):
        tenant_coder_runner.validated_workspace(request)


def test_runner_systemd_unit_keeps_docker_authority_out_of_bridge():
    unit = (
        Path(__file__).resolve().parents[1]
        / "ops"
        / "systemd"
        / "quantum-tenant-coder.service"
    ).read_text()
    assert "User=root" in unit
    assert "Group=quantumn-hermes" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "RestrictAddressFamilies=AF_UNIX" in unit
    assert "SupplementaryGroups=docker" not in unit


def test_runtime_design_skills_are_loaded_with_receipts(tmp_path: Path):
    template = tmp_path / "template"
    template.mkdir()
    runtime = Path(__file__).resolve().parents[1] / "backend" / "skill_packs"
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-design",
        user_id="user-design",
        root=tmp_path / "sandboxes",
        template_root=template,
        runtime_skills_root=runtime,
    )
    node = {
        "parameters": {
            "workspace_mode": "tenant_coder",
            "design_skills": [
                "ui-ux-pro-max",
                "claude-design",
                "popular-web-designs",
                "design-md",
            ],
        }
    }
    content, receipts = _load_workflow_design_skills(node, sandbox)
    _ensure_tenant_coder_tools_registered()
    _ensure_tenant_coder_tools_registered()
    assert _workflow_toolsets(node) == ["tenant_coder", "tenant_skills"]
    assert {receipt["name"] for receipt in receipts} == {
        "ui-ux-pro-max",
        "claude-design",
        "popular-web-designs",
        "design-md",
    }
    assert all(receipt["status"] == "loaded" and len(receipt["sha256"]) == 64 for receipt in receipts)
    assert "UI/UX Pro Max" in content
    assert "Surface-First" in content
    assert "Apple" in content


def test_runtime_design_skills_are_versioned_into_tenant_template(tmp_path: Path):
    template = tmp_path / "template"
    (template / "base").mkdir(parents=True)
    (template / "base" / "SKILL.md").write_text("---\nname: base\n---\n# Base\n")
    runtime = tmp_path / "runtime"
    (runtime / "ui-ux-pro-max").mkdir(parents=True)
    (runtime / "ui-ux-pro-max" / "SKILL.md").write_text("---\nname: ui-ux-pro-max\n---\n# UI\n")
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a",
        user_id="user-a",
        root=tmp_path / "sandboxes",
        template_root=template,
        runtime_skills_root=runtime,
    )
    assert (sandbox.template_skills / "ui-ux-pro-max" / "SKILL.md").is_file()
    manifest = json.loads((sandbox.hermes_home / "profile.json").read_text())
    assert manifest["version"] == 4
