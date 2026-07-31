# Changelog

All notable changes to llmdog will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-31

### Added
- Initial release
- Multi-service monitoring (LLM proxies, HTTP web UIs, Docker containers, shell-probed daemons)
- LLM-powered diagnosis and auto-fix
- Four guardrails: double-confirm (second LLM) / minimal-change (whitelist) / rollbackable / denylist
- Bug learning self-healing (recurrent bugs → known_issue → self-heal)
- systemd user-level timer integration (no sudo)
- Telegram notification support

### Tests
- 26 test cases
- 71% code coverage

### Security
- DRY_RUN default: true
- Minimal-change fix strategy
- Denylist for dangerous commands

---

## Format

- **Added**: 新功能
- **Changed**: 变更
- **Deprecated**: 即将废弃
- **Removed**: 已移除
- **Fixed**: 修复
- **Security**: 安全修复
