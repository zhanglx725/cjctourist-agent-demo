# E5-C 讲解质量评测集、证据审计与人工验收交接

## 基线与范围

- `baseline_commit`：`824f8446fb2f23c5adb0ed7491e69b8a39c636cb`
- `branch`：`codex/e5-c-narration-evaluation`
- E5-C 当前提交：`null`（待提交；本文件不编造提交哈希）
- 当前阶段：静态评测与人工验收准备完成；LangSmith 人工执行尚未开始。

本交接仅记录 E5-C 的评测数据、证据链、测试和待执行人工验收。它不修改或替代 TourState、VisitorProfile、路线、空间数据、知识库事实、卡片注册表或生产讲解链路。

## 交付文件

- `data/chen_clan_academy/evaluation/e5_narration_cases_v1.yaml`
- `data/chen_clan_academy/evaluation/e5_evidence_coverage_audit_v1.yaml`
- `test_e5_narration_acceptance.py`
- `data/chen_clan_academy/evaluation/manual_reviews/e5_c_langsmith_manual_scoring_template_v1.yaml`
- `data/chen_clan_academy/evaluation/handoffs/e5_c_quality_evaluation_handoff.md`

## 当前统计与校验

| 项目 | 当前结果 |
| --- | ---: |
| 评测案例 | 19 |
| `executable_static` | 12 |
| `blocked_pending_e5_a` | 7 |
| 证据审计对象 | 12 |
| 已知证据/数据缺口 | 1 |
| E5-C 静态测试 | 10 通过 |
| 相关既有回归 | 21 通过 |
| `git diff --check` | 通过 |
| LangSmith 人工执行 | 0；未执行 |

静态测试已校验案例字段、受控状态、点位与对象白名单、S10/S11 来源登记、07/08/09 的证据链、画像覆盖、预算与 TourState 文字边界，以及阻塞案例的资格声明。测试不调用 LLM、网络、LangSmith 或 LangGraph。

## 当前真实能力边界

现有仓库可以执行静态证据、来源、点位、白名单、运行资格与审计检查；这些检查不代表生产讲解质量已经通过。

当前尚未实现 E5 契约中的 `NarrationCoverage`、`NarrationPlan`、首次/后续讲解判定、成功输出后的覆盖写入和覆盖记录的跨 thread 隔离。因此以下能力均未进行 LangSmith 人工验收，也不得报告为通过：首次工艺完整度、后续工艺不重复、首次文物完整度、预算内保留核心证据链、listen_only 首讲质量、Coverage 跨 thread 隔离、无证据时 Coverage 不写入。

人工评分模板保留 12 条待执行记录：6 条 `not_run` 静态资格场景，6 条 `blocked_pending_e5_a` 的 E5-A 依赖场景。所有评分、thread_id、Trace URL、TourState 前后快照和 finding 仍为空，等待真实 LangSmith 执行后填写。

## 证据审计结论

`07_ornament_crafts.md` 提供工艺总述（S10）；`08_ornament_items.md` 提供单件详情（S11）；`09_ornament_locations.md` 与 `node_guide_cards_v1.json` 提供位置和审核点位关联。审计覆盖灰塑、木雕、石雕、陶塑，以及独角狮、福禄寿、引福归堂、百鸟朝凤、博古图、石狮子、书字换鹅和凤凰牡丹。

唯一已知缺口为 `e5_cov_001`：

- 受影响对象：`orn_083`（凤凰牡丹）
- 现有点位卡工艺值：`凤穿牡丹）（陶塑`
- S11 单件资料名称/工艺：`凤凰牡丹（凤穿牡丹）` / `陶塑`
- 推荐负责人：`spatial_data_owner`
- 当前处理：仅在 `e5_evidence_coverage_audit_v1.yaml` 中记录；未修改点位卡、空间数据或知识库。

## E5-A / E5-B 后续验收责任

E5-A 合入后，应先解除相应案例的 `blocked_pending_e5_a` 资格，再在真实独立 thread 中执行评分模板。E5-C 不以 Mock、临时状态或通用会话隔离替代以下验收：

1. 首次灰塑讲解优先使用 07 证据，并连接当前点审核对象。
2. 后续灰塑讲解不重复完整定义，转向当前对象的新细节或差异。
3. 首次文物讲解满足位置、工艺、可见细节与有来源题材/故事的最低组合。
4. 短预算时减少对象或互动扩展，同时保留首次工艺和核心文物证据链。
5. `listen_only` 不降低事实深度，也不输出问题或任务式表达。
6. NarrationCoverage 在不同 thread 间不共享。
7. 无 evidence、澄清、错误或空输出不写入 NarrationCoverage。

生产实现和修复责任属于 E5-A、E5-B 或对应数据负责人；E5-C 只维护验收口径、证据审计、人工评分模板与问题记录。

## 修改边界与提交状态

本阶段未修改生产代码、知识库事实、空间数据、路线、TourState、VisitorProfile、公共文档或现有测试。本阶段未执行 LangSmith、未提交、未推送。
