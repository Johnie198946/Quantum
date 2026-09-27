"""Owner-bound manual save and Chat share the same strict image recipe."""
import io
import hashlib
import pytest
from PIL import Image
from pydantic import ValidationError
from backend.services.image_processing import ImageEdit, save_image, expected_image_size
from backend.services.capability_catalog import invoke_capability, describe_capability
from backend.services.generated_artifacts import generated_artifact_path


def picture(size=(160,120), fmt="PNG"):
    stream = io.BytesIO()
    Image.new("RGB",size,"cornflowerblue").save(stream,format=fmt)
    return stream.getvalue()


@pytest.mark.asyncio
async def test_manual_save_owner_contract_and_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT",str(tmp_path))
    owner = {"tenant_key":"studio","user_id":"alice"}
    raw = picture()
    source = save_image("studio","alice",raw)
    result = save_image("studio","alice",picture((80,60),"JPEG"))
    edit = {"format":"jpg","studio":{"output_width":80,"output_height":60,"quality":0.7,"layers":[{"id":"title","text":"校园午后"}]}}
    data = {"source_artifact_id":source["artifact_id"],"result_artifact_id":result["artifact_id"],"source_hash":hashlib.sha256(raw).hexdigest(),"filename":"午后.jpg","edit":edit}
    async def save(data=data, actor=owner):
        return await invoke_capability("media.save_edit",data,payload=actor,idempotency_key="save-one")
    first = await save()
    assert first["status"] == "completed",first
    assert await save() == first
    receipt = first["events"][0]["payload"]
    path, stored = generated_artifact_path("studio","alice",receipt["artifact_id"])
    assert path.read_bytes() == picture((80,60),"JPEG")
    assert stored["metadata"]["operations"]["studio"]["layers"][0]["text"] == "校园午后"
    assert stored["kind"] == "image_processed"
    assert (await save({**data,"filename":"changed.jpg"}))["error"]["code"] == "idempotency_conflict"
    assert (await save(actor={**owner,"user_id":"bob"}))["status"] == "failed"
    assert (await save({**data,"source_hash":"0"*64}))["error"]["code"] == "source_changed"
    assert (await save({**data,"result_artifact_id":source["artifact_id"]}))["error"]["code"] == "result_mismatch"
    foreign = save_image("studio","bob",raw)
    bad = {**edit,"studio":{**edit["studio"],"layers":[{"id":"foreign","kind":"image","asset_id":foreign["artifact_id"]}]}}
    assert (await save({**data,"edit":bad}))["status"] == "failed"


@pytest.mark.parametrize("recipe",[
    {"quality":2},{"output_width":100},{"exposure":float("nan")},
    {"layers":[{"id":"x","kind":"image"}]},
    {"layers":[{"id":"x"},{"id":"x"}]},
    {"strokes":[{"id":"x","points":[{"x":2,"y":0}]}]},
    {"crops":[{"width":10,"height":10,"corners":[]}]},
    {"filter":"not-installed"},{"subject_x":-1},
])
def test_strict_recipe_boundaries(recipe):
    with pytest.raises(ValidationError): ImageEdit(studio=recipe)


def test_dimensions_and_pcm_exposure():
    edit = ImageEdit(studio={"rotation":90,"output_width":60,"output_height":80})
    assert expected_image_size({"width":160,"height":120},edit) == (60,80)
    contract = describe_capability("media.process")
    assert "studio" in contract["input_schema"]["properties"]
    assert contract["confirmation"] == "none"
    assert describe_capability("media.save_edit")["confirmation"] == "none"


def test_concurrent_save_publishes_one_immutable_artifact(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from backend.services.image_processing import save_processed_image
    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT",str(tmp_path))
    raw = picture()
    source = save_image("race","alice",raw)
    data = {"source_artifact_id":source["artifact_id"],"source_hash":source["content_hash"],"result_artifact_id":source["artifact_id"],"filename":"copy.png","edit":{"format":"png","studio":{}}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda _:save_processed_image("race","alice",data,"same-key"),range(8)))
    assert len({r["artifact_id"] for r in receipts}) == 1
    assert not list(tmp_path.rglob(".pending-*"))


def test_pcm_studio_schema_matches_validated_domain_model():
    schema = ImageEdit.model_json_schema()
    def expanded(v):
        if isinstance(v,list): return [expanded(x) for x in v]
        if not isinstance(v,dict): return v
        if "$ref" in v: return expanded(schema["$defs"][v["$ref"].split("/")[-1]])
        return {k:expanded(x) for k,x in v.items() if k not in {"title","$defs"}}
    expected = expanded(schema)
    assert describe_capability("media.process")["input_schema"]["properties"]["studio"] == expected["properties"]["studio"]
    assert describe_capability("media.save_edit")["input_schema"]["properties"]["edit"] == expected


@pytest.mark.asyncio
async def test_chat_bridge_can_save_real_uploaded_pixels(tmp_path,monkeypatch):
    import asyncio,json
    import scripts.hermes_bridge as bridge
    monkeypatch.setenv("AI_LAB_GENERATED_ARTIFACT_ROOT",str(tmp_path))
    original = save_image("bridge-studio","alice",picture())
    actor = {"tenant_key":"bridge-studio","user_id":"alice"}
    data = {"source_artifact_id":original["artifact_id"],"source_hash":original["content_hash"],"result_artifact_id":original["artifact_id"],"filename":"copy.png","edit":{"format":"png","studio":{}}}
    old_loop = bridge._bridge_async_loop;bridge._bridge_async_loop = asyncio.get_running_loop()
    def invoke():
        bridge._client_context_tool_context.value = {"identity":actor,"request_id":"image-studio-bridge-save"}
        try: return json.loads(bridge._app_capability_invoke_tool({"capability_id":"media.save_edit","input":data}))
        finally: bridge._client_context_tool_context.value = None
    try:
        result = await asyncio.to_thread(invoke)
        assert result["status"] == "completed",result
        assert result["events"][0]["renderer"] == "image_card"
        assert await asyncio.to_thread(invoke) == result
    finally: bridge._bridge_async_loop = old_loop
