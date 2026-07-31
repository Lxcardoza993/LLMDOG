"""llmdog 核心逻辑测试:探活 / 四道护栏 / bug 学习循环 / 内置动作。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import urllib.request

import llmdog


# ============ probe ============
def test_probe_cmd_success():
    ok, _d = llmdog.probe({'probe': {'cmd': 'true'}})
    assert ok is True


def test_probe_cmd_fail():
    ok, _d = llmdog.probe({'probe': {'cmd': 'false'}})
    assert ok is False


def test_probe_cmd_timeout():
    ok, _d = llmdog.probe({'probe': {'cmd': 'sleep 30'}})
    assert ok is False  # run() 默认 timeout 15s


def test_probe_bad_words_fake_200(monkeypatch):
    """假 200 坑:body 含坏词算失败(防 503 错误体塞进 200 body)。"""
    class FakeResp:
        def getcode(self): return 200
        def read(self): return b'{"error":"auth_unavailable"}'
    monkeypatch.setattr(urllib.request, 'urlopen', lambda req, timeout=10: FakeResp())
    ok, d = llmdog.probe({'probe': {'url': 'http://x', 'bad_words': ['auth_unavailable']}})
    assert ok is False
    assert 'auth_unavailable' in d


def test_probe_ok_statuses_401(monkeypatch):
    """要 auth 的控制器(401)算活——连得上=服务在。"""
    import urllib.error
    def fake_urlopen(req, timeout=10):
        raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {}, None)
    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    ok, _d = llmdog.probe({'probe': {'url': 'http://x', 'ok_statuses': [200, 401], 'bad_words': []}})
    assert ok is True


# ============ guardrails 四道护栏 ============
def test_guardrails_pass():
    svc = {'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = {'action_type': 'builtin', 'action_cmd': 'kill_main_pid(x.service)',
            'rollback_cmd': 'builtin:noop', 'risk': 'low'}
    ok, why = llmdog.guardrails(svc, plan)
    assert ok, why


def test_guardrails_not_in_whitelist():
    svc = {'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = {'action_type': 'builtin', 'action_cmd': 'kill_main_pid(y.service)',
            'rollback_cmd': 'builtin:noop', 'risk': 'low'}
    ok, _ = llmdog.guardrails(svc, plan)
    assert not ok  # y 不在白名单


def test_guardrails_blacklist_rm_rf():
    svc = {'whitelist': ['shell:rm -rf /']}
    plan = {'action_type': 'shell', 'action_cmd': 'rm -rf /',
            'rollback_cmd': 'shell:rm -rf /', 'risk': 'low'}
    ok, why = llmdog.guardrails(svc, plan)
    assert not ok
    assert '黑名单' in why


def test_guardrails_blacklist_workflow():
    svc = {'whitelist': ['shell:vim .github/workflows/x.yml']}
    plan = {'action_type': 'shell', 'action_cmd': 'vim .github/workflows/x.yml',
            'rollback_cmd': 'shell:vim .github/workflows/x.yml', 'risk': 'low'}
    ok, _why = llmdog.guardrails(svc, plan)
    assert not ok


def test_guardrails_risk_not_low():
    svc = {'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = {'action_type': 'builtin', 'action_cmd': 'kill_main_pid(x.service)',
            'rollback_cmd': 'builtin:noop', 'risk': 'high'}
    ok, _ = llmdog.guardrails(svc, plan)
    assert not ok


def test_guardrails_rollback_query_rejected():
    """rollback 是纯查询(诊断命令)非动作→拒(模拟时 LLM 曾把诊断当 rollback)。"""
    svc = {'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = {'action_type': 'builtin', 'action_cmd': 'kill_main_pid(x.service)',
            'rollback_cmd': 'systemctl status x', 'risk': 'low'}
    ok, why = llmdog.guardrails(svc, plan)
    assert not ok
    assert '动作词' in why or '查询' in why


def test_guardrails_noop_rollback_ok():
    """builtin:noop 是合法 rollback(kill 后 systemd Restart=always 自拉回)。"""
    svc = {'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = {'action_type': 'builtin', 'action_cmd': 'kill_main_pid(x.service)',
            'rollback_cmd': 'builtin:noop', 'risk': 'low'}
    ok, _ = llmdog.guardrails(svc, plan)
    assert ok


# ============ build_fixed_plan(fixed_rule 快路径)============
def test_build_fixed_plan_strips_shell_prefix():
    """回归:action_cmd 必须剥 shell: 前缀——否则撞上 guardrails 的无前缀
    wl_norm 永远不匹配(2026-07-31 tgbot_verify 被自家护栏拦截 4h 的根因)。"""
    svc = {'fixed_action': 'shell:docker restart c', 'rollback': ['shell:docker start c'],
           'whitelist': ['shell:docker restart c']}
    plan = llmdog.build_fixed_plan(svc)
    assert plan['action_type'] == 'shell'
    assert plan['action_cmd'] == 'docker restart c'
    assert plan['rollback_cmd'] == 'shell:docker start c'  # rollback 保留前缀(护栏特例认 builtin:noop)
    ok, why = llmdog.guardrails(svc, plan)
    assert ok, why


def test_build_fixed_plan_builtin_prefix():
    svc = {'fixed_action': 'builtin:kill_main_pid(x.service)', 'rollback': ['builtin:noop'],
           'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = llmdog.build_fixed_plan(svc)
    assert plan['action_type'] == 'builtin'
    assert plan['action_cmd'] == 'kill_main_pid(x.service)'
    ok, why = llmdog.guardrails(svc, plan)
    assert ok, why


# ============ _learn_bug 学习通知去重 ============
def test_learn_bug_notify_only_once_even_if_state_lost(tmp_paths, mock_llm, monkeypatch):
    """同一 bug 只 🧠 通知一次——即使 bugs.json/services_learned.yaml 被删
    (2026-07-31 真实事故:state 文件丢失 → 重学 → TG 重复轰炸)。"""
    sent = []
    monkeypatch.setattr(llmdog, 'notify', lambda m: sent.append(m))
    svc = {'name': 'cpa', 'whitelist': ['builtin:kill_main_pid(x.service)']}
    plan = {'action_cmd': 'kill_main_pid(x.service)', 'root_cause': 'mem stuck'}
    # 连续 3 次真修复成功,达到学习阈值
    for _ in range(3):
        llmdog._learn_bug(svc, plan, 'diag', True)
    assert len([m for m in sent if '学了新 bug' in m]) == 1
    # 模拟状态文件被删(bugs.json + learned.yaml),计数清零重学
    os.remove(llmdog.BUGS_JSON)
    os.remove(llmdog.LEARNED_YAML)
    for _ in range(3):
        llmdog._learn_bug(svc, plan, 'diag', True)
    # notified.json 独立存活 → 不再重报;learned.yaml 会重建(自愈知识不丢)
    assert len([m for m in sent if '学了新 bug' in m]) == 1
    assert os.path.exists(llmdog.LEARNED_YAML)


# ============ bug 签名 ============
def test_bug_sig_same():
    assert llmdog._bug_sig('cpa', 'memory stuck') == llmdog._bug_sig('cpa', 'memory stuck')


def test_bug_sig_diff_service():
    assert llmdog._bug_sig('cpa', 'x') != llmdog._bug_sig('hermes', 'x')


def test_bug_sig_diff_root_cause():
    assert llmdog._bug_sig('cpa', 'a') != llmdog._bug_sig('cpa', 'b')


# ============ bug 学习循环 ============
def test_learn_bug_writes_learned(tmp_paths, mock_llm):
    svc = {'name': 'cpa', 'whitelist': ['builtin:kill_main_pid(cli-proxy-api.service)']}
    plan = {'root_cause': 'memory unavailable stuck',
            'action_cmd': 'kill_main_pid(cli-proxy-api.service)', 'action_type': 'builtin'}
    for _ in range(3):  # 反复 3 次达阈值
        llmdog._learn_bug(svc, plan, 'some diag', True)
    assert os.path.exists(tmp_paths / 'learned.yaml')
    import yaml
    learned = yaml.safe_load(open(tmp_paths / 'learned.yaml'))
    assert 'cpa' in learned
    assert len(learned['cpa']['known_issues']) >= 1


def test_learn_bug_below_threshold_no_learn(tmp_paths, mock_llm):
    svc = {'name': 'cpa', 'whitelist': []}
    plan = {'root_cause': 'x', 'action_cmd': '', 'action_type': 'builtin'}
    llmdog._learn_bug(svc, plan, 'd', True)  # 只 1 次
    assert not os.path.exists(tmp_paths / 'learned.yaml')  # 未达阈值不提炼


def test_learn_bug_dry_run_skip(tmp_paths, mock_llm, monkeypatch):
    monkeypatch.setattr(llmdog, 'DRY_RUN', True)
    svc = {'name': 'cpa', 'whitelist': []}
    plan = {'root_cause': 'x', 'action_cmd': '', 'action_type': 'builtin'}
    for _ in range(3):
        llmdog._learn_bug(svc, plan, 'd', True)
    assert not os.path.exists(tmp_paths / 'learned.yaml')  # DRY_RUN 不学


def test_learn_bug_low_severity_skip(tmp_paths, mock_llm):
    """LLM 判 med/low 不加入监控(只 high 才加)。"""
    mock_llm.append('{"name":"minor","symptom":"s","root_cause":"r",'
                     '"fix_action":"builtin:noop","severity":"med"}')
    svc = {'name': 'cpa', 'whitelist': []}
    plan = {'root_cause': 'minor bug', 'action_cmd': '', 'action_type': 'builtin'}
    for _ in range(3):
        llmdog._learn_bug(svc, plan, 'd', True)
    assert not os.path.exists(tmp_paths / 'learned.yaml')  # med 不加入


# ============ 内置动作 ============
def test_execute_builtin_noop():
    rc, _d = llmdog.execute_builtin('noop')
    assert rc == 0


def test_execute_builtin_kill_invalid_unit():
    """kill_main_pid 不存在的 unit:无 MainPID → rc=1 不崩。"""
    rc, _d = llmdog.execute_builtin('kill_main_pid(nonexistent-xxx.service)')
    assert rc == 1  # 无 MainPID,安全返回不崩


# ============ 状态 ============
def test_state_save_load(tmp_paths):
    st = {'cpa': {'fail_count': 5, 'last_fix': 123}}
    llmdog.save_state(st)
    loaded = llmdog.load_state()
    assert loaded['cpa']['fail_count'] == 5


# ============ main 流程集成 ============
def _write_svc(tmp_paths, svc, monkeypatch):
    import yaml
    monkeypatch.setattr(llmdog, 'SERVICES_YAML', str(tmp_paths / 'services.yaml'))
    yaml.dump({'services': [svc]}, open(str(tmp_paths / 'services.yaml'), 'w'),
              allow_unicode=True)
    monkeypatch.setattr(llmdog, 'TG_BOT', '')
    monkeypatch.setattr(llmdog, 'TG_CHAT', '')


def test_main_healthy_clears_counter(tmp_paths, monkeypatch):
    """探活通→清计数,不告警。"""
    _write_svc(tmp_paths, {'name': 'ok_svc', 'probe': {'cmd': 'true'},
              'fail_threshold': 3, 'cooldown_min': 10, 'mode': 'alert',
              'diagnostics': ['true'], 'whitelist': [], 'rollback': [],
              'known_issues': []}, monkeypatch)
    notified = []
    monkeypatch.setattr(llmdog, 'notify', lambda m: notified.append(m))
    llmdog.main()
    st = llmdog.load_state()
    assert st['ok_svc']['fail_count'] == 0
    assert not notified


def test_main_alert_mode_notifies(tmp_paths, mock_llm, monkeypatch):
    """alert 模式:探活失败→告警,不调 LLM 执行。"""
    _write_svc(tmp_paths, {'name': 'alert_svc', 'probe': {'cmd': 'false'},
              'fail_threshold': 1, 'cooldown_min': 0, 'mode': 'alert',
              'diagnostics': ['true'], 'whitelist': [], 'rollback': [],
              'known_issues': []}, monkeypatch)
    notified = []
    monkeypatch.setattr(llmdog, 'notify', lambda m: notified.append(m))
    llmdog.main()
    assert any('alert_svc' in n for n in notified)


def test_main_dry_run_fake_execute(tmp_paths, mock_llm, monkeypatch):
    """DRY_RUN: llm_analyze 出方案→护栏通过→假执行(不真 kill),记 DRYRUN。"""
    monkeypatch.setattr(llmdog, 'DRY_RUN', True)
    _write_svc(tmp_paths, {'name': 'llm_svc', 'probe': {'cmd': 'false'},
              'fail_threshold': 1, 'cooldown_min': 0, 'mode': 'llm_analyze',
              'diagnostics': ['true'],
              'whitelist': ['builtin:kill_main_pid(x.service)'],
              'rollback': ['builtin:noop'], 'known_issues': []}, monkeypatch)
    notified = []
    monkeypatch.setattr(llmdog, 'notify', lambda m: notified.append(m))
    llmdog.main()
    st = llmdog.load_state()
    assert st['llm_svc']['last_fix'] > 0  # DRY_RUN 也设 last_fix
    assert st['llm_svc']['fail_count'] == 1  # 未清零(DRY_RUN 未真修复验证)


def test_main_llm_unavailable_fallback(tmp_paths, monkeypatch):
    """LLM 不可用(call_llm 返回 None)→ 发原始诊断 TG,不执行。"""
    monkeypatch.setattr(llmdog, 'call_llm', lambda p, timeout=60: None)
    _write_svc(tmp_paths, {'name': 'dead_svc', 'probe': {'cmd': 'false'},
              'fail_threshold': 1, 'cooldown_min': 0, 'mode': 'llm_analyze',
              'diagnostics': ['true'],
              'whitelist': ['builtin:kill_main_pid(x.service)'],
              'rollback': ['builtin:noop'], 'known_issues': []}, monkeypatch)
    notified = []
    monkeypatch.setattr(llmdog, 'notify', lambda m: notified.append(m))
    llmdog.main()
    assert any('LLM' in n and '不可用' in n for n in notified)


# ============ known_issue_fallback(LLM 不可用的已知病快路径)============
def test_known_issue_fallback_whitelisted(tmp_paths):
    """fix_action 剥前缀后在白名单 → 出 plan,且能过四道护栏。"""
    svc = {'name': 'cpa',
           'whitelist': ['builtin:kill_main_pid(cli-proxy-api.service)'],
           'rollback': ['builtin:noop'],
           'known_issues': [{'name': 'mem stuck',
                             'fix_action': 'builtin:kill_main_pid(cli-proxy-api.service)'}]}
    plan = llmdog.known_issue_fallback(svc)
    assert plan and plan['action_cmd'] == 'kill_main_pid(cli-proxy-api.service)'
    assert plan['action_type'] == 'builtin'
    ok, why = llmdog.guardrails(svc, plan)
    assert ok, why


def test_known_issue_fallback_not_whitelisted(tmp_paths):
    """fix_action 不在白名单 → None(白名单=人工预授权,超纲不动)。"""
    svc = {'name': 'cpa', 'whitelist': ['builtin:noop'],
           'known_issues': [{'name': 'x', 'fix_action': 'shell:rm -rf /tmp/x'}]}
    assert llmdog.known_issue_fallback(svc) is None


def test_main_llm_down_known_issue_executes(tmp_paths, monkeypatch):
    """LLM 不可用但 known_issues 有白名单内对症动作 → 直接执行不再只告警。
    2026-08-01 00:27/00:38 实战:CPA 卡死=8317 自己挂,llm_analyze 瘫痪两次'需人工'。"""
    monkeypatch.setattr(llmdog, 'call_llm', lambda p, timeout=60: None)
    _write_svc(tmp_paths, {'name': 'cpa', 'probe': {'cmd': 'false'},
              'fail_threshold': 1, 'cooldown_min': 0, 'mode': 'llm_analyze',
              'verify_wait': 0, 'diagnostics': ['true'],
              'whitelist': ['builtin:kill_main_pid(x.service)'],
              'rollback': ['builtin:noop'],
              'known_issues': [{'name': 'mem stuck',
                                'fix_action': 'builtin:kill_main_pid(x.service)'}]}, monkeypatch)
    executed = []
    monkeypatch.setattr(llmdog, 'execute',
                        lambda plan: executed.append(plan['action_cmd']) or (0, 'ok'))
    notified = []
    monkeypatch.setattr(llmdog, 'notify', lambda m: notified.append(m))
    calls = {'n': 0}

    def fake_probe(svc):
        calls['n'] += 1
        return (calls['n'] > 1), 'ok'  # 首次死(触发),复查活(修复成功)

    monkeypatch.setattr(llmdog, 'probe', fake_probe)
    llmdog.main()
    assert executed == ['kill_main_pid(x.service)']  # 走了 fallback 真执行
    assert any('修复成功' in n for n in notified)
    assert not any('不可用' in n for n in notified)  # 不再只告警需人工


# ============ call_llm 多提供商 failover ============
def _write_providers(tmp_paths, providers, monkeypatch):
    """写只含 llm_providers 的 services.yaml,并把 SERVICES_YAML 指过去。"""
    import yaml
    monkeypatch.setattr(llmdog, 'SERVICES_YAML', str(tmp_paths / 'services.yaml'))
    yaml.dump({'services': [], 'llm_providers': providers},
              open(str(tmp_paths / 'services.yaml'), 'w'), allow_unicode=True)


class _FakeLLMResp:
    def __init__(self, d):
        self._d = d

    def read(self):
        return json.dumps(self._d).encode()


def test_call_llm_failover_to_second(tmp_paths, monkeypatch):
    """第一家挂(连接异常)→ 自动切第二家并返回。
    动机:8317=CPA 自己,CPA 卡死时 LLM 全瘫只能告警(2026-08-01 凌晨实战)。"""
    _write_providers(tmp_paths, [
        {'name': 'dead', 'url': 'http://x/1', 'key': 'k', 'model': 'm'},
        {'name': 'alive', 'url': 'http://x/2', 'key': 'k', 'model': 'm'},
    ], monkeypatch)

    def fake_urlopen(req, timeout=60):
        if '/1' in req.full_url:
            raise TimeoutError('hang')
        return _FakeLLMResp({'content': [{'type': 'text', 'text': 'ok-answer'}]})

    monkeypatch.setattr(llmdog.urllib.request, 'urlopen', fake_urlopen)
    assert llmdog.call_llm('p') == 'ok-answer'


def test_call_llm_fake200_failover(tmp_paths, monkeypatch):
    """第一家返回假 200(auth_unavailable 错误体塞进 200)→ 当失败切第二家。"""
    _write_providers(tmp_paths, [
        {'name': 'fake', 'url': 'http://x/1', 'key': 'k', 'model': 'm'},
        {'name': 'alive', 'url': 'http://x/2', 'key': 'k', 'model': 'm'},
    ], monkeypatch)

    def fake_urlopen(req, timeout=60):
        if '/1' in req.full_url:
            return _FakeLLMResp({'content': [{'type': 'text',
                                 'text': 'auth_unavailable: no auth available'}]})
        return _FakeLLMResp({'content': [{'type': 'text', 'text': 'real-answer'}]})

    monkeypatch.setattr(llmdog.urllib.request, 'urlopen', fake_urlopen)
    assert llmdog.call_llm('p') == 'real-answer'


def test_call_llm_all_down_returns_none(tmp_paths, monkeypatch):
    """全挂 → None(走 known_issue_fallback/告警,不崩)。"""
    _write_providers(tmp_paths, [
        {'name': 'd1', 'url': 'http://x/1', 'key': 'k', 'model': 'm'},
        {'name': 'd2', 'url': 'http://x/2', 'key': 'k', 'model': 'm'},
    ], monkeypatch)

    def boom(req, timeout=60):
        raise ConnectionError('down')

    monkeypatch.setattr(llmdog.urllib.request, 'urlopen', boom)
    assert llmdog.call_llm('p') is None


def test_call_llm_env_fallback_when_no_providers(tmp_paths, monkeypatch):
    """services.yaml 无 llm_providers → 回退 env 单 provider(向后兼容老配置)。"""
    monkeypatch.setattr(llmdog, 'SERVICES_YAML', str(tmp_paths / 'nonexist.yaml'))
    monkeypatch.setattr(llmdog, 'LLM_URL', 'http://x/9')
    monkeypatch.setattr(llmdog, 'LLM_KEY', 'k')
    monkeypatch.setattr(llmdog, 'LLM_MODEL', 'm')
    monkeypatch.setattr(llmdog.urllib.request, 'urlopen',
                        lambda req, timeout=60: _FakeLLMResp(
                            {'content': [{'type': 'text', 'text': 'env-answer'}]}))
    assert llmdog.call_llm('p') == 'env-answer'
