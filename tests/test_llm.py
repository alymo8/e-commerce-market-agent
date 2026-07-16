from app.llm.deepseek import extract_json_object


def test_extract_json_from_fenced_reply():
    reply = 'Here you go:\n```json\n{"summary": "ok", "recommendations": ["a"]}\n```'
    obj = extract_json_object(reply)
    assert obj["summary"] == "ok"
    assert obj["recommendations"] == ["a"]


def test_extract_json_raises_when_absent():
    import pytest
    with pytest.raises(ValueError):
        extract_json_object("no json here")
