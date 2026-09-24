from types import SimpleNamespace

import pytest

from backend.services.html_tool_renderer import secure_html_tool
from backend.services.presentation_scenario import build_html_tool_plan
from backend.services.workflow_executor import artifact_storage_contract
from scripts.hermes_bridge import _workflow_artifact_contract, _workflow_artifact_instruction


def _html(body: str = "<button id='run'>Run</button>") -> str:
    return f"""<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Tool</title>
<style>button{{min-height:44px}}</style></head><body>{body}</body></html>"""


def test_html_workflow_reuses_reviewed_design_gate_and_scoped_coder():
    workflow = SimpleNamespace(
        title="预算规划器",
        description="生成一个预算规划 HTML 工具",
        requirements_snapshot={"scenario_id": "html-tool-generation", "output_kind": "html"},
    )
    plan = build_html_tool_plan(workflow, plan_id="plan-1", knowledge_scope=[])

    assert plan is not None
    assert [node["id"] for node in plan["nodes"]] == [
        "html_tool_analysis",
        "html_tool_design",
        "html_tool_illustration_prompt",
        "html_tool_illustration",
        "html_tool_file",
    ]
    design = plan["nodes"][1]
    illustration = plan["nodes"][3]
    final = plan["nodes"][4]
    assert design["parameters"]["approval_gate"] == "design"
    assert design["parameters"]["agent_id"] == "coder"
    assert design["parameters"]["design_skills"] == [
        "ui-ux-pro-max", "claude-design", "popular-web-designs", "design-md"
    ]
    assert illustration["parameters"]["workspace_mode"] == "tenant_coder"
    assert final["parameters"]["workspace_mode"] == "tenant_coder"
    assert final["parameters"]["output_format"] == "html"
    assert final["parameters"]["allow_network"] is False


def test_html_contract_is_preserved_from_bridge_to_storage():
    contract = _workflow_artifact_contract({"parameters": {"output_format": "html"}})
    assert contract == {
        "render_type": "html",
        "extension": "html",
        "mime_type": "text/html; charset=utf-8",
    }
    assert "44px" in _workflow_artifact_instruction(contract)

    node = SimpleNamespace(node_id="html_tool_file", agent_id="coder", model_used="m", provider_used="p", attempt=1)
    extension, metadata = artifact_storage_contract(
        {"render_type": "html", "extension": "html"}, event_id="evt-1", node=node
    )
    assert extension == "html"
    assert metadata["render_type"] == "html"
    assert metadata["mime_type"] == "text/html; charset=utf-8"


def test_secure_html_tool_injects_csp_and_keeps_inline_interaction():
    hardened = secure_html_tool(_html("<script>document.body.dataset.ready='1'</script>"))
    assert "Content-Security-Policy" in hardened
    assert "connect-src 'none'" in hardened
    assert "document.body.dataset.ready" in hardened


@pytest.mark.parametrize(
    "payload",
    [
        _html('<script>fetch("https://example.com")</script>'),
        _html('<img src="https://example.com/a.png">'),
        _html('<iframe srcdoc="<p>nested</p>"></iframe>'),
        '<!doctype html><html><meta name="viewport" content="width=device-width"><title>No head</title><body></body></html>',
        "<html><head><title>Missing viewport</title></head><body></body></html>",
    ],
)
def test_secure_html_tool_fails_closed_for_unsafe_or_incomplete_output(payload: str):
    with pytest.raises(ValueError):
        secure_html_tool(payload)
