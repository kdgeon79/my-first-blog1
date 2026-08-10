import json
import subprocess

import pytest

import config
import llm


def test_extract_json_direct():
    assert llm._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_noise():
    noisy = "실행 중...\n```json\n{\"foods\": [], \"total_kcal\": 0, \"comment\": \"ok\"}\n```\n완료"
    assert llm._extract_json(noisy)["comment"] == "ok"


def test_extract_json_failure():
    with pytest.raises(ValueError):
        llm._extract_json("JSON 없음")


def _fake_run(result_stdout, calls):
    def fake(cmd, capture_output, text, timeout):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=result_stdout, stderr="")

    return fake


def test_parse_meal_via_codex_cli(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "cli")
    monkeypatch.setattr(config, "LLM_CLI", "codex")
    calls = []
    payload = json.dumps(
        {"foods": [{"name": "김밥", "quantity": "1줄", "kcal": 350}], "total_kcal": 350, "comment": "좋아요"}
    )
    monkeypatch.setattr(subprocess, "run", _fake_run(f"배너 로그\n{payload}", calls))

    parsed = llm.parse_meal("김밥 한 줄")
    assert parsed["total_kcal"] == 350
    cmd = calls[0]
    assert cmd[0] == "codex" and cmd[1] == "exec"
    assert "JSON 스키마" in cmd[-1]  # 스키마 지시가 프롬프트에 포함됨


def test_claude_cli_command_shape(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "cli")
    monkeypatch.setattr(config, "LLM_CLI", "claude")
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run('{"ok": true}', calls))

    llm._generate("시스템", "질문")
    cmd = calls[0]
    assert cmd[0] == "claude" and cmd[1] == "-p"


def test_cli_nonzero_exit_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "cli")

    def fake(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="login required")

    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(llm.LLMCliError):
        llm.parse_meal("김밥")


def test_cli_missing_binary_raises(monkeypatch):
    monkeypatch.setattr(config, "LLM_BACKEND", "cli")

    def fake(cmd, capture_output, text, timeout):
        raise FileNotFoundError(cmd[0])

    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(llm.LLMCliError):
        llm.parse_meal("김밥")


def test_image_goes_through_temp_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LLM_BACKEND", "cli")
    monkeypatch.setattr(config, "LLM_CLI", "codex")
    seen = {}

    def fake(cmd, capture_output, text, timeout):
        # codex exec -i <임시파일> <프롬프트>
        idx = cmd.index("-i")
        seen["image_path"] = cmd[idx + 1]
        from pathlib import Path

        seen["existed_during_call"] = Path(cmd[idx + 1]).exists()
        payload = json.dumps({"foods": [], "total_kcal": 0, "comment": ""})
        return subprocess.CompletedProcess(cmd, 0, stdout=payload, stderr="")

    monkeypatch.setattr(subprocess, "run", fake)
    llm.parse_meal_image(b"fake-bytes", "image/jpeg", "점심")

    assert seen["image_path"].endswith(".jpg")
    assert seen["existed_during_call"] is True
    from pathlib import Path

    assert not Path(seen["image_path"]).exists()  # 호출 후 임시 파일 정리
