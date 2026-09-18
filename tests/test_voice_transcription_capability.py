from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import documents
from backend.services.voice import VoiceService


def _request(body: bytes, content_type: str) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/documents/voice/transcriptions",
        "headers": [(b"content-type", content_type.encode())],
    }, receive)


@pytest.mark.asyncio
async def test_voice_transcription_authenticated_success_and_fail_closed(monkeypatch):
    class Working:
        async def transcribe(self, audio: bytes, format: str):
            assert audio == b"audio"
            assert format == "m4a"
            return "测试文本"

    monkeypatch.setattr(documents, "_voice_service", Working())
    result = await documents.transcribe_voice(
        _request(b"audio", "audio/m4a"),
        {"tenant_key": "tenant-a", "user_id": "user-a"},
    )
    assert result == {"text": "测试文本", "language": "zh", "status": "completed"}

    class Unavailable:
        async def transcribe(self, audio: bytes, format: str):
            raise RuntimeError("speech transcription is unavailable")

    monkeypatch.setattr(documents, "_voice_service", Unavailable())
    with pytest.raises(HTTPException) as unavailable:
        await documents.transcribe_voice(
            _request(b"audio", "audio/m4a"),
            {"tenant_key": "tenant-a", "user_id": "user-a"},
        )
    assert unavailable.value.status_code == 503


@pytest.mark.asyncio
async def test_voice_transcription_rejects_invalid_media_and_empty_body():
    with pytest.raises(HTTPException) as media:
        await documents.transcribe_voice(
            _request(b"audio", "text/plain"),
            {"tenant_key": "tenant-a", "user_id": "user-a"},
        )
    assert media.value.status_code == 415

    with pytest.raises(HTTPException) as empty:
        await documents.transcribe_voice(
            _request(b"", "audio/m4a"),
            {"tenant_key": "tenant-a", "user_id": "user-a"},
        )
    assert empty.value.status_code == 422


@pytest.mark.asyncio
async def test_voice_service_does_not_return_empty_success_when_model_missing():
    service = object.__new__(VoiceService)
    service.model = None
    with pytest.raises(RuntimeError, match="unavailable"):
        await service.transcribe(b"audio", "m4a")
