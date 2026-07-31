# LLMDOG · 设计文档

> 给用户/贡献者看的设计文档。大白话,先结论。

## 一句话

本机服务看门狗,每 2 分钟探一遍你指定的服务(加服务就往 `services.yaml` 加一条)。哪个连续几次探不通,就:收诊断 → 调本地 LLM 分析根因+出修复方案 → 四道护栏把关 → 备份 → 执行 → 验证 → 成了发 TG,没成回滚+升级告警。还能把反复修过的 bug 自动学进监控,下次复发自己治。

## 和传统看门狗的区别

传统看门狗是**固定规则**:探不通就重启,一根筋。

LLMDOG 多一层 **LLM 分析**:把诊断数据(日志、进程、端口、systemd 状态)喂给本地 LLM,让它自己判断该 restart / kill 进程 / 还是告警。能处理"根因不明"的情况,不是无脑重启。还多一层 **bug 学习**:真修过的 bug 自动提炼成 known_issue 写进监控,复发时 LLM 直接对症。

代价:慢一点、费点 token、LLM 自己可能抖。所以默认 DRY_RUN(只分析+出方案+假执行,不动真格),跑稳了再开真修复。

## 四道护栏(直接修复,但反复确认/最小改动/可回滚)

1. **反复确认** — LLM 出方案后,再调一次 LLM 做二次确认,两次都同意才执行。
2. **最小改动** — 只允许 whitelist 里的动作(`builtin:xxx` 内置安全 / `shell:xxx` 逐字校验)。
3. **可回滚** — 每个动作必须配 rollback 命令(或 `builtin:noop` 当 systemd Restart=always 自拉回);rollback 要含动作词,不能是纯查询。
4. **黑名单** — 禁 `rm -rf` / force push / 删数据库 / 改 workflow / 改 CPA config 等。

## 三档 mode

| mode | 干啥 | 用在 |
|---|---|---|
| `llm_analyze` | 走 LLM 分析根因+出方案+修复 | 能修的(user 级服务 / docker 容器 / os.kill 属主进程) |
| `fixed_rule` | 固定动作快路径(不调 LLM) | 根因明确的快路径 |
| `alert` | 只探活+告警,不修复 | 无权限(系统级需 root)/ 重叠(别的看门狗已管) |

## 文件结构

```
llmdog/
├── llmdog.py              # 主脚本(探活/诊断/调LLM/护栏/执行/验证/通知/学习)
├── services.yaml          # 服务清单(人工配置,.gitignore 不入库)
├── services.yaml.example  # 示例配置(提交)
├── config.env             # 配置(LLM端点/TG token/DRY_RUN,.gitignore 不入库)
├── config.env.example     # 示例配置(提交)
├── llmdog.service         # systemd oneshot
├── llmdog.timer           # 每 2 分钟触发
├── state/                 # 状态(state.json / bugs.json / services_learned.yaml / lock)
├── logs/                  # 日志
└── SPEC.md                # 本文件

~/.config/systemd/user/
├── llmdog.service         # user 级(不需 sudo)
└── llmdog.timer           # OnBootSec=2min, OnUnitInactiveSec=2min, Persistent=true
```

## services.yaml 字段

```yaml
- name: my_service
  probe:                       # 探活:HTTP url 或 cmd shell
    url: http://127.0.0.1:8080/v1/messages   # 或 cmd: "docker info --format ..."
    method: POST
    headers: {Authorization: "Bearer <YOUR_KEY>"}
    body: '...'
    ok_statuses: [200]         # 默认[200];要auth的控制器用[200,401](401=连得上=活)
    bad_words: ["auth_unavailable"]  # body 含这些词算失败(防假200)
  fail_threshold: 3            # 连续几次失败才触发
  cooldown_min: 10             # 两次修复间隔(防抖)
  mode: llm_analyze            # llm_analyze | fixed_rule | alert
  diagnostics: [...]           # 触发后收集的诊断命令(喂LLM)
  whitelist: [...]             # LLM 只能从这选动作(builtin:xxx / shell:xxx)
  rollback: [...]              # 回滚动作
  known_issues: [...]          # 历史反复bug(症状+根因+对症修法),喂LLM复发对症
```

**动作两类**:
- `builtin:xxx` — llmdog.py 内置动作(安全预定义):`kill_main_pid`(拿 MainPID → SIGTERM 5s → SIGKILL,属主你不用 sudo;systemd Restart=always 自拉回)、`noop`(无操作,用于 kill 后自拉回的 rollback)。
- `shell:xxx` — shell 命令,护栏逐字校验(必须在 whitelist 且不碰黑名单)。

> ⚠️ llmdog 以普通用户跑(user 级 systemd),`shell:systemctl restart 系统级服务` 会 Permission denied。系统级服务用 `builtin:kill_main_pid`(os.kill 不需 root,前提是进程属主是你)。

## bug 学习自愈机制

- **bugs.json**:每次真修复成功(非 DRY_RUN)记 bug 签名(服务+根因),去重计数
- 反复≥3 次 + LLM 判严重(high) → 调 LLM 提炼成 known_issue(症状+根因+对症 fix_action)
- 写进 `state/services_learned.yaml`(纯数据,不动 services.yaml 注释)
- 下轮 `load_services` merge:learned 的 known_issues/whitelist 追加进运行时配置
- LLM 看 known_issues 对症从 whitelist 出 action → 自愈
- **安全**:只真修复才学;whitelist 只自动加 builtin(防误伤),shell 不自动加;发 TG 告知学了啥

## LLM 调用

- **端点**:你的 LLM 代理(直连,不走 clash 出口——防 clash 挂时看门狗也瞎)
- **non-stream**(防假 200:有些代理把 503 错误体塞进 HTTP 200 body)
- **取回复**:遍历 content 找 `type==text` 块取其 `text`(不能取 `content[0]`,reasoning 模型那是 thinking 块)
- **max_tokens 2000+**(reasoning 模型先吃 token,小了会空回复截断)
- LLM 不可用 → 降级发原始诊断 TG,不执行

## 流程

```
探活 → 通? → 清计数,结束
       ↓不通 计数+1,到阈值? → 没到:记日志结束
       ↓到了 cooldown内? → 是:结束
       ↓否 收诊断
       ↓ mode=alert? → 发TG告警,结束
       ↓ LLM分析 → 出方案
       ↓ 二次确认 → 不通过:告警,结束
       ↓ 四道护栏 → 不通过:告警,结束
       ↓ DRY_RUN? → 是:记方案,结束(不动真格)
       ↓否 执行 → sleep8s → 再探活
       ↓ 通? → 发TG修复成功 + 清计数 + 学习bug
       ↓不通 rollback + 发TG告警
```

## 安装

```bash
# 1. 配置
cp config.env.example config.env      # 填实际 LLM 端点/key、TG token,chmod 600
cp services.yaml.example services.yaml # 填你的服务

# 2. 装 user 级 systemd(不需 sudo)
mkdir -p ~/.config/systemd/user/
cp llmdog.service llmdog.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now llmdog.timer
loginctl enable-linger $USER  # 不登录也跑(若没开)

# 3. 验证
systemctl --user status llmdog.timer
tail -f logs/llmdog.log
python3 llmdog.py  # 手动跑一次
```

DRY_RUN 跑稳后,改 `config.env` 的 `LLMDOG_DRY_RUN=0`,下轮 timer 自动开真修复。
