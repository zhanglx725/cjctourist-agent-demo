# E5 集成验收记录

## 当前集成身份

```text
E5-0 契约基线：824f844
E5-A/B 生产实现：5183b7e
E5-C 评测基线：a643a5
E5-D 集成提交：effc5a5
集成分支：codex/e5-integration
```

## 评测历史与运行结果分离

`e5_narration_cases_v1.yaml`、其静态测试和 E5-C handoff 保留为历史冻结评测标准。E5-D 使用 `e5_narration_runtime_results_v1.yaml` 记录当前实现的真实运行结果；该覆盖层在本机自动测试和 LangSmith Trace 返回前全部为 `pending`，不把生产代码存在写成验收通过。

## 当前已知边界

- 当前沙箱无法启动项目 Windows 虚拟环境，原因是基础 WindowsApps Python 不可访问；这不是代码测试失败。
- `tour_qa` 仍不写 NarrationCoverage；游客先通过问答了解工艺后，到站仍可能得到首次工艺介绍。
- E5-C 已记录 `orn_083` 的工艺值规范化缺口，状态应保持数据复核，不由讲解模型补造。
- LangSmith 场景尚未执行，不得标记为 verified。
