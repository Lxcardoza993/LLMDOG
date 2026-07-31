# 贡献指南 Contributing Guide

## 快速开始 Quick Start

1. Fork 本仓库
2. 创建分支: `git checkout -b feature/your-feature`
3. 本地测试: `make dev && make test && make lint`
4. Push 并提 PR

## 开发流程

### 1. 环境准备

```bash
# 推荐 Python 3.10+
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

### 2. 代码规范

- Commit message: 使用 [conventional commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `refactor:`
- 行宽: <= 88 字符
-导入: `isort` 排序, `black` 格式化

### 3. 测试要求

- 新增功能必须对应新增测试
- `make test` 覆盖率目标 **70%+**
- 测试文件命名: `test_*.py` 或 `*_test.py`

### 4. 配置文件

| 文件 | 说明 |
|------|------|
| `services.yaml.example` | 模板,提 PR 时可改 |
| `services.yaml` | 真实配置,**绝不要提交** (已在 .gitignore) |

## PR 检查清单

- [ ] `make dev` - 无错误
- [ ] `make lint` - 无警告
- [ ] `make test` - 全通过 + 覆盖率达标
- [ ] CHANGELOG 已更新(如有用户可见变更)
- [ ] DRY_RUN 模式验证过

## 致谢 Contributors

感谢所有贡献者! 本项目由 OpenClaw 中文社区 + linux.do 社区社区驱动。

<a href="https://github.com/Lxcardoza993/LLMDOG/graphs/contributors">
  <img src="https://-contributor.omg.api/llmdog.svg" alt="Contributors" />
</a>

---

See also: [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)
