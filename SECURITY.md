# 安全策略 Security Policy

## 报告漏洞 Report a Vulnerability

我们重视安全问题。如发现安全漏洞，请通过以下方式**(private)报告**:

- **私邮件**: li@lxlynx.com (PGP 可选)
- **私 GitHub Advisory**: 使用 GitHub Security Advisory 功能创建 private 的 Security Advisory

响应 SLA:
- 24 小时内确认收到报告
- 72 小时内给出初步评估和修复计划
- 7 天内发布修复版本(如需)

## 工具风险说明

**本工具会执行系统命令**,包括但不限于:

- `systemctl --user restart <service>` - 重启 systemd 服务
- `kill -9 <pid>` - 强制终止进程
- `docker restart <container>` - 重启容器
- 其他通过 `services.yaml` 配置的诊断/修复命令

**使用者须知风险**:
1. Always 首次使用前开启 `DRY_RUN: true`,查看拟执行的命令
2. Review `services.yaml` 中的 `diagnose` 和 `fix` 命令
3. 确保 systemd service 文件权限正确(不应 require sudo)
4. 建议在测试环境验证后再用于生产

## 四道护栏 Four Lines of Defense

本工具的安全边界:

| 防线 | 机制 | 说明 |
|------|------|------|
| **Line 1** | `DRY_RUN` | 默认开启,只输出不执行 |
| **Line 2** | `double-confirm` | 执行前需二次确认(交互模式) |
| **Line 3** | `minimal-change` | 只执行最小必要命令 |
| **Line 4** | `denylist` | 禁止执行危险命令(如 `rm -rf`, `dd`) |

## 已知限制

- systemd user-level timer 需用户级别 `pwchange` 或 `daemon-control` 权限
- 某些服务诊断需要额外权限(`journalctl` 需 `systemd-journal` group)

---

Last updated: 2026-07-31
