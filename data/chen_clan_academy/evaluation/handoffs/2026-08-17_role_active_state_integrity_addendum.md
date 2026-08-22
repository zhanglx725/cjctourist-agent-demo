# 2026-08-17 Active 风格改造：状态完整性补充交接

本文件补充 `2026-08-17_role_active_architecture_and_remediation_report.md`，不修改队友维护的人工测试原始日志。

## 本轮合并修复（待统一回归）

1. **详情是只读重讲，不是第二次到站**：`request_stop_detail` 改走同一套 E5 已审核证据包。它使用临时空 Coverage 视图，因此不会因首讲已覆盖而压缩、错换或遗漏当前点内容。
2. **详情不污染后续状态**：详情不写 Coverage、不创建待续讲、不附加“完成本点/下一站”服务尾，也不会触发主动拍照。详情仍可进入 Active 角色生成与校验；失败则回退到当前点的安全正文，游览进度不变。
3. **结束总结口径修复**：`visit_summary` 现在认可 `narration_commit` 与 `deterministic_narration_fallback` 的成功首讲记录。旧逻辑只认 `stop_guidance`，会把 Active 成功发布误报为“无可确认 Coverage”。详情不提交 Coverage，因而不会被误计入。
4. **当前点绑定不变量**：定向测试检查详情后的 `active_stop_program.node_id == tour_state.current_stop_id`。月台会作为固定端到端样本继续验证：路线承诺、ContentPlan、对象、工艺、必讲事实与最终正文必须一致。
5. **主动拍照政策保持**：仅在已审核、路线计划且适宜的到站位置推荐；它必须独立成服务段、无内部术语。详情重讲不触发它。这不是“所有未询问拍照均禁止”。

## 新增自动化验收

- 详情后的 Coverage 与详情前完全一致；
- 详情不触发照片；
- 详情后的活动点位与 `current_stop_id` 一致；
- Active 角色提交后的工艺与对象进入结束总结；
- 原有路线进度仍由 A1 事件适配器独占。

尚未运行本轮统一回归，因此不得把以上改动标记为测试通过。
