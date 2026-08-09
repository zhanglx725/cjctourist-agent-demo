# Role Narration Shadow 质量验收交接

## 当前基线

案例 8 已由操作员在全新 Thread 中复测通过：

- 同时选择静听与儿童友好时进入 `clarification`；
- 单独选择儿童友好模式时进入 `role_mode_confirmation`；
- `active_role=child`，当前点位继续保持为前院中部；
- 儿童友好观察目标正确绑定独角狮；
- 未出现空白正文、自由 RAG 安全兜底或点位记忆丢失；
- `atomic_read_plan_shadow` 正常执行且未遮蔽游客正文。

案例 8 结论：`passed_by_operator`。

## 18 种风格 Shadow 质量门槛

`role_narration_quality.py` 只读取 `role_narration_evaluations` 审计，
不调用模型、不读取检索结果，也不写 TourState、VisitorProfile、路线或 Coverage。

质量报告固定覆盖已审核的 18 种风格，并按风格统计：

- 样本数量与验证通过率；
- Schema 成功率；
- fallback 比率；
- 事实边界、内部字段泄漏和游客正文安全违规；
- `listen_only` 互动违规；
- 状态写入违规；
- 旧正文保留违规；
- Shadow 中意外 Active 接管。

默认进入有限 Active 的必要条件为：

```text
每种风格样本数 >= 3
validation acceptance rate >= 95%
schema success rate >= 95%
fallback rate <= 5%
safety violations = 0
state writes = 0
legacy message violations = 0
active takeover in Shadow = 0
```

缺少任意风格样本时结果为 `shadow_only`，不能用其他风格的高通过率代替。
任何事实越界、内部字段泄漏、静听互动或状态写入均为硬阻塞项。

## 自动化覆盖

`test_role_narration_quality.py` 验证：

- 完整 18 种风格目录；
- 样本不足时失败关闭；
- 18 种风格各 3 条、共 54 条合格样本通过门槛；
- 安全与状态违规硬阻塞；
- 静听互动违规硬阻塞；
- 未知风格和畸形审计失败关闭。

当前仍保持 `active_takeover=false`。

## 下一步人工采样

在 LangSmith 中为每种风格采集至少 3 条真实点位讲解 Shadow 审计。
每条需保留 `active_role_narration_audit` 或对应的
`role_narration_evaluations` 最后一条记录。完成采样后，将审计数组交给
`evaluate_role_narration_shadow` 生成统一质量报告，再决定是否允许单风格、
单点位有限 Active。
