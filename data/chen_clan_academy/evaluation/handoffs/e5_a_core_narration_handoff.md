# E5-A：核心讲解与 NarrationCoverage 交接

## E5-A1 状态

E5-A1 已实现纯数据模型与会话生命周期。E5-A2 已新增独立的 `GuidanceEvidenceBundle`，但尚未接入游客文案或成功讲解后的自动提交。

## 公共接口

- `empty_narration_coverage()`：建立空覆盖状态。
- `load_narration_coverage(value)`：加载既有字典；缺失字段的旧会话以 `None` 回退为空状态。
- `commit_introductions(coverage, records)`：不可变、原子地提交首次介绍记录；重复同一对象或工艺保持幂等并保留首条审计记录。
- `clear_narration_coverage()`：返回新的空覆盖状态。
- `is_craft_introduced()` / `is_ornament_introduced()`：只读查询。

工艺 ID 采用 `node_guide_cards_v1.json` 中已审核对象使用的规范工艺名称，例如“灰塑”“木雕”。仅做空白清理，不合并别名。文物使用稳定 `ornament_id`。

## 状态边界

`narration_coverage` 是 `AgentState` 的线程内字段。新路线在 `direct_route_node` 成功初始化时清空它；TourState、VisitorProfile、qa_context、active_stop_program 与 tour_interaction_state 均不写入该数据。

本步没有“讲解成功后自动提交”的行为：E5-A4 必须只在最终 visitor_message 成功生成且具备有效 evidence 时，提交由纯取证/编排层返回的待提交记录。

## E5-A2：结构化证据包

`guidance_evidence_bundle.py` 提供 `build_guidance_evidence_bundle(program, coverage, rag_search)`，输出：

- `craft_overviews`：仅首次接触工艺、仅接受 `07_ornament_crafts.md` 中精确工艺证据；同一工艺一轮只检索一次。
- `ornament_details`：每件实际选中对象均检索，且仅接受 `08_ornament_items.md` 中标题精确匹配该对象的 evidence。
- `location_evidence`：仅通过当前点、`final_node_id` 和 `change/add_node` 审核映射复核的位置提示；不产生文化事实来源。
- `coverage_status` 与 `coverage_candidates`：仅作为 E5-A4 后续提交依据；本步绝不写 `NarrationCoverage`。
- `evidence_by_item`：保留给 B3 调用方的兼容只读视图，未删除原有 B3 接口。

证据包失败关闭：单个 packet 的 RAG 异常或空结果只产生结构化空 packet，不能用其他对象/工艺 evidence 替代；来源编号仅从被接受的真实 evidence 去重汇总。

## E5-A3：中性证据渲染

`narration_rendering.py` 提供 `render_guidance_evidence(program, bundle, guidance_policy)`，返回不可变 `NarrationRenderResult`。它不调用 RAG、不调用 LLM、不写 AgentState 或 NarrationCoverage。

- 首次工艺仅在 A2 给出合格 `07` packet 时先于对象渲染；需要至少两类从 evidence 文本确定性识别的工艺维度，才保留 craft coverage candidate。
- 首次对象从合格 `08` packet 确定性选择形态/构图和题材/寓意/故事证据；缺少任一类时仅输出已有事实及 warning，不保留该对象候选。
- repeat 工艺只作一句回顾，repeat 对象不再生成首次候选。
- 首次工艺内容折入首个核心对象既有 `planned_seconds`，不建立第二份时间预算；当站点预算小于 150 秒时只渲染已选对象的稳定首项，后续对象列入 `omitted_ornament_ids`。
- `used_source_ids` 只汇总实际进入 visitor_message 的事实 evidence；位置映射不作为文化事实来源。`listen_only` 不产生任务或问句。

E5-A3 本身未替换 B3 普通渲染入口；E5-A4 已在首次到站成功输出后完成受控接入。`request_stop_detail` 在本增量仍保留 B3 的既有详细展开行为，待其专属证据契约完成后再迁移。

## E5-A4：真实 stop guidance 接入

`stop_guidance_node` 现读取缺失即为空的 `narration_coverage`，调用 A2/A3，并只在 E5 渲染具有非空 visitor_message、实际 rendered subject、实际使用来源、当前正式点位一致且候选未省略时构建 `IntroductionRecord`。`commit_introductions()` 对整组记录原子执行；任何构建或提交异常保留原 coverage。

新增的 AgentState 审计字段不保存 RAG 正文或游客全文：

- `active_guidance_evidence_bundle`：节点、packet subject、来源和首次/后续状态。
- `active_narration_render_audit`：渲染对象、使用来源、预算、遗漏对象、warning 及 coverage commit 状态。

若 A2/A3 失败，系统回退既有 B3 安全讲解并保持 coverage 不变。`tour_qa` 仍不写 coverage：游客先在问答中了解工艺、再到站时，首版仍可能得到首次工艺介绍；该限制待后续独立验收。

若 A2 只有 `07_ornament_crafts.md` 的工艺总述、而没有当前审核对象的合格 `08_ornament_items.md` 详情，A4 也会回退 B3：工艺总述不能单独取代到站对象讲解，更不能据此提交 coverage。

## 验证

沙箱使用项目解释器时其 `pyvenv.cfg` 仍引用不可用的 WindowsApps Python，因而本次没有把该环境的启动失败记为代码测试失败；以下命令待项目本机执行并回填结果。

请在 Windows CMD 使用项目虚拟环境执行：

```cmd
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest -v test_narration_coverage.py test_session_memory.py test_agent_tour_state.py test_tour_interaction_e2e.py
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest -v test_e5_guidance_evidence_bundle.py test_guide_program_evidence.py test_guide_narration.py test_agent_stop_guidance.py
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest -v test_e5_narration_rendering.py test_guide_narration.py test_guide_program_evidence.py test_agent_stop_guidance.py test_stage_b_e2e.py test_guidance_policy_integration.py
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest -v test_e5_stop_guidance_coverage_integration.py test_narration_coverage.py test_e5_guidance_evidence_bundle.py test_e5_narration_rendering.py test_agent_stop_guidance.py test_stage_b_e2e.py test_session_memory.py test_tour_interaction_e2e.py test_guidance_policy_integration.py
"D:\VScode_Project\codexspace\codex_agent\.venv\Scripts\python.exe" -m unittest discover -v
git diff --check
```

## 已知边界与冲突

未发现与 A1、TourState 或 E5 契约冲突。E5-A1 不保存 RAG 正文、游客回答正文或画像，不能用覆盖记录证明位置、历史或对象事实。
