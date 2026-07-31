"""pytest 共享 fixture:mock LLM + 临时 state 目录,避免测试污染真实运行时。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest

import llmdog


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch):
    """重定向 state/log 到临时目录,测试不碰真实 state/。"""
    d = str(tmp_path)
    os.makedirs(d, exist_ok=True)
    monkeypatch.setattr(llmdog, 'STATE_DIR', d)
    monkeypatch.setattr(llmdog, 'LOG_DIR', d)
    monkeypatch.setattr(llmdog, 'STATE_FILE', os.path.join(d, 'state.json'))
    monkeypatch.setattr(llmdog, 'BUGS_JSON', os.path.join(d, 'bugs.json'))
    monkeypatch.setattr(llmdog, 'LEARNED_YAML', os.path.join(d, 'learned.yaml'))
    monkeypatch.setattr(llmdog, 'NOTIFIED_JSON', os.path.join(d, 'notified.json'))
    monkeypatch.setattr(llmdog, 'LOCK_FILE', os.path.join(d, 'lock'))
    monkeypatch.setattr(llmdog, 'DRY_RUN', False)  # 测试真修复路径(不跳过 _learn_bug)
    return tmp_path


@pytest.fixture
def mock_llm(monkeypatch):
    """mock call_llm,可往 queue 塞预设返回;默认返回一个合法 kill 方案 JSON。"""
    queue = []

    def fake(prompt, timeout=60):
        if queue:
            return queue.pop(0)
        # 按 prompt 内容返回不同格式(_learn_bug 调 _llm_extract_issue / llm_confirm / llm_analyze)
        if '提炼成 known_issue' in prompt or 'known_issue' in prompt:
            return ('{"name":"memory stuck","symptom":"auth_unavailable","root_cause":"mem stuck",'
                    '"fix_action":"builtin:kill_main_pid(x.service)","severity":"high"}')
        if 'approve' in prompt:
            return '{"approve":true,"concern":"ok"}'
        # llm_analyze 格式
        return ('{"root_cause":"memory stuck","action_type":"builtin",'
                '"action_cmd":"kill_main_pid(x.service)",'
                '"rollback_cmd":"builtin:noop","risk":"low","reason":"test"}')

    monkeypatch.setattr(llmdog, 'call_llm', fake)
    return queue
