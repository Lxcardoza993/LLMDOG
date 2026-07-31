---
name: Bug Report
about: 报告一个可复现的问题
title: "bug: [简短描述]"
labels: ["bug", "triage"]
---

## 环境 Environment

- Python 版本: `python --version`
- 操作系统: `uname -a` (WSL/Linux/macOS/Windows)
- llmdog 版本: `git rev-parse HEAD` 或 `pip show llmdog`
- 运行方式: systemd timer / direct CLI

## 配置 Configuration

`services.yaml` 中相关服务的配置片段:

```yaml
# 请提供复现问题的服务配置
```

## 日志 Log

> 通过 `grep <trace_id> /var/log/llmdog/*.log` 或 `journalctl --user -u llmdog.timer -n 100` 获取

```
2026-07-31 10:00:00 [INFO] Starting check for service: xxx
2026-07-31 10:00:01 [WARN] Service unavailable, attempting diagnose...
2026-07-31 10:00:02 [ERROR] Diagnose failed: ...
```

请提供完整的 trace_id 和关键日志行。

## DRY_RUN 状态

- [ ] 开启 (`DRY_RUN: true`)
- [ ] 关闭 (`DRY_RUN: false`)

## 期望行为 Expected Behavior

> 清晰描述应发生的情况

## 实际行为 Actual Behavior

> 清晰描述实际发生的情况,包括错误信息、日志输出、屏幕截图等

## 重现步骤 Steps to Reproduce

1. 
2. 
3. 
4. 

## 可能的修复建议 (可选) Possible Fix

---

**Note**: 安全相关问题请走 [SECURITY.md](../SECURITY.md) 的 private 报告流程。
