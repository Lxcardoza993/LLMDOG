# PR: [简短标题]

## 改动摘要 Changes

> 1-2 句话描述这次 PR 做了什么

## 关联 Issue

- Closes: #xxx
- Related: #xxx

## 测试情况 Testing

```bash
# 本地测试结果
$ make dev
...
$ make lint
...
$ make test
...
coverage: XX%
```

- [ ] 新增测试覆盖
- [ ] 所有测试通过
- [ ] 覆盖率 >= 70%

## 配置文件变更

- [ ] 修改了 `services.yaml.example`
- [ ] 修改了真实 `services.yaml` (**请勿提交**)

## DRY_RUN 验证

- [ ] 本地 DRY_RUN 模式已验证
- [ ] 手动执行拟修复命令已测试

## 自查 Checklist

- [ ] Commit message 符合 [conventional commits](https://www.conventionalcommits.org/)
- [ ] 代码格式 (`black`, `isort`) 通过
- [ ] 类型检查 (`mypy`) 通过
- [ ] CHANGELOG 已更新 (如需)

---

**Note**: 安全相关改动请先 private 报告,勿直接公开 PR。
