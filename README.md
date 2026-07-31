# 🐶 LLMDOG

> A watchdog that actually *thinks*.
> An LLM-powered local-service watchdog: probe → diagnose with LLM → guardrail → fix → verify → self-heal. It even *learns* from bugs it has fixed, so recurrences heal themselves.

> 带个 LLM 大脑的本机服务看门狗:探活 → LLM 分析根因 → 四道护栏把关 → 修复 → 验证 → 失败回滚。还能把反复修过的 bug 自动学进监控,下次复发自己治——不用你半夜爬起来 restart。

[![Python 3](https://img.shields.io/badge/python-3.6%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-contributing)
[![default: DRY_RUN](https://img.shields.io/badge/default-DRY__RUN-orange.svg)](#-dry_run-安全模式)

**English** · [中文文档](#-中文文档)

---

## ✨ Features

- 🔍 **Multi-service probing** — HTTP `url` *or* shell `cmd`; check status code **and** body keywords (defeats the "200-with-error-body" fake-healthy trap).
- 🧠 **LLM root-cause analysis** — feeds diagnostics (logs / `systemctl` / `journalctl` / ports / `ps`) to a local LLM, gets a JSON repair plan.
- 🛡 **Four guardrails** — double-confirm (second LLM call) / minimal-change (whitelist) / rollbackable / denylist (`rm -rf`, force-push, data deletes…).
- 🧬 **Bug learning & self-healing** — every *real* successful fix is recorded; if a bug recurs ≥3 times and the LLM flags it *high* severity, it's distilled into a `known_issue` and written into monitoring. Next recurrence, the LLM recognizes the symptom and heals it from the whitelist.
- 📋 **Three modes** — `llm_analyze` (LLM-driven fix) / `fixed_rule` (deterministic fast path) / `alert` (only probe + notify, for services you can't or shouldn't auto-fix).
- 📨 **Telegram notify** — fixed-it / learned-a-bug / it's-down messages to your TG.
- ⏱ **systemd timer** — probes every 2 min, **user-level (no sudo)**.
- 🔒 **DRY_RUN by default** — analyzes + fake-executes, touches nothing real until you're confident.

## 🏗 How it works

```
 probe ──ok──▶ clear counter, done
   │
 fail
   ▼
 count+1, reach threshold? ──no──▶ log, done
   │ yes
 cooldown? ──yes─▶ skip
   │ no
 collect diagnostics (logs / systemctl / ps / curl)
   ▼
 mode=alert? ──yes──▶ TG alert, done            (can't/won't fix)
   │ no
 LLM analyze ──▶ plan JSON {root_cause, action, rollback, risk}
   ▼
 second LLM confirm ──fail──▶ TG alert, done
   ▼ pass
 four guardrails ──fail──▶ TG alert, done
   ▼ pass
 DRY_RUN? ──yes──▶ log plan, done                (no-op)
   │ no
 execute action ──▶ sleep 8s ──▶ re-probe
   ▼
 ok? ──yes──▶ TG "fixed" + clear counter + LEARN BUG
   │ no
 rollback + TG "failed, rolled back, needs human"
```

## 📦 Install

```bash
git clone https://github.com/YOUR_USER/LLMDOG.git
cd LLMDOG

# 1. config (fill your LLM endpoint/key + TG bot token, then chmod 600)
cp config.env.example config.env
cp services.yaml.example services.yaml   # edit to your services

# 2. install user-level systemd (NO sudo needed)
mkdir -p ~/.config/systemd/user/
cp llmdog.service llmdog.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llmdog.timer
loginctl enable-linger $USER   # run even when not logged in

# 3. verify
systemctl --user status llmdog.timer
tail -f logs/llmdog.log
python3 llmdog.py              # manual run
```

## ⚙️ Config

**`config.env`** (copy from `.example`, `chmod 600`):

```bash
LLMDOG_DRY_RUN=1                          # 1=analyze+fake-exec; 0=real fix
LLMDOG_LLM_URL=http://127.0.0.1:8317/v1/messages  # your LLM proxy (direct, not via clash)
LLMDOG_LLM_KEY=YOUR_KEY
LLMDOG_LLM_MODEL=deepseek-v4-pro
LLMDOG_TG_BOT_TOKEN=YOUR_TG_BOT_TOKEN     # leave empty = only log, no TG
LLMDOG_TG_CHAT_ID=YOUR_CHAT_ID
LLMDOG_TG_PROXY=http://127.0.0.1:8899     # telegram needs a proxy in CN
```

**`services.yaml`** (copy from `.example`, one entry per service):

```yaml
services:
  - name: my_llm_proxy
    probe:
      url: http://127.0.0.1:8317/v1/messages
      method: POST
      headers: {Authorization: "Bearer <YOUR_KEY>", anthropic-version: "2023-06-01"}
      body: '{"model":"glm-5.2","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
      bad_words: ["auth_unavailable", '"type":"error"']   # body keywords = fail (fake-200 trap)
    fail_threshold: 3
    cooldown_min: 10
    mode: llm_analyze          # llm_analyze | fixed_rule | alert
    diagnostics:
      - "systemctl status my-llm-proxy.service --no-pager -l"
      - "journalctl -u my-llm-proxy.service -n 80 --no-pager"
    whitelist:
      - "builtin:kill_main_pid(my-llm-proxy.service)"  # SIGTERM 5s→SIGKILL, no sudo; systemd auto-restarts
    rollback: ["builtin:noop"]                         # systemd Restart=always auto-recovers
    known_issues:
      - name: "memory-level stuck (config edit doesn't clear)"
        symptom: "body contains auth_unavailable, but process alive, /models responds"
        root_cause: "memory-level unavailable, config reload doesn't clear, kill to clear"
        fix_action: "builtin:kill_main_pid(my-llm-proxy.service)"
```

Edit `services.yaml` → next timer tick picks it up automatically (no restart). Edit `llmdog.py` → next tick uses the new code (oneshot re-reads each run).

## 🛡 The four guardrails

LLMDOG fixes things directly, but with four safety nets — set by the principle *"direct repair, but double-confirm / minimal-change / rollbackable, and the safety boundary need not be too strict"*:

1. **Double-confirm** — after the LLM proposes a plan, a second LLM call re-checks "is this right? any risk? any collateral damage?". Both must agree.
2. **Minimal change** — the action must verbatim-match a `whitelist` entry (`builtin:` or `shell:`).
3. **Rollbackable** — every action carries a `rollback_cmd` with an action verb (start/restart/kill/reload/stop), never a pure query.
4. **Denylist** — `rm -rf`, force-push, data deletes, workflow edits, config-file edits… blocked.

## 🧬 Bug learning & self-healing

Every *real* successful fix (not DRY_RUN) is recorded into `state/bugs.json` keyed by (service + root_cause). When a bug recurs ≥3 times and the LLM judges it *high* severity, it's distilled into a `known_issue` (symptom + root-cause + fix-action) and written into `state/services_learned.yaml`. On the next run, `load_services()` merges it into the live config — so the LLM sees the known issue in its prompt and heals the recurrence from the whitelist. You get a TG message whenever it learns something.

**Safety**: only *verified real fixes* are learned (DRY_RUN plans aren't); `whitelist` auto-adds only `builtin:` safe actions (never `shell:`, to prevent the LLM adding a harmful command).

## 🔒 DRY_RUN 安全模式

Default `LLMDOG_DRY_RUN=1`: llmdog probes + analyzes + fake-executes (logs the plan, touches nothing). When you've seen several successful dry-run plans *and* a real outage got the right plan, flip `LLMDOG_DRY_RUN=0` to enable real repair. Next timer tick picks it up — no restart needed.

## 📄 License

[MIT](LICENSE) — built for homelabbers, self-hosters, and anyone tired of 3am "why is my relay down" pages.

## 🙏 Acknowledgements

- **[OpenClaw 中文社区](https://github.com/openclaw)** — for the agent/reverse-engineering ecosystem and toolchain inspiration.
- **[linux.do 社区](https://linux.do)** — for the Chinese open-source & self-hosting community, where a lot of the real-world pain points (CPA, clash, WSL2, Docker Desktop watchdogs) were hashed out.

This project stands on the shoulders of the countless self-hosted watchdogs and proxy projects maintained by these communities.

---

## 🇨🇳 中文文档

带个 LLM 大脑的本机服务看门狗:每 2 分钟探一遍你指定的服务,探不通就收诊断→调本地 LLM 分析根因→四道护栏把关→执行→验证→成了发 TG,没成回滚+告警。还能把反复修过的 bug 自动学进监控,下次复发自己治。

### 特性

- 🔍 多服务探活:HTTP url 或 shell cmd,看状态码 + 看 body 关键词(防"503 错误体塞进 200 body"假活坑)
- 🧠 LLM 分析根因:诊断数据(日志/进程/systemd 状态)喂本地 LLM,出 JSON 修复方案
- 🛡 四道护栏:反复确认(二次 LLM)/ 最小改动(白名单)/ 可回滚 / 黑名单禁危险动作
- 🧬 bug 学习自愈:真修过的 bug 记库,反复≥3 次+LLM 判严重→自动提炼成 known_issue 加进监控→复发对症自愈
- 📋 三档 mode:`llm_analyze`(走 LLM 修复)/ `fixed_rule`(固定动作)/ `alert`(只告警不修复)
- 📨 TG 通知:修了啥/学啥/挂了啥都发 TG
- ⏱ systemd timer:每 2 分钟,user 级(不需 sudo)
- 🔒 DRY_RUN 默认:只分析+假执行,跑稳再开真修复

### 安装

```bash
git clone https://github.com/YOUR_USER/LLMDOG.git && cd LLMDOG
cp config.env.example config.env        # 填 LLM 端点/key + TG token,chmod 600
cp services.yaml.example services.yaml # 填你的服务
mkdir -p ~/.config/systemd/user/ && cp llmdog.service llmdog.timer ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now llmdog.timer
loginctl enable-linger $USER  # 不登录也跑
tail -f logs/llmdog.log
```

详见上方 English 部分的 Config / Guardrails / Bug learning 节(配置/护栏/学习机制通用,字段同名)。

### 致谢

- **[OpenClaw 中文社区](https://github.com/openclaw)** — agent/逆向工程生态与工具链启发。
- **[linux.do 社区](https://linux.do)** — 中文开源与自托管社区,大量真实痛点(CPA、clash、WSL2、Docker Desktop 看门狗)在此被反复打磨。

本项目站在这些社区维护的无数自托管看门狗与代理项目的肩膀上。

## 🤝 Contributing

PRs welcome. Keep `services.yaml` / `config.env` out of commits (they're in `.gitignore` — they hold real keys). Run `python3 -m py_compile llmdog.py` before submitting.
