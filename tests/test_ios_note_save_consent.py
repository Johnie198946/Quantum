"""Guard the two stream consumers: completing an answer is not note consent."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reading_stream_completion_never_calls_note_writer():
    source = (ROOT / "ios/AIPlatformApp/Views/Settings/SettingsView.swift").read_text()
    selection_submit = source.split("private func submit(_ prompt: String) async {", 1)[1].split("private func recordActivity", 1)[0]
    sheet_submit = source.split("private func submit() async {", 1)[1].split("struct ReaderAnnotationEntry", 1)[0]
    for consumer in (selection_submit, sheet_submit):
        assert "saveAnswer(" not in consumer
        assert "onSaveAnswer" not in consumer
        assert "createNote(" not in consumer
    assert "Button(action: saveAnswer)" in source
    assert "if onSaveAnswer(lastQuestion, answer, sessionID) { dismiss() }" in source
    assert "automaticallySaveAnswer" not in source
    chat = (ROOT / "ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift").read_text()
    assert "automaticallySaveAnswer" not in chat
